#!/usr/bin/env python3
"""Promote one exact Agent Identity batch into the live cloud CPA pool."""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import pwd
import re
import secrets
import shutil
import stat
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import import_active_cloud_cpa_credential as base


ACTIVE_CLOUDX_VERSION = "0.1.25"
REQUIRED_CPA_VERSION = "7.2.71-cloudx-policy.8"
REQUIRED_CPA_SHA256 = "4dfa561451662ca5deae566f6fcfdc32bec7f42590439fa053000c4b84f915c0"
REQUIRED_CAPABILITY = "codex-agent-identity-v1"
PLAN_SCHEMA = "cloudx.active-agent-identity-promotion-plan.v1"
RESULT_SCHEMA = "cloudx.active-agent-identity-promotion.v1"
MAX_BATCH = 32
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
AUTH_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth")
ARCHIVE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-archive")
FAILURE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-failures")
SWEEP_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-sweeps")
TRANSACTION_ROOT = pathlib.Path("/var/lib/codex-gateway/agent-identity-promotions")
RUNTIME_ROOT = pathlib.Path("/run/cloudx-agent-identity-promotion")
ACTIVE_ARTIFACT = pathlib.Path("/opt/cloudx/current/cloudx-cloud.pyz")
CAPABILITY_SIDECAR = pathlib.Path("/etc/cloudx/cloud-cpa-capabilities.json")
IMPORT_LOCK = AUTH_DIR / ".cloudx-import.lock"
CPA_SERVICE = "cliproxy.service"
FAILURE_PATH = "cloudx-cpa-failure.path"
SWEEP_PATH = "cloudx-cpa-sweep.path"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
ED25519_PKCS8_PREFIX = bytes.fromhex("302e020100300506032b657004220420")


Rejected = base.ActiveImportRejected


def confirmation(expected_sha256: str, expected_active: int, expected_new: int) -> str:
    return "PROMOTE CLOUD AGENT IDENTITY BATCH %s %d+%d %s" % (
        ACTIVE_CLOUDX_VERSION,
        expected_active,
        expected_new,
        expected_sha256[:16],
    )


def recovery_confirmation(transaction_id: str) -> str:
    return "ROLL BACK CLOUD AGENT IDENTITY PROMOTION %s" % transaction_id


def validate_expectations(expected_sha256: str, expected_active: int, expected_new: int) -> None:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise Rejected("invalid_arguments", "expected request SHA-256 is invalid")
    if expected_active < 1 or expected_active > 128:
        raise Rejected("invalid_arguments", "expected active count is invalid")
    if expected_new < 1 or expected_new > MAX_BATCH:
        raise Rejected("invalid_arguments", "expected batch count is invalid")


def plan(expected_sha256: str, expected_active: int, expected_new: int) -> Dict[str, Any]:
    validate_expectations(expected_sha256, expected_active, expected_new)
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": confirmation(expected_sha256, expected_active, expected_new),
        "requiredActiveCloudxVersion": ACTIVE_CLOUDX_VERSION,
        "requiredCpaVersion": REQUIRED_CPA_VERSION,
        "requiredCpaSha256": REQUIRED_CPA_SHA256,
        "requiredCapability": REQUIRED_CAPABILITY,
        "requestSha256": expected_sha256,
        "activeBefore": expected_active,
        "newCredentials": expected_new,
        "activeAfter": expected_active + expected_new,
        "signedImporterDryRun": True,
        "signedImporterApply": True,
        "baselineTemporarilyHeldForCohortCanary": True,
        "cohortCanaryRequests": expected_new,
        "automaticRollback": True,
        "manualRecoveryPreparedBeforeMutation": True,
        "rawCredentialStored": False,
        "serviceRestarted": False,
        "automaticAction": False,
    }


def recovery_plan(transaction_id: str) -> Dict[str, Any]:
    if not TRANSACTION_RE.fullmatch(transaction_id):
        raise Rejected("invalid_arguments", "transaction ID is invalid")
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": recovery_confirmation(transaction_id),
        "transactionId": transaction_id,
        "action": "restore-pre-promotion-active-pool",
        "serviceRestarted": False,
        "automaticAction": False,
    }


def read_input(stream: Any, expected_sha256: str) -> bytes:
    raw = base.read_input(stream)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise Rejected("input_mismatch", "credential input does not match the confirmed request")
    return raw


def _safe_bytes(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise Rejected("unsafe_file", "promotion input file is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise Rejected("unsafe_file", "promotion input file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise Rejected("unsafe_file", "promotion input file is invalid")
        raw = b""
        while len(raw) <= maximum:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise Rejected("unsafe_file", "promotion input file changed while reading") from exc
    if len(raw) > maximum or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise Rejected("unsafe_file", "promotion input file changed while reading")
    return raw


def _sha256(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> str:
    return hashlib.sha256(_safe_bytes(path, maximum)).hexdigest()


def _json_file(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> Dict[str, Any]:
    try:
        value = json.loads(_safe_bytes(path, maximum).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("invalid_state", "promotion state is invalid") from exc
    if not isinstance(value, dict):
        raise Rejected("invalid_state", "promotion state is invalid")
    return value


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _private_directory(path: pathlib.Path, mode: int = 0o700, uid: int = 0, gid: int = 0) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise Rejected("unsafe_directory", "promotion directory is unsafe")
    os.chown(path, uid, gid)
    path.chmod(mode)
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != mode or info.st_uid != uid or info.st_gid != gid:
        raise Rejected("unsafe_directory", "promotion directory ownership changed")


def _file_map(root: pathlib.Path, suffix: str = "") -> Dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise Rejected("unsafe_directory", "promotion state directory is unavailable")
    result: Dict[str, str] = {}
    for path in sorted(root.iterdir()):
        if path.is_symlink():
            raise Rejected("unsafe_file", "promotion state contains a symlink")
        if not path.is_file() or (suffix and path.suffix != suffix):
            continue
        result[path.name] = _sha256(path)
    return result


def _copy_private(source: pathlib.Path, target: pathlib.Path, mode: int = 0o600) -> None:
    raw = _safe_bytes(source)
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(mode)
        os.chown(target, 0, 0)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _archive_entries() -> List[Dict[str, Any]]:
    document = _json_file(ARCHIVE_DIR / "manifest.json", MAX_MANIFEST_BYTES)
    entries = document.get("entries")
    if document.get("schema") != "cloudx.cpa-quarantine.v1" or not isinstance(entries, list):
        raise Rejected("archive_invalid", "CPA archive manifest is invalid")
    if any(not isinstance(entry, dict) for entry in entries):
        raise Rejected("archive_invalid", "CPA archive manifest is invalid")
    return list(entries)


def _capability_state(service: Mapping[str, str]) -> Tuple[Dict[str, Any], pathlib.Path]:
    document = _json_file(CAPABILITY_SIDECAR, MAX_MANIFEST_BYTES)
    capabilities = document.get("capabilities")
    binary = pathlib.Path(str(document.get("binary") or ""))
    if (
        document.get("schema") != "cloudx.cloud-cpa-capabilities.v1"
        or document.get("runtimeVersion") != REQUIRED_CPA_VERSION
        or document.get("binarySha256") != REQUIRED_CPA_SHA256
        or not isinstance(capabilities, list)
        or REQUIRED_CAPABILITY not in capabilities
        or not binary.is_absolute()
        or _sha256(binary, 256 * 1024 * 1024) != REQUIRED_CPA_SHA256
    ):
        raise Rejected("capability_mismatch", "active cloud CPA capability evidence does not match")
    pid = int(service.get("MainPID") or 0)
    try:
        executable = pathlib.Path(os.readlink("/proc/%d/exe" % pid)).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise Rejected("service_unavailable", "active cloud CPA executable is unavailable") from exc
    if executable != binary.resolve(strict=True):
        raise Rejected("capability_mismatch", "active cloud CPA executable does not match")
    return document, binary


def _validate_active_files(paths: Sequence[pathlib.Path], uid: int, gid: int) -> None:
    for path in paths:
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != uid or info.st_gid != gid:
            raise Rejected("active_pool_unsafe", "active CPA credential ownership or mode is invalid")


def _preflight(expected_active: int) -> Dict[str, Any]:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise Rejected("wrong_host", "active Agent Identity promotion requires root on Linux")
    if base.active_version() != ACTIVE_CLOUDX_VERSION:
        raise Rejected("release_mismatch", "required signed Cloudx release is not active")
    self_check = base.safe_json(base.run_command([sys.executable, str(ACTIVE_ARTIFACT), "self-check"]).stdout)
    if self_check.get("status") != "ok" or self_check.get("version") != ACTIVE_CLOUDX_VERSION:
        raise Rejected("release_mismatch", "active signed Cloudx self-check failed")
    if base.unit_state(FAILURE_PATH) != (True, True) or base.unit_state(SWEEP_PATH) != (True, True):
        raise Rejected("watcher_unavailable", "cloud CPA watchers are not active")
    service = base.service_state(CPA_SERVICE)
    if service.get("ActiveState") != "active" or service.get("SubState") != "running":
        raise Rejected("service_unavailable", "cloud CPA service is unavailable")
    cliproxy = pwd.getpwnam("cliproxy")
    if any(path.suffix == ".json" and (path.is_symlink() or not path.is_file()) for path in AUTH_DIR.iterdir()):
        raise Rejected("active_pool_unsafe", "active CPA credential entry is unsafe")
    active = base.regular_json_files(AUTH_DIR)
    if len(active) != expected_active:
        raise Rejected("active_pool_changed", "active CPA count does not match the confirmed baseline")
    _validate_active_files(active, cliproxy.pw_uid, cliproxy.pw_gid)
    if base.regular_files(FAILURE_DIR):
        raise Rejected("watcher_input_not_empty", "CPA failure input is not empty")
    base.require_available_pool_observation(SWEEP_DIR)
    archive = _archive_entries()
    sidecar, binary = _capability_state(service)
    return {
        "service": service,
        "active": active,
        "activeMap": {path.name: _sha256(path) for path in active},
        "archiveEntries": archive,
        "archiveCount": len(archive),
        "failureMap": _file_map(FAILURE_DIR),
        "sweepMap": _file_map(SWEEP_DIR),
        "cliproxyUid": cliproxy.pw_uid,
        "cliproxyGid": cliproxy.pw_gid,
        "sidecar": sidecar,
        "binary": binary,
    }


@contextmanager
def _transaction_lock() -> Iterator[None]:
    _private_directory(TRANSACTION_ROOT)
    lock_path = TRANSACTION_ROOT / ".promotion.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Rejected("promotion_busy", "another active promotion is running") from exc
        yield


def _prepare_transaction(
    baseline: Dict[str, Any], expected_sha256: str, expected_new: int
) -> pathlib.Path:
    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    transaction = TRANSACTION_ROOT / transaction_id
    _private_directory(transaction)
    for relative in ("baseline/active", "hold/active", "rollback/active", "rollback/failure", "evidence", "tool"):
        _private_directory(transaction / relative)
    for source, name, mode in (
        (pathlib.Path(__file__).resolve(strict=True), "promote_cloud_agent_identity_batch.py", 0o700),
        (pathlib.Path(base.__file__).resolve(strict=True), "import_active_cloud_cpa_credential.py", 0o600),
    ):
        _copy_private(source, transaction / "tool" / name, mode)
    for source in baseline["active"]:
        _copy_private(source, transaction / "baseline/active" / source.name)
    manifest = {
        "schema": RESULT_SCHEMA,
        "transactionId": transaction_id,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "phase": "prepared",
        "requestHash": expected_sha256,
        "expectedNew": expected_new,
        "activeBefore": len(baseline["active"]),
        "activeAfter": len(baseline["active"]) + expected_new,
        "baselineActive": baseline["activeMap"],
        "archiveEntries": baseline["archiveEntries"],
        "archiveCount": baseline["archiveCount"],
        "failureMap": baseline["failureMap"],
        "sweepMap": baseline["sweepMap"],
        "service": baseline["service"],
        "cliproxyUid": baseline["cliproxyUid"],
        "cliproxyGid": baseline["cliproxyGid"],
        "promoted": {},
        "rawCredentialStored": False,
        "toolSha256": _sha256(transaction / "tool/promote_cloud_agent_identity_batch.py"),
        "helperSha256": _sha256(transaction / "tool/import_active_cloud_cpa_credential.py"),
    }
    base.atomic_json(transaction / "manifest.json", manifest)
    compile(_safe_bytes(transaction / "tool/promote_cloud_agent_identity_batch.py").decode("utf-8"), "recovery-tool", "exec")
    return transaction


def _attestation_copy(transaction: pathlib.Path, sidecar: Mapping[str, Any]) -> pathlib.Path:
    cliproxy = pwd.getpwnam("cliproxy")
    _private_directory(RUNTIME_ROOT, 0o755)
    active = RUNTIME_ROOT / transaction.name
    _private_directory(active, 0o750, 0, cliproxy.pw_gid)
    target = active / "capabilities.json"
    raw = (json.dumps(dict(sidecar), sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.chown(target, 0, cliproxy.pw_gid)
    target.chmod(0o440)
    return target


def _cleanup_attestation(path: Optional[pathlib.Path]) -> None:
    if path is None:
        return
    shutil.rmtree(path.parent, ignore_errors=True)
    try:
        RUNTIME_ROOT.rmdir()
    except OSError:
        pass


def _signed_import(
    raw: bytes,
    dry_run: bool,
    host: str,
    port: int,
    binary: pathlib.Path,
    attestation: pathlib.Path,
) -> Dict[str, Any]:
    cliproxy = pwd.getpwnam("cliproxy")
    command = [
        "sudo",
        "-n",
        "-u",
        cliproxy.pw_name,
        "env",
        "CLOUDX_AUTH_DIR=%s" % AUTH_DIR,
        "CLOUDX_IMPORT_LOCK=%s" % IMPORT_LOCK,
        "CLOUDX_GATEWAY_URL=http://%s:%d" % (host, port),
        "CLOUDX_CPA_BINARY=%s" % binary,
        "CLOUDX_CPA_CAPABILITY_MANIFEST=%s" % attestation,
        sys.executable,
        str(ACTIVE_ARTIFACT),
        "import",
    ]
    if dry_run:
        command.append("--dry-run")
    completed = base.run_command(command, input_bytes=raw, timeout=90.0)
    document = base.safe_json(completed.stdout)
    if completed.returncode != 0 or document.get("status") != "accepted":
        raise Rejected("import_rejected", "signed active importer rejected the Agent Identity batch")
    return document


def _agent_fingerprint(path: pathlib.Path) -> str:
    document = _json_file(path, 128 * 1024)
    forbidden = {
        "access_token", "refresh_token", "id_token", "token", "tokens",
        "task", "task_id", "agent_task", "agent_task_id",
    }
    runtime_id = document.get("agent_runtime_id")
    private_key = document.get("agent_private_key")
    if (
        str(document.get("auth_mode") or "").casefold() != "agentidentity"
        or document.get("type") != "codex"
        or document.get("auth_kind") != "oauth"
        or document.get("disabled") is not False
        or document.get("websockets") is not False
        or not isinstance(runtime_id, str)
        or not runtime_id.strip()
        or len(runtime_id) > 256
        or not isinstance(private_key, str)
        or any(key in document for key in forbidden)
    ):
        raise Rejected("target_invalid", "promoted Agent Identity record is invalid")
    try:
        der = base64.b64decode(private_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Rejected("target_invalid", "promoted Agent Identity record is invalid") from exc
    if len(der) != len(ED25519_PKCS8_PREFIX) + 32 or not der.startswith(ED25519_PKCS8_PREFIX):
        raise Rejected("target_invalid", "promoted Agent Identity record is invalid")
    return hashlib.sha256(runtime_id.strip().encode("utf-8") + b"\0" + der).hexdigest()


def _validate_promoted(
    paths: Sequence[pathlib.Path], expected: int, uid: int, gid: int
) -> Dict[str, str]:
    if len(paths) != expected:
        raise Rejected("target_mismatch", "active importer did not create the confirmed batch")
    _validate_active_files(paths, uid, gid)
    result = {path.name: _agent_fingerprint(path) for path in paths}
    if len(set(result.values())) != expected:
        raise Rejected("target_mismatch", "promoted Agent Identity records are not distinct")
    return result


def _hold_baseline(transaction: pathlib.Path, names: Sequence[str]) -> None:
    hold = transaction / "hold/active"
    for name in names:
        source = AUTH_DIR / name
        target = hold / name
        if not source.is_file() or source.is_symlink() or target.exists():
            raise Rejected("baseline_changed", "active baseline changed before cohort canary")
        if source.stat().st_dev != hold.stat().st_dev:
            raise Rejected("rollback_unavailable", "active baseline hold is not same-filesystem")
        os.replace(source, target)
    _fsync_directory(AUTH_DIR)
    _fsync_directory(hold)


def _restore_baseline(transaction: pathlib.Path, manifest: Mapping[str, Any]) -> None:
    uid = int(manifest["cliproxyUid"])
    gid = int(manifest["cliproxyGid"])
    for name, digest in dict(manifest.get("baselineActive") or {}).items():
        target = AUTH_DIR / name
        held = transaction / "hold/active" / name
        backup = transaction / "baseline/active" / name
        if target.is_file() and not target.is_symlink():
            _validate_active_files([target], uid, gid)
            continue
        source = held if held.is_file() and not held.is_symlink() else backup
        if not source.is_file() or source.is_symlink() or _sha256(source) != digest:
            raise Rejected("recovery_incomplete", "active baseline recovery source is unavailable")
        if source == backup:
            raw = _safe_bytes(source)
            descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        else:
            os.replace(source, target)
        target.chmod(0o600)
        os.chown(target, uid, gid)
    _fsync_directory(AUTH_DIR)


def _canaries(host: str, port: int, count: int) -> Dict[str, int]:
    attempts = 0
    for _unused in range(count):
        result = base.live_canary(host, port)
        if result.get("httpStatus") != 200 or result.get("policy") != "2":
            raise Rejected("live_model_failed", "active Agent Identity cohort canary failed")
        attempts += int(result.get("attempts") or 0)
    return {"requests": count, "attempts": attempts}


def _restore_promoted_archives(names: Sequence[str]) -> None:
    entries = _archive_entries()
    selectors = [
        str(entry.get("quarantine_name") or "")
        for entry in entries
        if str(entry.get("source_relative") or "") in names
    ]
    for selector in selectors:
        completed = base.run_command([
            sys.executable,
            str(ACTIVE_ARTIFACT),
            "cpa-health-restore",
            selector,
            "--confirm",
            selector,
            "--auth-dir",
            str(AUTH_DIR),
            "--archive-dir",
            str(ARCHIVE_DIR),
        ])
        document = base.safe_json(completed.stdout)
        if completed.returncode != 0 or document.get("status") != "restored":
            raise Rejected("recovery_incomplete", "promoted archived credential could not be contained")


def _move_promoted_failures(transaction: pathlib.Path, names: Sequence[str]) -> None:
    baseline = dict(_json_file(transaction / "manifest.json").get("failureMap") or {})
    for path in base.regular_files(FAILURE_DIR):
        if path.name in baseline:
            continue
        try:
            document = _json_file(path, 16 * 1024)
        except Rejected:
            continue
        if str(document.get("authFile") or "") in names:
            os.replace(path, transaction / "rollback/failure" / path.name)


def _remove_promoted(transaction: pathlib.Path, names: Sequence[str]) -> None:
    rollback = transaction / "rollback/active"
    for name in names:
        source = AUTH_DIR / name
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file() or (rollback / name).exists():
            raise Rejected("recovery_incomplete", "promoted credential recovery path is unsafe")
        os.replace(source, rollback / name)
    _fsync_directory(AUTH_DIR)
    _fsync_directory(rollback)


def _remove_transaction_trigger(transaction: pathlib.Path) -> None:
    trigger = SWEEP_DIR / "trigger.json"
    if trigger.is_file() and not trigger.is_symlink():
        target = transaction / "evidence" / "rollback-trigger.json"
        target.unlink(missing_ok=True)
        os.replace(trigger, target)


def _rollback(transaction: pathlib.Path, host: str, port: int, *, verify: bool) -> Dict[str, Any]:
    manifest = _json_file(transaction / "manifest.json")
    baseline_names = sorted(dict(manifest.get("baselineActive") or {}))
    promoted = sorted(dict(manifest.get("promoted") or {}))
    if not promoted:
        active_candidates = set(path.name for path in base.regular_json_files(AUTH_DIR)) - set(baseline_names)
        baseline_archive = list(manifest.get("archiveEntries") or [])
        archived_candidates = {
            str(entry.get("source_relative") or "")
            for entry in _archive_entries()
            if entry not in baseline_archive and isinstance(entry.get("source_relative"), str)
        }
        promoted = sorted((active_candidates | archived_candidates) - {""})
    _restore_baseline(transaction, manifest)
    _restore_promoted_archives(promoted)
    _remove_promoted(transaction, promoted)
    _move_promoted_failures(transaction, promoted)
    _remove_transaction_trigger(transaction)
    time.sleep(4.0)
    canary = _canaries(host, port, 1) if verify else {"requests": 0, "attempts": 0}
    active = base.regular_json_files(AUTH_DIR)
    service = base.service_state(CPA_SERVICE)
    restored = (
        sorted(path.name for path in active) == baseline_names
        and service == manifest.get("service")
        and len(_archive_entries()) == int(manifest.get("archiveCount") or -1)
        and _file_map(FAILURE_DIR) == dict(manifest.get("failureMap") or {})
    )
    base.require_available_pool_observation(SWEEP_DIR)
    if not restored:
        raise Rejected("recovery_incomplete", "active Agent Identity promotion baseline was not restored")
    manifest["phase"] = "recovered"
    manifest["recoveredAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["rawCredentialStored"] = False
    base.atomic_json(transaction / "manifest.json", manifest)
    result = {
        "schema": RESULT_SCHEMA,
        "status": "recovered",
        "transactionId": transaction.name,
        "activeRestored": len(active),
        "archiveRestored": len(_archive_entries()),
        "liveCanary": canary["requests"] == 1,
        "serviceRestarted": False,
        "rawCredentialStored": False,
    }
    base.atomic_json(transaction / "evidence/recovery.json", result)
    return result


def _apply(
    raw: bytes,
    expected_sha256: str,
    expected_active: int,
    expected_new: int,
    host: str,
    port: int,
) -> Dict[str, Any]:
    with _transaction_lock():
        baseline = _preflight(expected_active)
        transaction = _prepare_transaction(baseline, expected_sha256, expected_new)
        attestation: Optional[pathlib.Path] = None
        try:
            attestation = _attestation_copy(transaction, baseline["sidecar"])
            preview = _signed_import(raw, True, host, port, baseline["binary"], attestation)
            if (
                preview.get("requestHash") != expected_sha256
                or preview.get("written") != expected_new
                or preview.get("skipped") != 0
            ):
                raise Rejected("dry_run_mismatch", "active importer preview does not match the confirmed batch")
            imported = _signed_import(raw, False, host, port, baseline["binary"], attestation)
            if (
                imported.get("requestHash") != expected_sha256
                or imported.get("requestId") != preview.get("requestId")
                or imported.get("written") != expected_new
                or imported.get("skipped") != 0
            ):
                raise Rejected("apply_mismatch", "active importer result changed after preview")
            current = base.regular_json_files(AUTH_DIR)
            created = [path for path in current if path.name not in baseline["activeMap"]]
            promoted = _validate_promoted(
                created,
                expected_new,
                int(baseline["cliproxyUid"]),
                int(baseline["cliproxyGid"]),
            )
            manifest = _json_file(transaction / "manifest.json")
            manifest["phase"] = "imported"
            manifest["promoted"] = promoted
            base.atomic_json(transaction / "manifest.json", manifest)
            time.sleep(4.0)
            _hold_baseline(transaction, sorted(baseline["activeMap"]))
            try:
                time.sleep(5.0)
                cohort = _canaries(host, port, expected_new)
            finally:
                _restore_baseline(transaction, manifest)
            time.sleep(3.0)
            final_canary = _canaries(host, port, 1)
            repeated = _signed_import(raw, True, host, port, baseline["binary"], attestation)
            active = base.regular_json_files(AUTH_DIR)
            if (
                repeated.get("requestHash") != expected_sha256
                or repeated.get("written") != 0
                or repeated.get("skipped") != expected_new
                or len(active) != expected_active + expected_new
                or base.service_state(CPA_SERVICE) != baseline["service"]
                or len(_archive_entries()) != baseline["archiveCount"]
                or _file_map(FAILURE_DIR) != baseline["failureMap"]
            ):
                raise Rejected("acceptance_mismatch", "active Agent Identity promotion acceptance changed")
            base.require_available_pool_observation(SWEEP_DIR)
            receipt = {
                "schema": RESULT_SCHEMA,
                "status": "accepted",
                "transactionId": transaction.name,
                "requestHash": expected_sha256,
                "written": expected_new,
                "skipped": 0,
                "activeBefore": expected_active,
                "activeAfter": len(active),
                "distinctAgentIdentities": len(set(promoted.values())),
                "cohortCanaryRequests": cohort["requests"],
                "cohortCanaryAttempts": cohort["attempts"],
                "finalCanaryRequests": final_canary["requests"],
                "archiveEntries": baseline["archiveCount"],
                "failureInputs": 0,
                "sweepTrigger": False,
                "cpaPid": int(baseline["service"]["MainPID"]),
                "cpaRestarts": int(baseline["service"]["NRestarts"]),
                "serviceRestarted": False,
                "rawCredentialStored": False,
                "manualRecoveryConfirmation": recovery_confirmation(transaction.name),
            }
            manifest["phase"] = "accepted"
            manifest["acceptedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
            base.atomic_json(transaction / "manifest.json", manifest)
            base.atomic_json(transaction / "receipt.json", receipt)
            return receipt
        except Exception as exc:
            failure_code = exc.code if isinstance(exc, Rejected) else "transaction_error"
            recovered: Optional[Dict[str, Any]] = None
            try:
                recovered = _rollback(transaction, host, port, verify=True)
            except Rejected:
                recovered = None
            failure = {
                "schema": RESULT_SCHEMA,
                "status": "failed",
                "transactionId": transaction.name,
                "failureCode": failure_code,
                "baselineRestored": recovered is not None,
                "serviceRestarted": False,
                "rawCredentialStored": False,
            }
            base.atomic_json(transaction / "failure.json", failure)
            raise Rejected(
                failure_code,
                "active Agent Identity promotion failed and was contained" if recovered else "active Agent Identity promotion failed; manual recovery is required",
                result=failure,
            ) from exc
        finally:
            _cleanup_attestation(attestation)


def _recover_existing(transaction_id: str, host: str, port: int) -> Dict[str, Any]:
    transaction = TRANSACTION_ROOT / transaction_id
    if transaction.parent != TRANSACTION_ROOT or transaction.is_symlink() or not transaction.is_dir():
        raise Rejected("transaction_unavailable", "promotion transaction is unavailable")
    with _transaction_lock():
        return _rollback(transaction, host, port, verify=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--expected-request-sha256", default="")
    root.add_argument("--expected-active-before", type=int, default=0)
    root.add_argument("--expected-new", type=int, default=0)
    root.add_argument("--host", default="100.90.97.113")
    root.add_argument("--port", type=int, default=8317)
    root.add_argument("--recover", default="")
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    return root


def main(argv: Optional[Sequence[str]] = None, stream: Any = None) -> int:
    args = parser().parse_args(argv)
    if args.recover:
        document = recovery_plan(args.recover)
        if not args.apply:
            print(json.dumps(document, sort_keys=True))
            return 0
        if args.confirm != document["confirmation"]:
            raise Rejected("confirmation_mismatch", "promotion recovery confirmation does not match")
        print(json.dumps(_recover_existing(args.recover, args.host, args.port), sort_keys=True))
        return 0
    document = plan(args.expected_request_sha256, args.expected_active_before, args.expected_new)
    if not args.apply:
        print(json.dumps(document, sort_keys=True))
        return 0
    if args.confirm != document["confirmation"]:
        raise Rejected("confirmation_mismatch", "promotion confirmation does not match")
    raw = read_input(stream if stream is not None else sys.stdin.buffer, args.expected_request_sha256)
    print(json.dumps(_apply(
        raw,
        args.expected_request_sha256,
        args.expected_active_before,
        args.expected_new,
        args.host,
        args.port,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Rejected as exc:
        if exc.result is not None:
            print(json.dumps(exc.result, sort_keys=True))
        print("promote-cloud-agent-identity: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
