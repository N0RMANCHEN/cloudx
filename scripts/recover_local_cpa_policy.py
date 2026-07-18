#!/usr/bin/env python3
"""Inspect or restore the pinned local CPA baseline from a prepared activation job."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import pathlib
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple


JOB_SCHEMA = "cloudx.local-cpa-policy-activation-job.v2"
PLAN_SCHEMA = "cloudx.local-cpa-policy-recovery-plan.v1"
RESULT_SCHEMA = "cloudx.local-cpa-policy-recovery.v1"
RECEIPT_SCHEMA = "cloudx.local-cpa-policy-recovery-receipt.v1"
MAX_JOB_BYTES = 1024 * 1024
MAX_LAUNCHER_BYTES = 256 * 1024
MAX_BINARY_BYTES = 100 * 1024 * 1024
COMMUNICATION_CANARY_TEXT = "LOCAL_CPA_POLICY_COMMUNICATION_OK"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RecoveryRejected(RuntimeError):
    def __init__(self, code: str, message: str, *, service_restarted: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.service_restarted = service_restarted


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_read(path: pathlib.Path, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise RecoveryRejected("file_unavailable", "required recovery file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise RecoveryRejected("file_unsafe", "required recovery file is unsafe or oversized")
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
            raise RecoveryRejected("file_unsafe", "required recovery file is oversized")
        return raw
    finally:
        os.close(descriptor)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: pathlib.Path, maximum: int) -> str:
    return sha256_bytes(safe_read(path, maximum))


def fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: pathlib.Path, raw: bytes, *, mode: int, uid: int, gid: int) -> None:
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise RecoveryRejected("launcher_unsafe", "local CPA launcher path is unsafe")
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, uid, gid)
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, document: Dict[str, Any]) -> None:
    raw = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def required_string(document: Dict[str, Any], name: str) -> str:
    value = document.get(name)
    if not isinstance(value, str) or not value:
        raise RecoveryRejected("job_invalid", "recovery job field is invalid")
    return value


def required_path(document: Dict[str, Any], name: str) -> pathlib.Path:
    path = pathlib.Path(required_string(document, name))
    if not path.is_absolute():
        raise RecoveryRejected("job_invalid", "recovery job path is invalid")
    return path


def load_job(job: pathlib.Path) -> Dict[str, Any]:
    job = job.expanduser().absolute()
    info = job.lstat()
    if job.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise RecoveryRejected("job_unsafe", "recovery job directory is unsafe")
    job = job.resolve(strict=True)
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RecoveryRejected("job_unsafe", "recovery job directory is not private")
    try:
        document = json.loads(safe_read(job / "job.json", MAX_JOB_BYTES).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryRejected("job_invalid", "recovery job is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != JOB_SCHEMA:
        raise RecoveryRejected("job_invalid", "recovery job schema is invalid")
    if required_string(document, "jobId") != job.name:
        raise RecoveryRejected("job_invalid", "recovery job identity is invalid")
    for private_path in (job / "job.json", job / "launcher.before"):
        private_info = private_path.lstat()
        if private_path.is_symlink() or private_info.st_uid != os.geteuid() or stat.S_IMODE(private_info.st_mode) & 0o077:
            raise RecoveryRejected("job_unsafe", "recovery job file is not private")
    for name in ("baselineSha256", "launcherSnapshotSha256", "recoveryToolSha256"):
        if not SHA256_RE.fullmatch(required_string(document, name)):
            raise RecoveryRejected("job_invalid", "recovery job digest is invalid")
    if sha256_file(pathlib.Path(__file__).resolve(), MAX_JOB_BYTES) != document["recoveryToolSha256"]:
        raise RecoveryRejected("tool_changed", "recovery tool digest changed")
    snapshot = job / "launcher.before"
    if sha256_file(snapshot, MAX_LAUNCHER_BYTES) != document["launcherSnapshotSha256"]:
        raise RecoveryRejected("snapshot_changed", "recovery launcher snapshot changed")
    baseline = required_path(document, "baselineBinary")
    if sha256_file(baseline, MAX_BINARY_BYTES) != document["baselineSha256"]:
        raise RecoveryRejected("baseline_changed", "local CPA baseline binary changed")
    launcher = required_path(document, "launcherPath")
    if launcher.is_symlink() or launcher.parent.is_symlink() or not launcher.parent.is_dir():
        raise RecoveryRejected("launcher_unsafe", "local CPA launcher parent is unsafe")
    label = required_string(document, "serviceLabel")
    if not LABEL_RE.fullmatch(label) or label != "com.codexx.cliproxyapi":
        raise RecoveryRejected("job_invalid", "local CPA service label is invalid")
    if int(document.get("launcherUid", -1)) != os.geteuid() or int(document.get("launcherGid", -1)) != os.getegid():
        raise RecoveryRejected("job_invalid", "local CPA launcher owner contract is invalid")
    if int(document.get("launcherMode", -1)) != 0o644:
        raise RecoveryRejected("job_invalid", "local CPA launcher mode contract is invalid")
    expected_confirmation = "RESTORE LOCAL CPA BASELINE %s %s" % (job.name, document["launcherSnapshotSha256"][:12])
    if required_string(document, "recoveryConfirmation") != expected_confirmation:
        raise RecoveryRejected("job_invalid", "local CPA recovery confirmation is invalid")
    raw = safe_read(snapshot, MAX_LAUNCHER_BYTES)
    try:
        plist = plistlib.loads(raw)
    except Exception as exc:
        raise RecoveryRejected("snapshot_invalid", "recovery launcher snapshot is invalid") from exc
    arguments = plist.get("ProgramArguments")
    if plist.get("Label") != label or not isinstance(arguments, list) or not arguments:
        raise RecoveryRejected("snapshot_invalid", "recovery launcher snapshot contract is invalid")
    if arguments != [str(baseline), "--config", str(required_path(document, "configPath"))]:
        raise RecoveryRejected("snapshot_invalid", "recovery launcher does not select the baseline")
    document["jobPath"] = str(job)
    return document


def run_command(argv: Sequence[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryRejected("command_failed", "local CPA recovery command failed") from exc


def launch_state(document: Dict[str, Any]) -> Tuple[bool, int, bool]:
    service = "gui/%d/%s" % (os.geteuid(), document["serviceLabel"])
    completed = run_command(["launchctl", "print", service], timeout=10.0)
    match = re.search(r"\bpid = ([0-9]+)", completed.stdout)
    pid = int(match.group(1)) if match else 0
    selected = any(
        line.strip() == "program = %s" % document["baselineBinary"]
        for line in completed.stdout.splitlines()
    )
    return completed.returncode == 0, pid, selected


def top_level_endpoint(path: pathlib.Path) -> Tuple[str, int]:
    raw = safe_read(path, MAX_JOB_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecoveryRejected("config_invalid", "local CPA config is not UTF-8") from exc
    values: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        if key.strip() in {"host", "port"}:
            values[key.strip()] = raw_value.split("#", 1)[0].strip().strip("\"'")
    host = values.get("host", "")
    try:
        port = int(values.get("port", ""))
    except ValueError as exc:
        raise RecoveryRejected("config_invalid", "local CPA config port is invalid") from exc
    if not host or not 1 <= port <= 65535:
        raise RecoveryRejected("config_invalid", "local CPA config endpoint is invalid")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1" if host == "0.0.0.0" else "::1"
    return host, port


def probe_health(document: Dict[str, Any], timeout: float = 30.0) -> bool:
    host, port = top_level_endpoint(required_path(document, "configPath"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection: Optional[http.client.HTTPConnection] = None
        try:
            connection = http.client.HTTPConnection(host, port, timeout=2.0)
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            body = response.read(4096)
            if response.status == 200 and b'"status":"ok"' in body.replace(b" ", b""):
                return True
        except (OSError, http.client.HTTPException):
            pass
        finally:
            if connection is not None:
                connection.close()
        time.sleep(0.25)
    return False


def probe_communication(document: Dict[str, Any]) -> bool:
    codex_binary = required_path(document, "codexBinary")
    codex_home = required_path(document, "communicationCodexHome")
    if not codex_binary.is_file() or not os.access(codex_binary, os.X_OK):
        raise RecoveryRejected("codex_unavailable", "official Codex recovery canary is unavailable")
    if codex_home.is_symlink() or not codex_home.is_dir():
        raise RecoveryRejected("codex_profile_unavailable", "Codex recovery profile is unavailable")
    environment = dict(os.environ)
    environment["HOME"] = str(pathlib.Path.home().resolve())
    environment["CODEX_HOME"] = str(codex_home)
    for name in (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CLOUDX_MODE",
        "CLOUDX_MODE_LEASE_ID", "CLOUDX_MODE_BROKER_PORT", "CODEXX_ACTIVE_ACCOUNT",
        "CODEXX_ACTIVE_HOME", "CODEXX_ACTIVE_PINNED",
    ):
        environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-recovery-canary-") as temporary:
        try:
            completed = subprocess.run(
                [
                    str(codex_binary), "exec", "--skip-git-repo-check",
                    "Reply with exactly %s" % COMMUNICATION_CANARY_TEXT,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180.0,
                check=False,
                cwd=temporary,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RecoveryRejected("communication_failed", "Codex recovery canary failed") from exc
    return completed.returncode == 0 and COMMUNICATION_CANARY_TEXT in completed.stdout + completed.stderr


def established_socket_rows(document: Dict[str, Any]) -> int:
    unused_host, port = top_level_endpoint(required_path(document, "configPath"))
    completed = run_command(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:ESTABLISHED"], timeout=10.0)
    if completed.returncode not in {0, 1}:
        raise RecoveryRejected("connection_audit_failed", "local CPA connection audit failed")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return max(0, len(lines) - 1) if completed.returncode == 0 else 0


def check_quiescent(document: Dict[str, Any]) -> Dict[str, Any]:
    samples = int(document.get("quiescenceSamples", 3))
    interval = float(document.get("quiescenceIntervalSeconds", 1.0))
    maximum = 0
    for index in range(samples):
        rows = established_socket_rows(document)
        maximum = max(maximum, rows)
        if rows:
            return {
                "schema": RESULT_SCHEMA,
                "status": "busy",
                "establishedSocketRows": rows,
                "serviceChanged": False,
            }
        if index + 1 < samples:
            time.sleep(interval)
    return {
        "schema": RESULT_SCHEMA,
        "status": "quiescent",
        "establishedSocketRows": maximum,
        "serviceChanged": False,
    }


def wait_unloaded(document: Dict[str, Any], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    absent_samples = 0
    while time.monotonic() < deadline:
        loaded, unused_pid, unused_selected = launch_state(document)
        absent_samples = absent_samples + 1 if not loaded else 0
        if absent_samples >= 3:
            return
        time.sleep(0.25)
    raise RecoveryRejected("unload_timeout", "local CPA service did not fully unload")


def bootstrap_baseline(document: Dict[str, Any], timeout: float = 30.0) -> int:
    domain = "gui/%d" % os.geteuid()
    launcher = required_path(document, "launcherPath")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            run_command(["launchctl", "bootstrap", domain, str(launcher)], timeout=15.0)
        except RecoveryRejected:
            pass
        loaded, pid, selected = launch_state(document)
        if loaded and pid > 0 and selected:
            return pid
        time.sleep(0.5)
    raise RecoveryRejected("bootstrap_failed", "local CPA baseline could not be loaded")


def recovery_command(document: Dict[str, Any]) -> Sequence[str]:
    return [
        sys.executable, str(pathlib.Path(__file__).resolve()), "--apply", "--job",
        document["jobPath"], "--confirm", document["recoveryConfirmation"],
    ]


def plan(document: Dict[str, Any]) -> Dict[str, Any]:
    loaded, pid, selected = launch_state(document)
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "jobId": document["jobId"],
        "confirmation": document["recoveryConfirmation"],
        "command": recovery_command(document),
        "baselineLoaded": loaded and selected and pid > 0,
        "currentPid": pid,
        "automaticAction": False,
        "stopsCodexProcesses": False,
    }


def write_receipt(document: Dict[str, Any], result: Dict[str, Any]) -> None:
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "jobId": document["jobId"],
        "completedAt": utc_now(),
        "status": result.get("status", "failed"),
        "failureCode": result.get("failureCode", ""),
        "pid": result.get("pid", 0),
        "healthCanary": result.get("healthCanary", "not-accepted"),
        "communicationCanary": result.get("communicationCanary", "not-accepted"),
        "serviceRestarted": bool(result.get("serviceRestarted", False)),
        "serviceAvailable": bool(result.get("serviceAvailable", False)),
        "launcherRestored": bool(result.get("launcherRestored", False)),
    }
    atomic_json(pathlib.Path(document["jobPath"]) / "recovery-receipt.json", receipt)


def recover(document: Dict[str, Any], confirmation: str) -> Dict[str, Any]:
    if confirmation != document["recoveryConfirmation"]:
        raise RecoveryRejected("confirmation_mismatch", "local CPA recovery confirmation does not match")
    snapshot = safe_read(pathlib.Path(document["jobPath"]) / "launcher.before", MAX_LAUNCHER_BYTES)
    launcher = required_path(document, "launcherPath")
    current = safe_read(launcher, MAX_LAUNCHER_BYTES) if launcher.is_file() else b""
    loaded, pid, selected = launch_state(document)
    if sha256_bytes(current) == document["launcherSnapshotSha256"] and loaded and pid > 0 and selected:
        if probe_health(document, timeout=5.0):
            if not probe_communication(document):
                raise RecoveryRejected("communication_failed", "local CPA baseline communication canary failed")
            result = {
                "schema": RESULT_SCHEMA, "status": "already-recovered", "pid": pid,
                "healthCanary": "passed", "communicationCanary": "passed", "serviceRestarted": False,
                "serviceAvailable": True, "launcherRestored": False,
            }
            write_receipt(document, result)
            return result
    atomic_write(
        launcher,
        snapshot,
        mode=int(document["launcherMode"]),
        uid=int(document["launcherUid"]),
        gid=int(document["launcherGid"]),
    )
    loaded, pid, selected = launch_state(document)
    restarted = False
    if loaded and pid > 0 and selected and probe_health(document, timeout=5.0):
        if not probe_communication(document):
            raise RecoveryRejected("communication_failed", "local CPA baseline communication canary failed")
        result = {
            "schema": RESULT_SCHEMA, "status": "recovered", "pid": pid,
            "healthCanary": "passed", "communicationCanary": "passed", "serviceRestarted": False,
            "serviceAvailable": True, "launcherRestored": True,
        }
        write_receipt(document, result)
        return result
    service = "gui/%d/%s" % (os.geteuid(), document["serviceLabel"])
    if loaded:
        try:
            run_command(["launchctl", "bootout", service], timeout=45.0)
        except RecoveryRejected:
            pass
        wait_unloaded(document)
    pid = bootstrap_baseline(document)
    restarted = True
    if not probe_health(document):
        raise RecoveryRejected("health_failed", "local CPA baseline health canary failed", service_restarted=True)
    if not probe_communication(document):
        raise RecoveryRejected("communication_failed", "local CPA baseline communication canary failed", service_restarted=True)
    if sha256_file(launcher, MAX_LAUNCHER_BYTES) != document["launcherSnapshotSha256"]:
        raise RecoveryRejected("launcher_changed", "local CPA launcher changed during recovery", service_restarted=True)
    result = {
        "schema": RESULT_SCHEMA,
        "status": "recovered",
        "pid": pid,
        "healthCanary": "passed",
        "communicationCanary": "passed",
        "serviceRestarted": restarted,
        "serviceAvailable": True,
        "launcherRestored": True,
    }
    write_receipt(document, result)
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--job", type=pathlib.Path, required=True)
    action = root.add_mutually_exclusive_group()
    action.add_argument("--check-quiescent", action="store_true")
    action.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise RecoveryRejected("platform_invalid", "local CPA recovery requires the macOS login user")
    document = load_job(args.job.expanduser())
    if args.check_quiescent:
        result = check_quiescent(document)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "quiescent" else 1
    if not args.apply:
        print(json.dumps(plan(document), sort_keys=True))
        return 0
    try:
        result = recover(document, args.confirm)
    except RecoveryRejected as exc:
        pid = 0
        healthy = False
        try:
            loaded, pid, selected = launch_state(document)
            healthy = loaded and pid > 0 and selected and probe_health(document, timeout=2.0)
        except RecoveryRejected:
            pass
        result = {
            "schema": RESULT_SCHEMA,
            "status": "failed",
            "failureCode": exc.code,
            "pid": pid,
            "healthCanary": "passed" if healthy else "not-accepted",
            "communicationCanary": "not-accepted",
            "serviceRestarted": exc.service_restarted,
            "serviceAvailable": healthy,
            "launcherRestored": False,
        }
        write_receipt(document, result)
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryRejected as exc:
        print("recover-local-cpa-policy: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
