#!/usr/bin/env python3
"""Schedule an explicitly confirmed local CPA activation after the current turn can finish."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install_cpa_policy_candidate.py"
RECOVERY_TOOL = ROOT / "scripts/recover_local_cpa_policy.py"
CONTRACT = ROOT / "third_party/cliproxyapi/deployment-contract.json"
REQUIRED_ACTIVE_CLOUDX_VERSION = "0.1.21"
PLAN_SCHEMA = "cloudx.local-cpa-policy-activation-schedule-plan.v2"
SCHEDULE_SCHEMA = "cloudx.local-cpa-policy-activation-schedule.v2"
JOB_SCHEMA = "cloudx.local-cpa-policy-activation-job.v2"
RECEIPT_SCHEMA = "cloudx.local-cpa-policy-activation-receipt.v2"
DEFAULT_DELAY_SECONDS = 180
MINIMUM_DELAY_SECONDS = 120
MAXIMUM_DELAY_SECONDS = 600
MAX_FILE_BYTES = 2 * 1024 * 1024


class ScheduleRejected(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_read(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise ScheduleRejected("required activation file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ScheduleRejected("activation file is unsafe or oversized")
        chunks = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise ScheduleRejected("activation file is oversized")
        return raw
    finally:
        os.close(descriptor)


def private_directory(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise ScheduleRejected("activation state directory is unsafe")
    path.chmod(0o700)


def atomic_write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> None:
    private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, document: Dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"))


def load_json(path: pathlib.Path, schema: str) -> Dict[str, Any]:
    try:
        document = json.loads(safe_read(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScheduleRejected("activation job is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != schema:
        raise ScheduleRejected("activation job schema is invalid")
    return document


def installer_module() -> Any:
    spec = importlib.util.spec_from_file_location("cloudx_cpa_policy_installer", INSTALLER)
    if spec is None or spec.loader is None:
        raise ScheduleRejected("CPA policy installer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def current_cloudx_version(home: pathlib.Path) -> str:
    current = home / ".local/lib/cloudx/current"
    if not current.is_symlink():
        return ""
    try:
        return current.resolve(strict=True).name
    except OSError:
        return ""


def plan(delay_seconds: int) -> Dict[str, Any]:
    module = installer_module()
    value = module.expanded_target("local", module.load_contract(CONTRACT))
    unused_stage, activation = module.confirmations("local", value)
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": activation,
        "candidateVersion": value["version"],
        "candidateSha256": value["candidateSha256"],
        "requiredActiveCloudxVersion": REQUIRED_ACTIVE_CLOUDX_VERSION,
        "deferredSeconds": delay_seconds,
        "currentTurnRestarted": False,
        "codexProcessesStopped": False,
        "sharedCPAUnavailableDuringRestart": True,
        "inFlightRequestContinuityGuaranteed": False,
        "realCodexCanaryBeforeActivation": True,
        "realCodexCanaryAfterActivation": True,
        "realCodexCanaryAfterRollback": True,
        "automaticRollback": True,
        "requiresZeroEstablishedConnections": True,
        "manualRecoveryPreparedBeforeRestart": True,
        "automaticRecoveryUsesManualTool": True,
        "failureStageReceipt": True,
        "automaticAction": False,
    }


def schedule(delay_seconds: int, confirmation: str) -> Dict[str, Any]:
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise ScheduleRejected("local CPA activation scheduling requires the macOS login user")
    document = plan(delay_seconds)
    if confirmation != document["confirmation"]:
        raise ScheduleRejected("local CPA activation confirmation does not match")
    home = pathlib.Path.home().resolve()
    if current_cloudx_version(home) != document["requiredActiveCloudxVersion"]:
        raise ScheduleRejected("required signed Cloudx receipt-consumer release is not active locally")
    module = installer_module()
    value = module.expanded_target("local", module.load_contract(CONTRACT))
    module.verify_candidate(value["stagedBinary"], value)

    state_root = home / ".local/state/cloudx/cpa-policy-activation-jobs"
    private_directory(state_root)
    job_id = "%s-%s" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), secrets.token_hex(4))
    job = state_root / job_id
    private_directory(job)
    installer_raw = safe_read(INSTALLER)
    recovery_raw = safe_read(RECOVERY_TOOL)
    contract_raw = safe_read(CONTRACT)
    worker_raw = safe_read(pathlib.Path(__file__).resolve())
    launcher_snapshot = module.safe_snapshot(
        value["launcher"], maximum=module.MAX_LAUNCHER_BYTES, required=True
    )
    baseline_snapshot = module.safe_snapshot(
        value["baselineBinary"], maximum=module.MAX_CANDIDATE_BYTES, required=True
    )
    if launcher_snapshot.mode != 0o644 or launcher_snapshot.uid != os.geteuid() or launcher_snapshot.gid != os.getegid():
        raise ScheduleRejected("local CPA launcher ownership or mode changed")
    if module.sha256_bytes(baseline_snapshot.data) != value["baselineSha256"]:
        raise ScheduleRejected("local CPA baseline binary changed")
    installer_copy = job / "install_cpa_policy_candidate.py"
    recovery_copy = job / "recover_local_cpa_policy.py"
    contract_copy = job / "deployment-contract.json"
    worker_copy = job / "schedule_local_cpa_policy_activation.py"
    atomic_write(installer_copy, installer_raw)
    atomic_write(recovery_copy, recovery_raw)
    atomic_write(contract_copy, contract_raw)
    atomic_write(worker_copy, worker_raw)
    atomic_write(job / "launcher.before", launcher_snapshot.data)
    execute_after = time.time() + delay_seconds
    launcher_sha256 = sha256(launcher_snapshot.data)
    recovery_confirmation = "RESTORE LOCAL CPA BASELINE %s %s" % (job_id, launcher_sha256[:12])
    job_document = {
        "schema": JOB_SCHEMA,
        "jobId": job_id,
        "createdAt": utc_now(),
        "executeAfterEpoch": execute_after,
        "confirmation": confirmation,
        "requiredActiveCloudxVersion": document["requiredActiveCloudxVersion"],
        "candidateVersion": document["candidateVersion"],
        "candidateSha256": document["candidateSha256"],
        "installerSha256": sha256(installer_raw),
        "recoveryToolSha256": sha256(recovery_raw),
        "contractSha256": sha256(contract_raw),
        "workerSha256": sha256(worker_raw),
        "launcherSnapshotSha256": launcher_sha256,
        "launcherPath": str(value["launcher"]),
        "launcherMode": launcher_snapshot.mode,
        "launcherUid": launcher_snapshot.uid,
        "launcherGid": launcher_snapshot.gid,
        "baselineBinary": str(value["baselineBinary"]),
        "baselineSha256": value["baselineSha256"],
        "serviceLabel": value["serviceLabel"],
        "configPath": str(value["config"]),
        "codexBinary": str(value["codexBinary"]),
        "communicationCodexHome": str(value["communicationCodexHome"]),
        "recoveryConfirmation": recovery_confirmation,
        "quiescenceSamples": 5,
        "quiescenceIntervalSeconds": 1.0,
    }
    atomic_json(job / "job.json", job_document)
    recovery_command = [
        sys.executable,
        str(recovery_copy),
        "--apply",
        "--job",
        str(job),
        "--confirm",
        recovery_confirmation,
    ]
    manual = (
        "Cloudx local CPA baseline recovery\n\n"
        "Inspect without changing service state:\n  %s --job %s\n\n"
        "Restore the pinned baseline and verify health plus real Codex communication:\n"
        "  %s --apply --job %s --confirm '%s'\n"
        % (recovery_copy, job, recovery_copy, job, recovery_confirmation)
    )
    atomic_write(job / "RECOVERY.txt", manual.encode("utf-8"))
    log_path = job / "worker.log"
    descriptor = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    environment = {
        "HOME": str(home),
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONUNBUFFERED": "1",
    }
    try:
        process = subprocess.Popen(
            [sys.executable, str(worker_copy), "--worker", str(job)],
            stdin=subprocess.DEVNULL,
            stdout=descriptor,
            stderr=descriptor,
            cwd=str(job),
            env=environment,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        os.close(descriptor)
    return {
        "schema": SCHEDULE_SCHEMA,
        "status": "scheduled",
        "jobId": job_id,
        "workerPid": process.pid,
        "executeAfterEpoch": execute_after,
        "deferredSeconds": delay_seconds,
        "currentTurnRestarted": False,
        "receipt": str(job / "receipt.json"),
        "log": str(log_path),
        "recoveryPlan": str(job / "RECOVERY.txt"),
        "recoveryCommand": recovery_command,
    }


def emit_worker_event(job_id: str, stage: str, status: str) -> None:
    print(json.dumps({"jobId": job_id, "stage": stage, "status": status}, sort_keys=True), flush=True)


def parse_result(raw: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def installer_failure_code(stderr: str) -> str:
    lowered = stderr.lower()
    for needle, code in (
        ("established connection", "connections_present"),
        ("quiescent", "connections_present"),
        ("baseline restoration", "automatic_recovery_failed"),
        ("communication", "communication_failed"),
        ("health", "health_failed"),
        ("launchd", "launchd_failed"),
        ("candidate", "candidate_rejected"),
    ):
        if needle in lowered:
            return code
    return "installer_rejected"


def run_recovery(job: pathlib.Path, recovery: pathlib.Path, document: Dict[str, Any]) -> Dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(recovery),
            "--apply",
            "--job",
            str(job),
            "--confirm",
            str(document["recoveryConfirmation"]),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=360.0,
        check=False,
        cwd=str(job),
    )
    result = parse_result(completed.stdout) or {}
    accepted = completed.returncode == 0 and result.get("status") in {"recovered", "already-recovered"}
    return {
        "status": "accepted" if accepted else "failed",
        "failureCode": str(result.get("failureCode") or "") if not accepted else "",
        "communicationCanary": str(result.get("communicationCanary") or "not-accepted"),
        "serviceRestarted": bool(result.get("serviceRestarted", False)),
        "serviceAvailable": bool(result.get("serviceAvailable", False)),
    }


def worker(job: pathlib.Path) -> int:
    receipt_path = job / "receipt.json"
    document: Optional[Dict[str, Any]] = None
    copies: Dict[str, Any] = {}
    activation_invoked = False
    installer_exit: Optional[int] = None
    failure_code = "worker_failed"
    recovery = {"status": "not-required", "communicationCanary": "not-run", "serviceRestarted": False, "serviceAvailable": False}
    try:
        document = load_json(job / "job.json", JOB_SCHEMA)
        emit_worker_event(document["jobId"], "job-validation", "started")
        copies = {
            "installer": (job / "install_cpa_policy_candidate.py", document.get("installerSha256")),
            "recovery": (job / "recover_local_cpa_policy.py", document.get("recoveryToolSha256")),
            "contract": (job / "deployment-contract.json", document.get("contractSha256")),
            "worker": (job / "schedule_local_cpa_policy_activation.py", document.get("workerSha256")),
            "launcher": (job / "launcher.before", document.get("launcherSnapshotSha256")),
        }
        for path, expected in copies.values():
            if sha256(safe_read(path)) != expected:
                raise ScheduleRejected("activation job file digest changed")
        emit_worker_event(document["jobId"], "job-validation", "accepted")
        delay = max(0.0, float(document["executeAfterEpoch"]) - time.time())
        if delay:
            emit_worker_event(document["jobId"], "deferred-wait", "started")
            time.sleep(delay)
        home = pathlib.Path.home().resolve()
        if current_cloudx_version(home) != document["requiredActiveCloudxVersion"]:
            raise ScheduleRejected("required signed Cloudx release changed before activation")
        emit_worker_event(document["jobId"], "activation", "started")
        activation_invoked = True
        completed = subprocess.run(
            [
                sys.executable,
                str(copies["installer"][0]),
                "--target",
                "local",
                "--contract",
                str(copies["contract"][0]),
                "--activate",
                "--confirm",
                str(document["confirmation"]),
                "--recovery-tool",
                str(copies["recovery"][0]),
                "--recovery-job",
                str(job),
                "--recovery-confirm",
                str(document["recoveryConfirmation"]),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600.0,
            check=False,
            cwd=str(job),
        )
        installer_exit = completed.returncode
        result = parse_result(completed.stdout) if completed.returncode == 0 else None
        accepted = bool(
            completed.returncode == 0
            and result
            and result.get("status") in {"active", "already-active"}
            and result.get("communicationCanary") == "passed"
        )
        if accepted:
            emit_worker_event(document["jobId"], "activation", "accepted")
        else:
            failure_code = installer_failure_code(completed.stderr)
            emit_worker_event(document["jobId"], "activation", "failed")
            recovery = run_recovery(job, copies["recovery"][0], document)
            emit_worker_event(document["jobId"], "baseline-recovery", recovery["status"])
        service_available = accepted or recovery["serviceAvailable"]
        communication_passed = accepted or recovery["communicationCanary"] == "passed"
        atomic_json(
            receipt_path,
            {
                "schema": RECEIPT_SCHEMA,
                "jobId": document["jobId"],
                "status": "accepted" if accepted else "failed",
                "completedAt": utc_now(),
                "installerExit": installer_exit,
                "candidateVersion": document["candidateVersion"],
                "candidateSha256": document["candidateSha256"],
                "failureCode": "" if accepted else failure_code,
                "communicationCanary": "passed" if communication_passed else "not-accepted",
                "recoveryStatus": recovery["status"],
                "recoveryCommunicationCanary": recovery["communicationCanary"],
                "recoveryServiceRestarted": recovery["serviceRestarted"],
                "serviceAvailable": service_available,
                "manualRecoveryPrepared": True,
                "recoveryPlan": str(job / "RECOVERY.txt"),
                "automaticRollbackOnInstallerFailure": True,
            },
        )
        return 0 if accepted else 1
    except Exception:
        if activation_invoked and document and copies.get("recovery"):
            try:
                recovery = run_recovery(job, copies["recovery"][0], document)
            except Exception:
                recovery = {"status": "failed", "communicationCanary": "not-accepted", "serviceRestarted": False, "serviceAvailable": False}
        service_available = recovery["serviceAvailable"]
        atomic_json(
            receipt_path,
            {
                "schema": RECEIPT_SCHEMA,
                "jobId": document.get("jobId", job.name) if document else job.name,
                "status": "failed",
                "completedAt": utc_now(),
                "installerExit": installer_exit,
                "failureCode": failure_code,
                "communicationCanary": "passed" if recovery["communicationCanary"] == "passed" else "not-accepted",
                "recoveryStatus": recovery["status"],
                "serviceAvailable": service_available,
                "manualRecoveryPrepared": bool(document),
                "recoveryPlan": str(job / "RECOVERY.txt"),
                "automaticRollbackOnInstallerFailure": True,
            },
        )
        return 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--delay-seconds", type=int, default=DEFAULT_DELAY_SECONDS)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--worker", type=pathlib.Path, help=argparse.SUPPRESS)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.worker is not None:
        return worker(args.worker.resolve())
    if not MINIMUM_DELAY_SECONDS <= args.delay_seconds <= MAXIMUM_DELAY_SECONDS:
        raise ScheduleRejected("local CPA activation delay must be between 120 and 600 seconds")
    if not args.apply:
        print(json.dumps(plan(args.delay_seconds), sort_keys=True))
        return 0
    print(json.dumps(schedule(args.delay_seconds, args.confirm), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScheduleRejected as exc:
        print("schedule-local-cpa-policy: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
