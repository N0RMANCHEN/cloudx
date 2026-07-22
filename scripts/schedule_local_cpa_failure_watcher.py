#!/usr/bin/env python3
"""Wait for accepted combined local CPA activation, then activate its watcher separately."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Sequence

import schedule_local_cpa_policy_activation as activation


ROOT = pathlib.Path(__file__).resolve().parents[1]
WATCHER = ROOT / "scripts/install_cpa_failure_watcher.py"
CONTRACT = ROOT / "third_party/cliproxyapi/deployment-contract.json"
CONFIRMATION = "ACTIVATE LOCAL CPA FAILURE WATCHER 0.1.27"
PLAN_SCHEMA = "cloudx.local-cpa-failure-watcher-schedule-plan.v1"
SCHEDULE_SCHEMA = "cloudx.local-cpa-failure-watcher-schedule.v1"
JOB_SCHEMA = "cloudx.local-cpa-failure-watcher-job.v1"
RECEIPT_SCHEMA = "cloudx.local-cpa-failure-watcher-receipt.v1"
ACTIVATION_RECEIPT_SCHEMA = "cloudx.local-cpa-policy-activation-receipt.v2"
REQUIRED_VERSION = "0.1.27"
REQUIRED_POLICY_VERSION = "7.0.2-codexx-fast-service-tier-cloudx-policy.9-agent-identity"
REQUIRED_POLICY_SHA256 = "174a46d58a95f56104d0bb3722c4fb5e7dffc125f2f525505d96f556291aa761"
JOB_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$")
POLL_SECONDS = 60
FOLLOWER_GRACE_SECONDS = 60 * 60


class WatcherScheduleRejected(RuntimeError):
    pass


def watcher_module() -> Any:
    spec = importlib.util.spec_from_file_location("cloudx_cpa_failure_watcher", WATCHER)
    if spec is None or spec.loader is None:
        raise WatcherScheduleRejected("failure watcher cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def activation_job(path: pathlib.Path) -> tuple[pathlib.Path, Dict[str, Any]]:
    home = pathlib.Path.home().resolve()
    root = home / ".local/state/cloudx/cpa-policy-activation-jobs"
    try:
        resolved = path.expanduser().resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise WatcherScheduleRejected("activation job is outside the private job root") from exc
    if len(relative.parts) != 1 or not JOB_ID_RE.fullmatch(relative.parts[0]):
        raise WatcherScheduleRejected("activation job identity is invalid")
    info = resolved.lstat()
    if resolved.is_symlink() or not resolved.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise WatcherScheduleRejected("activation job permissions are unsafe")
    document = activation.load_json(resolved / "job.json", activation.JOB_SCHEMA)
    if (
        document.get("jobId") != resolved.name
        or document.get("requiredActiveCloudxVersion") != REQUIRED_VERSION
        or document.get("candidateVersion") != REQUIRED_POLICY_VERSION
        or document.get("candidateSha256") != REQUIRED_POLICY_SHA256
        or not isinstance(document.get("quiescenceDeadlineEpoch"), (int, float))
    ):
        raise WatcherScheduleRejected("activation job does not match local policy5")
    return resolved, document


def plan(job_id: str) -> Dict[str, Any]:
    if not JOB_ID_RE.fullmatch(job_id):
        raise WatcherScheduleRejected("activation job identity is invalid")
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "activationJobId": job_id,
        "requiredActiveCloudxVersion": REQUIRED_VERSION,
        "requiredPolicyVersion": REQUIRED_POLICY_VERSION,
        "requiredPolicySha256": REQUIRED_POLICY_SHA256,
        "pollSeconds": POLL_SECONDS,
        "requiresAcceptedActivationReceipt": True,
        "requiresActivationCommunicationCanary": True,
        "restartsExternalCPA": False,
        "stopsCodexProcesses": False,
        "automaticRollback": True,
        "automaticAction": False,
    }


def schedule(path: pathlib.Path, confirmation: str) -> Dict[str, Any]:
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise WatcherScheduleRejected("local watcher scheduling requires the macOS login user")
    job, activation_document = activation_job(path)
    document = plan(job.name)
    if confirmation != document["confirmation"]:
        raise WatcherScheduleRejected("local failure-watcher confirmation does not match")
    if activation.current_cloudx_version(pathlib.Path.home().resolve()) != REQUIRED_VERSION:
        raise WatcherScheduleRejected("required signed Cloudx release is not active")
    module = watcher_module()
    value = module.target_value("local", CONTRACT)
    expected = module.plan_document("local", value)
    if expected.get("confirmation") != CONFIRMATION:
        raise WatcherScheduleRejected("local failure-watcher plan changed")
    state_root = pathlib.Path.home().resolve() / ".local/state/cloudx/cpa-failure-watcher-jobs"
    activation.private_directory(state_root)
    follower = state_root / job.name
    if follower.exists():
        raise WatcherScheduleRejected("local failure-watcher follower already exists")
    activation.private_directory(follower)
    watcher_raw = activation.safe_read(WATCHER)
    contract_raw = activation.safe_read(CONTRACT)
    worker_raw = activation.safe_read(pathlib.Path(__file__).resolve())
    scheduler_raw = activation.safe_read(pathlib.Path(activation.__file__).resolve())
    activation.atomic_write(follower / "install_cpa_failure_watcher.py", watcher_raw)
    activation.atomic_write(follower / "deployment-contract.json", contract_raw)
    activation.atomic_write(follower / "schedule_local_cpa_failure_watcher.py", worker_raw)
    activation.atomic_write(follower / "schedule_local_cpa_policy_activation.py", scheduler_raw)
    follower_document = {
        "schema": JOB_SCHEMA,
        "jobId": job.name,
        "activationJob": str(job),
        "activationReceipt": str(job / "receipt.json"),
        "deadlineEpoch": float(activation_document["quiescenceDeadlineEpoch"]) + FOLLOWER_GRACE_SECONDS,
        "confirmation": confirmation,
        "watcherSha256": activation.sha256(watcher_raw),
        "contractSha256": activation.sha256(contract_raw),
        "workerSha256": activation.sha256(worker_raw),
        "schedulerSha256": activation.sha256(scheduler_raw),
        "requiredPolicyVersion": REQUIRED_POLICY_VERSION,
        "requiredPolicySha256": REQUIRED_POLICY_SHA256,
        "pollSeconds": POLL_SECONDS,
    }
    activation.atomic_json(follower / "job.json", follower_document)
    log = follower / "worker.log"
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    environment = {
        "HOME": str(pathlib.Path.home().resolve()),
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONUNBUFFERED": "1",
    }
    try:
        process = subprocess.Popen(
            [sys.executable, str(follower / "schedule_local_cpa_failure_watcher.py"), "--worker", str(follower)],
            stdin=subprocess.DEVNULL,
            stdout=descriptor,
            stderr=descriptor,
            cwd=str(follower),
            env=environment,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        os.close(descriptor)
    return {
        "schema": SCHEDULE_SCHEMA,
        "status": "scheduled",
        "jobId": job.name,
        "workerPid": process.pid,
        "activationReceipt": str(job / "receipt.json"),
        "receipt": str(follower / "receipt.json"),
        "log": str(log),
        "restartsExternalCPA": False,
    }


def emit(job_id: str, stage: str, status: str) -> None:
    print(json.dumps({"jobId": job_id, "stage": stage, "status": status}, sort_keys=True), flush=True)


def safe_receipt(path: pathlib.Path, schema: str) -> Dict[str, Any]:
    try:
        document = json.loads(activation.safe_read(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WatcherScheduleRejected("dependent receipt is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != schema:
        raise WatcherScheduleRejected("dependent receipt schema is invalid")
    return document


def write_receipt(path: pathlib.Path, document: Dict[str, Any]) -> None:
    activation.atomic_json(path, {"schema": RECEIPT_SCHEMA, **document})


def worker(path: pathlib.Path) -> int:
    document: Dict[str, Any] = {}
    receipt_path = path / "receipt.json"
    try:
        document = activation.load_json(path / "job.json", JOB_SCHEMA)
        if document.get("jobId") != path.name or not JOB_ID_RE.fullmatch(path.name):
            raise WatcherScheduleRejected("local watcher job identity changed")
        copies = {
            "watcher": (path / "install_cpa_failure_watcher.py", document["watcherSha256"]),
            "contract": (path / "deployment-contract.json", document["contractSha256"]),
            "worker": (path / "schedule_local_cpa_failure_watcher.py", document["workerSha256"]),
            "scheduler": (path / "schedule_local_cpa_policy_activation.py", document["schedulerSha256"]),
        }
        emit(document["jobId"], "job-validation", "started")
        for candidate, expected in copies.values():
            if activation.sha256(activation.safe_read(candidate)) != expected:
                raise WatcherScheduleRejected("local watcher job file digest changed")
        emit(document["jobId"], "job-validation", "accepted")
        emit(document["jobId"], "activation-receipt-wait", "started")
        activation_receipt = pathlib.Path(document["activationReceipt"])
        while not activation_receipt.is_file():
            if time.time() >= float(document["deadlineEpoch"]):
                write_receipt(receipt_path, {
                    "jobId": document["jobId"], "status": "failed", "failureCode": "activation_receipt_timeout",
                    "watcherActivated": False, "externalCpaRestarted": False,
                })
                return 1
            time.sleep(float(document.get("pollSeconds", POLL_SECONDS)))
        source = safe_receipt(activation_receipt, ACTIVATION_RECEIPT_SCHEMA)
        if (
            source.get("jobId") != document["jobId"]
            or source.get("status") != "accepted"
            or source.get("candidateVersion") != document["requiredPolicyVersion"]
            or source.get("candidateSha256") != document["requiredPolicySha256"]
            or source.get("communicationCanary") != "passed"
            or source.get("serviceAvailable") is not True
        ):
            emit(document["jobId"], "activation-receipt-wait", "rejected")
            write_receipt(receipt_path, {
                "jobId": document["jobId"], "status": "failed", "failureCode": "activation_not_accepted",
                "watcherActivated": False, "externalCpaRestarted": False,
            })
            return 1
        emit(document["jobId"], "activation-receipt-wait", "accepted")
        completed = subprocess.run(
            [
                sys.executable, str(copies["watcher"][0]), "--target", "local",
                "--contract", str(copies["contract"][0]), "--activate",
                "--confirm", str(document["confirmation"]),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120.0,
            check=False,
            cwd=str(path),
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise WatcherScheduleRejected("local watcher returned invalid JSON") from exc
        accepted = completed.returncode == 0 and result.get("status") in {"active", "already-active"}
        emit(document["jobId"], "watcher-activation", "accepted" if accepted else "failed")
        write_receipt(receipt_path, {
            "jobId": document["jobId"], "status": "accepted" if accepted else "failed",
            "failureCode": "" if accepted else "watcher_rejected",
            "watcherStatus": str(result.get("status") or ""),
            "watcherActivated": accepted, "externalCpaRestarted": False,
        })
        return 0 if accepted else 1
    except Exception:
        write_receipt(receipt_path, {
            "jobId": document.get("jobId", path.name), "status": "failed", "failureCode": "follower_failed",
            "watcherActivated": False, "externalCpaRestarted": False,
        })
        return 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--activation-job", type=pathlib.Path)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--worker", type=pathlib.Path, help=argparse.SUPPRESS)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.worker is not None:
        return worker(args.worker.resolve())
    if args.activation_job is None:
        raise WatcherScheduleRejected("activation job is required")
    job_id = args.activation_job.expanduser().name
    if not args.apply:
        print(json.dumps(plan(job_id), sort_keys=True))
        return 0
    print(json.dumps(schedule(args.activation_job, args.confirm), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatcherScheduleRejected as exc:
        print("schedule-local-cpa-failure-watcher: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
