#!/usr/bin/env python3
"""Import one credential into the active cloud CPA and prove live model traffic."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import http.client
import json
import os
import pathlib
import pwd
import secrets
import stat
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ACTIVE_CLOUDX_VERSION = "0.1.18"
CONFIRMATION = "IMPORT ONE ACTIVE CLOUD CPA CREDENTIAL 0.1.18"
PLAN_SCHEMA = "cloudx.active-cpa-import-plan.v1"
RESULT_SCHEMA = "cloudx.active-cpa-import.v1"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
AUTH_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth")
ARCHIVE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-archive")
FAILURE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-failures")
SWEEP_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-sweeps")
TRANSACTION_ROOT = pathlib.Path("/var/lib/codex-gateway/active-import-transactions")
IMPORT_LOCK = AUTH_DIR / ".cloudx-import.lock"
ACTIVE_ARTIFACT = pathlib.Path("/opt/cloudx/current/cloudx-cloud.pyz")
CLIENT_CREDENTIAL = pathlib.Path("/etc/cloudx/client-credential")
CPA_SERVICE = "cliproxy.service"
FAILURE_PATH = "cloudx-cpa-failure.path"
SWEEP_PATH = "cloudx-cpa-sweep.path"
EXPECTED_TEXT = "CLOUDX_CLOUD_CPA_USABLE_OK"
MODEL_PRIORITY = (
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex",
    "gpt-5-codex",
)


class ActiveImportRejected(RuntimeError):
    def __init__(self, code: str, message: str, result: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.result = result


def run_command(
    argv: Sequence[str],
    *,
    input_bytes: Optional[bytes] = None,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[bytes]:
    try:
        kwargs: Dict[str, Any] = {"input": input_bytes} if input_bytes is not None else {"stdin": subprocess.DEVNULL}
        return subprocess.run(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ActiveImportRejected("command_failed", "active import command failed") from exc


def safe_json(raw: bytes) -> Dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActiveImportRejected("invalid_result", "active import returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ActiveImportRejected("invalid_result", "active import returned an invalid document")
    return value


def active_version() -> str:
    current = pathlib.Path("/opt/cloudx/current")
    if not current.is_symlink():
        return ""
    try:
        return current.resolve(strict=True).name
    except OSError:
        return ""


def service_state(name: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key in ("MainPID", "NRestarts", "ActiveState", "SubState", "Result"):
        completed = run_command(["systemctl", "show", name, "-p", key, "--value"], timeout=30.0)
        if completed.returncode != 0:
            raise ActiveImportRejected("service_unavailable", "CPA service state is unavailable")
        result[key] = completed.stdout.decode("utf-8", errors="replace").strip()
    return result


def unit_state(name: str) -> Tuple[bool, bool]:
    enabled = run_command(["systemctl", "is-enabled", name], timeout=30.0).returncode == 0
    active = run_command(["systemctl", "is-active", name], timeout=30.0).returncode == 0
    return enabled, active


def regular_json_files(root: pathlib.Path) -> List[pathlib.Path]:
    if root.is_symlink() or not root.is_dir():
        raise ActiveImportRejected("unsafe_auth_dir", "active CPA auth directory is unavailable")
    return sorted(
        path
        for path in root.iterdir()
        if path.suffix == ".json" and path.is_file() and not path.is_symlink()
    )


def regular_file_count(root: pathlib.Path) -> int:
    if not root.is_dir() or root.is_symlink():
        return 0
    return sum(1 for path in root.iterdir() if path.is_file() and not path.is_symlink())


def archive_entries() -> int:
    manifest = ARCHIVE_DIR / "manifest.json"
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActiveImportRejected("archive_unavailable", "CPA archive manifest is unavailable") from exc
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise ActiveImportRejected("archive_unavailable", "CPA archive manifest is invalid")
    return len(entries)


def validate_private_directory(path: pathlib.Path, uid: int, gid: int) -> None:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise ActiveImportRejected("unsafe_directory", "active import directory is unsafe")
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != uid or info.st_gid != gid:
        raise ActiveImportRejected("unsafe_directory", "active import directory ownership changed")


def ensure_transaction_root() -> None:
    TRANSACTION_ROOT.mkdir(parents=True, exist_ok=True)
    os.chown(TRANSACTION_ROOT, 0, 0)
    TRANSACTION_ROOT.chmod(0o700)
    validate_private_directory(TRANSACTION_ROOT, 0, 0)


def atomic_json(path: pathlib.Path, document: Dict[str, Any]) -> None:
    temporary = path.with_name(".%s.%d.%s" % (path.name, os.getpid(), secrets.token_hex(3)))
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_input(stream: Any) -> bytes:
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ActiveImportRejected("input_invalid", "credential input is empty or oversized")
    return raw


def signed_import(raw: bytes, dry_run: bool) -> Dict[str, Any]:
    cliproxy = pwd.getpwnam("cliproxy")
    command = [
        "sudo",
        "-n",
        "-u",
        cliproxy.pw_name,
        "env",
        "CLOUDX_AUTH_DIR=%s" % AUTH_DIR,
        "CLOUDX_IMPORT_LOCK=%s" % IMPORT_LOCK,
        sys.executable,
        str(ACTIVE_ARTIFACT),
        "import",
    ]
    if dry_run:
        command.append("--dry-run")
    completed = run_command(command, input_bytes=raw, timeout=60.0)
    document = safe_json(completed.stdout)
    if completed.returncode != 0 or document.get("status") != "accepted":
        raise ActiveImportRejected("import_rejected", "signed active importer rejected the credential")
    return document


def client_credential() -> str:
    try:
        value = CLIENT_CREDENTIAL.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ActiveImportRejected("credential_unavailable", "gateway client credential is unavailable") from exc
    if not value or len(value) > 4096:
        raise ActiveImportRejected("credential_unavailable", "gateway client credential is invalid")
    return value


def request(
    host: str,
    port: int,
    credential: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 180.0,
) -> Tuple[int, Dict[str, str], bytes]:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    headers = {"Authorization": "Bearer %s" % credential}
    raw = None
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ActiveImportRejected("response_oversized", "gateway response is oversized")
        return response.status, {key.lower(): value for key, value in response.getheaders()}, data
    except (OSError, http.client.HTTPException) as exc:
        raise ActiveImportRejected("gateway_unavailable", "gateway request failed") from exc
    finally:
        connection.close()


def select_model(document: Dict[str, Any]) -> str:
    data = document.get("data")
    models = [
        item.get("id")
        for item in data
        if isinstance(data, list) and isinstance(item, dict) and isinstance(item.get("id"), str)
    ] if isinstance(data, list) else []
    for candidate in MODEL_PRIORITY:
        if candidate in models:
            return candidate
    for candidate in models:
        if "codex" in candidate.lower():
            return candidate
    return models[0] if models else ""


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def live_canary(host: str, port: int) -> Dict[str, Any]:
    credential = client_credential()
    model = ""
    for _unused in range(20):
        status, _headers, raw = request(host, port, credential, "GET", "/v1/models", timeout=10.0)
        if status == 200:
            try:
                model = select_model(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                model = ""
            if model:
                break
        time.sleep(1.0)
    if not model:
        raise ActiveImportRejected("models_unavailable", "gateway did not expose a usable model")
    status, headers, raw = request(
        host,
        port,
        credential,
        "POST",
        "/v1/responses",
        {
            "model": model,
            "input": "Reply with exactly %s" % EXPECTED_TEXT,
            "max_output_tokens": 64,
            "stream": False,
        },
    )
    accepted = False
    if status == 200:
        try:
            accepted = EXPECTED_TEXT in "\n".join(strings(json.loads(raw.decode("utf-8"))))
        except (UnicodeDecodeError, json.JSONDecodeError):
            accepted = False
    policy = headers.get("x-cpa-max-concurrent-api-requests", "")
    if not accepted:
        raise ActiveImportRejected("live_model_failed", "live model canary failed")
    if policy != "2":
        raise ActiveImportRejected("policy_mismatch", "gateway concurrency policy is not two")
    return {"model": model, "httpStatus": status, "policy": policy}


def move_to_transaction_rollback(path: pathlib.Path, transaction: pathlib.Path) -> None:
    rollback = transaction / "rollback"
    rollback.mkdir(mode=0o700)
    os.chown(rollback, 0, 0)
    validate_private_directory(rollback, 0, 0)
    if path.stat().st_dev != rollback.stat().st_dev:
        raise ActiveImportRejected("rollback_unavailable", "active import rollback is not same-filesystem")
    os.replace(path, rollback / path.name)


def plan(host: str, port: int) -> Dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "requiredActiveCloudxVersion": ACTIVE_CLOUDX_VERSION,
        "input": "one-credential-via-stdin",
        "gateway": "%s:%d" % (host, port),
        "requiresEmptyActivePool": True,
        "signedImporterDryRun": True,
        "signedImporterApply": True,
        "liveResponsesCanary": True,
        "requiredBusinessPolicy": 2,
        "automaticRollbackOnUnknownFailure": True,
        "rawCredentialStored": False,
        "serviceRestarted": False,
        "automaticAction": False,
    }


def apply(raw: bytes, host: str, port: int) -> Dict[str, Any]:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ActiveImportRejected("wrong_host", "active cloud import requires root on Linux")
    if active_version() != ACTIVE_CLOUDX_VERSION:
        raise ActiveImportRejected("release_mismatch", "required signed Cloudx release is not active")
    self_check = safe_json(run_command([sys.executable, str(ACTIVE_ARTIFACT), "self-check"]).stdout)
    if self_check.get("version") != ACTIVE_CLOUDX_VERSION or self_check.get("status") != "ok":
        raise ActiveImportRejected("release_mismatch", "active signed Cloudx self-check failed")
    if unit_state(FAILURE_PATH) != (True, True) or unit_state(SWEEP_PATH) != (True, True):
        raise ActiveImportRejected("watcher_unavailable", "cloud CPA watchers are not active")
    before_files = regular_json_files(AUTH_DIR)
    if before_files:
        raise ActiveImportRejected("active_pool_not_empty", "active CPA pool must be empty for first acceptance")
    service_before = service_state(CPA_SERVICE)
    archive_before = archive_entries()
    failure_before = regular_file_count(FAILURE_DIR)
    sweep_before = regular_file_count(SWEEP_DIR)
    preview = signed_import(raw, True)
    if preview.get("written") != 1 or preview.get("skipped") != 0:
        raise ActiveImportRejected("dry_run_mismatch", "active import dry-run did not plan exactly one write")

    ensure_transaction_root()
    transaction_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    transaction = TRANSACTION_ROOT / transaction_id
    transaction.mkdir(mode=0o700)
    os.chown(transaction, 0, 0)
    validate_private_directory(transaction, 0, 0)
    atomic_json(
        transaction / "manifest.json",
        {
            "schema": RESULT_SCHEMA,
            "transactionId": transaction_id,
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "requestHash": hashlib.sha256(raw).hexdigest(),
            "activeBefore": 0,
            "archiveBefore": archive_before,
            "rawCredentialStored": False,
        },
    )

    target: Optional[pathlib.Path] = None
    try:
        imported = signed_import(raw, False)
        if imported.get("written") != 1 or imported.get("requestId") != preview.get("requestId"):
            raise ActiveImportRejected("apply_mismatch", "active import apply result changed")
        after_files = regular_json_files(AUTH_DIR)
        created = [path for path in after_files if path not in before_files]
        if len(created) != 1:
            raise ActiveImportRejected("target_mismatch", "active import did not create exactly one credential")
        target = created[0]
        info = target.stat()
        cliproxy = pwd.getpwnam("cliproxy")
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != cliproxy.pw_uid or info.st_gid != cliproxy.pw_gid:
            raise ActiveImportRejected("target_unsafe", "active credential ownership or mode is invalid")
        canary = live_canary(host, port)
        service_after = service_state(CPA_SERVICE)
        if service_after != service_before:
            raise ActiveImportRejected("service_changed", "CPA service changed during active import")
        if len(regular_json_files(AUTH_DIR)) != 1 or archive_entries() != archive_before:
            raise ActiveImportRejected("state_changed", "CPA credential/archive state changed unexpectedly")
        if regular_file_count(FAILURE_DIR) != failure_before or regular_file_count(SWEEP_DIR) != sweep_before:
            raise ActiveImportRejected("trigger_changed", "CPA watcher input changed after successful canary")
        receipt = {
            "schema": RESULT_SCHEMA,
            "transactionId": transaction_id,
            "status": "accepted",
            "requestId": imported.get("requestId"),
            "written": 1,
            "activeAuth": 1,
            "archiveEntries": archive_before,
            "liveModelTraffic": "passed",
            "model": canary["model"],
            "httpStatus": canary["httpStatus"],
            "policy": canary["policy"],
            "cpaPid": int(service_before["MainPID"]),
            "cpaRestarts": int(service_before["NRestarts"]),
            "serviceRestarted": False,
            "rawCredentialStored": False,
        }
        atomic_json(transaction / "receipt.json", receipt)
        return receipt
    except ActiveImportRejected as exc:
        time.sleep(3.0)
        archived = archive_entries() > archive_before
        if target is None:
            candidates = [path for path in regular_json_files(AUTH_DIR) if path not in before_files]
            target = candidates[0] if len(candidates) == 1 else None
        if target is not None and target.exists():
            move_to_transaction_rollback(target, transaction)
        restored = not regular_json_files(AUTH_DIR) and service_state(CPA_SERVICE) == service_before
        receipt = {
            "schema": RESULT_SCHEMA,
            "transactionId": transaction_id,
            "status": "failed",
            "failureCode": exc.code,
            "watcherArchived": archived,
            "baselineRestored": restored,
            "serviceRestarted": False,
            "rawCredentialStored": False,
        }
        atomic_json(transaction / "receipt.json", receipt)
        raise ActiveImportRejected(
            exc.code,
            "active credential import failed and was contained",
            result=receipt,
        ) from exc


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--host", default="100.90.97.113")
    root.add_argument("--port", type=int, default=8317)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    return root


def main(argv: Optional[Sequence[str]] = None, stream: Any = None) -> int:
    args = parser().parse_args(argv)
    document = plan(args.host, args.port)
    if not args.apply:
        print(json.dumps(document, sort_keys=True))
        return 0
    if args.confirm != CONFIRMATION:
        raise ActiveImportRejected("confirmation_mismatch", "active import confirmation does not match")
    raw = read_input(stream if stream is not None else sys.stdin.buffer)
    print(json.dumps(apply(raw, args.host, args.port), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActiveImportRejected as exc:
        if exc.result is not None:
            print(json.dumps(exc.result, sort_keys=True))
        print("import-active-cloud-cpa: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
