from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import cpa_auth, cpa_quota
from .public_metadata import emit_json, validate_public_document


DEFAULT_AUTH_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth")
DEFAULT_ARCHIVE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-archive")
DEFAULT_STATE_DIR = pathlib.Path("/var/lib/cloudx/cpa-health")
DEFAULT_FAILURE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-failures")
DEFAULT_WARNING_AVAILABLE_ACCOUNTS = 3
DEFAULT_FAILURE_CONFIRMATIONS = 3
FAILURE_RECEIPT_SCHEMA = "cloudx.cpa-auth-failure.v1"
MAX_FAILURE_RECEIPT_BYTES = 16 * 1024
MAX_FAILURE_RECEIPTS = 2048
MAX_FAILURE_RECEIPT_AGE_SECONDS = 30 * 60
MAX_FAILURE_RECEIPT_FUTURE_SKEW_SECONDS = 5 * 60
MIN_RUNTIME_FAILURE_CONFIRMATIONS = 2
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PERMANENT_RUNTIME_FAILURES = {
    "account_deactivated",
    "authentication_unauthorized",
    "missing_token",
    "refresh_invalid_grant",
    "refresh_token_reused",
    "refresh_token_revoked",
}


class CpaHealthUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CpaRuntime:
    quarantine: Callable[..., Dict[str, Any]]
    refresh: Callable[..., Dict[str, Any]]
    scan: Callable[..., List[Dict[str, Any]]]
    contexts: Callable[..., List[Dict[str, Any]]]
    payload_auth: Callable[..., Dict[str, Any]]
    probe: Callable[..., Optional[Dict[str, Any]]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def native_runtime() -> CpaRuntime:
    return CpaRuntime(
        quarantine=cpa_auth.quarantine_auth_record,
        refresh=cpa_auth.refresh_auth_accounts,
        scan=cpa_auth.scan_auth_records,
        contexts=cpa_auth.auth_contexts,
        payload_auth=cpa_auth.payload_auth,
        probe=cpa_quota.probe_account_quota_http,
    )


def cloudx_config(
    auth_dir: pathlib.Path,
    archive_dir: pathlib.Path,
    *,
    failure_confirmations: int,
) -> Dict[str, Any]:
    return {
        "cliproxy": {
            "account_name": "api",
            "auth_dir": str(auth_dir),
            "quarantine_dir": str(archive_dir),
            "failure_confirmations": max(1, failure_confirmations),
        }
    }


def probe_context(
    runtime: CpaRuntime,
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    state_key = str(context.get("state_key") or "account")
    payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
    auth = runtime.payload_auth(payload)
    if not isinstance(auth, dict):
        raise CpaHealthUnavailable("CPA runtime returned invalid auth context")
    return runtime.probe(
        config,
        {"name": state_key, "account": state_key},
        timeout_seconds=15,
        auth_override=auth,
        allow_auth_refresh=False,
    )


def summarize_probes(
    probes: List[Optional[Dict[str, Any]]],
    *,
    warning_available_accounts: int,
    checked_at: str,
) -> Dict[str, Any]:
    statuses = Counter(str((item or {}).get("status") or "unavailable") for item in probes)
    available = statuses["ready"] + statuses["warning"]
    limited = statuses["limited"]
    failed = len(probes) - available - limited
    reset_times = sorted(
        str(item.get("unavailable_until"))
        for item in probes
        if isinstance(item, dict) and item.get("unavailable_until")
    )
    remaining = [
        min(value for value in values if isinstance(value, int) and not isinstance(value, bool))
        for item in probes
        if isinstance(item, dict)
        and isinstance(item.get("remaining_percents"), list)
        and (values := item.get("remaining_percents"))
        and any(isinstance(value, int) and not isinstance(value, bool) for value in values)
    ]
    warning_threshold = max(1, warning_available_accounts)
    if not probes or failed == len(probes):
        state = "probe_error"
    elif available == 0 and limited > 0:
        state = "exhausted"
    elif available <= warning_threshold:
        state = "low_capacity"
    else:
        state = "healthy"
    return {
        "state": state,
        "checked_at": checked_at,
        "total": len(probes),
        "available": available,
        "ready": statuses["ready"],
        "warning": statuses["warning"],
        "limited": limited,
        "failed": failed,
        "zero_quota": sum(1 for value in remaining if value <= 0),
        "low_quota": sum(1 for value in remaining if 0 < value <= 10),
        "earliest_reset": reset_times[0] if reset_times else "",
    }


def probe_accounts(
    runtime: CpaRuntime,
    config: Dict[str, Any],
    *,
    warning_available_accounts: int,
    max_workers: int = 8,
) -> Tuple[Dict[str, Any], List[str]]:
    contexts = runtime.contexts(config, "api")
    if not isinstance(contexts, list) or any(not isinstance(item, dict) for item in contexts):
        raise CpaHealthUnavailable("CPA runtime returned invalid account contexts")
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(contexts)))) as pool:
        probes = list(pool.map(lambda context: probe_context(runtime, config, context), contexts))
    login_candidates: List[str] = []
    for context, item in zip(contexts, probes):
        if not isinstance(item, dict) or item.get("status") != "login":
            continue
        payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
        auth = runtime.payload_auth(payload)
        if not isinstance(auth, dict):
            raise CpaHealthUnavailable("CPA runtime returned invalid auth context")
        tokens = auth.get("tokens", {})
        if isinstance(tokens, dict) and not str(tokens.get("refresh_token") or "").strip():
            login_candidates.append(str(context.get("path") or ""))
    return (
        summarize_probes(
            probes,
            warning_available_accounts=warning_available_accounts,
            checked_at=utc_now().isoformat(),
        ),
        login_candidates,
    )


def load_state(path: pathlib.Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(path: pathlib.Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def archive_static_failures(
    runtime: CpaRuntime,
    config: Dict[str, Any],
    state_dir: pathlib.Path,
) -> List[str]:
    result = runtime.refresh(
        config,
        {"global_config_path": state_dir / "codexx-monitor.toml"},
        apply=True,
    )
    actions = result.get("actions") if isinstance(result, dict) else []
    if not isinstance(actions, list):
        actions = []
    return [
        pathlib.Path(str(action.get("moved_from") or "")).name
        for action in actions
        if isinstance(action, dict) and action.get("moved_from")
    ]


def archive_confirmed_login_failures(
    runtime: CpaRuntime,
    config: Dict[str, Any],
    login_candidates: List[str],
    previous: Dict[str, Any],
    *,
    confirmations: int,
) -> Tuple[List[str], Dict[str, Any]]:
    previous_candidates = previous.get("archive_candidates")
    if not isinstance(previous_candidates, dict):
        previous_candidates = {}
    scanned = runtime.scan(config)
    if not isinstance(scanned, list):
        raise CpaHealthUnavailable("CPA runtime returned invalid account records")
    records = {
        str(record.get("path") or ""): record
        for record in scanned
        if isinstance(record, dict)
    }
    now = utc_now().isoformat()
    next_candidates: Dict[str, Any] = {}
    archived: List[str] = []
    for path in sorted(set(login_candidates)):
        record = records.get(path)
        if not record or not pathlib.Path(path).is_file():
            continue
        old = previous_candidates.get(path)
        old_count = int(old.get("failure_count") or 0) if isinstance(old, dict) else 0
        failure_count = old_count + 1
        if failure_count < confirmations:
            next_candidates[path] = {
                "failure_count": failure_count,
                "last_reason": "usage-endpoint-login-without-refresh-token",
                "last_failed_at": now,
            }
            continue
        moved = runtime.quarantine(
            config,
            record,
            reason="confirmed-login-failure-without-refresh-token",
            moved_at=now,
        )
        archived.append(pathlib.Path(str(moved.get("moved_from") or path)).name)
    return archived, next_candidates


def _safe_file_bytes(path: pathlib.Path, maximum: int) -> Optional[bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            return None
        chunks: List[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        return raw if len(raw) <= maximum else None
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _sha256(path: pathlib.Path) -> str:
    raw = _safe_file_bytes(path, cpa_auth.MAX_AUTH_FILE_BYTES)
    if raw is None:
        raise OSError("unsafe CPA auth file")
    return hashlib.sha256(raw).hexdigest()


def _failure_receipt(path: pathlib.Path, *, now: datetime) -> Optional[Dict[str, Any]]:
    raw = _safe_file_bytes(path, MAX_FAILURE_RECEIPT_BYTES)
    if raw is None:
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if len(raw) > MAX_FAILURE_RECEIPT_BYTES or not isinstance(document, dict):
        return None
    observed = _parse_receipt_time(document.get("observedAt"))
    auth_file = str(document.get("authFile") or "")
    digest = str(document.get("authSha256") or "")
    reason = str(document.get("reason") or "")
    failure_count = document.get("failureCount")
    if (
        document.get("schema") != FAILURE_RECEIPT_SCHEMA
        or pathlib.Path(auth_file).name != auth_file
        or not auth_file.endswith(".json")
        or not SHA256_RE.fullmatch(digest)
        or reason not in PERMANENT_RUNTIME_FAILURES
        or document.get("permanentAuthFailure") is not True
        or document.get("weeklyQuota") is not False
        or not isinstance(failure_count, int)
        or isinstance(failure_count, bool)
        or failure_count < MIN_RUNTIME_FAILURE_CONFIRMATIONS
        or observed is None
    ):
        return None
    age = (now - observed.astimezone(timezone.utc)).total_seconds()
    if age < -MAX_FAILURE_RECEIPT_FUTURE_SKEW_SECONDS or age > MAX_FAILURE_RECEIPT_AGE_SECONDS:
        return None
    return {
        "auth_file": auth_file,
        "auth_sha256": digest,
        "reason": reason,
    }


def _parse_receipt_time(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def archive_runtime_failures(
    runtime: CpaRuntime,
    config: Dict[str, Any],
    failure_dir: pathlib.Path,
) -> Tuple[List[str], int, int]:
    if not failure_dir.is_dir() or failure_dir.is_symlink():
        return [], 0, 0
    scanned = runtime.scan(config)
    if not isinstance(scanned, list) or any(not isinstance(item, dict) for item in scanned):
        raise CpaHealthUnavailable("CPA runtime returned invalid account records")
    records: Dict[str, List[Dict[str, Any]]] = {}
    for record in scanned:
        path = pathlib.Path(str(record.get("path") or ""))
        if path.name and path.parent == pathlib.Path(config["cliproxy"]["auth_dir"]):
            records.setdefault(path.name, []).append(record)
    now = utc_now()
    archived: List[str] = []
    rejected = 0
    stale = 0
    for index, receipt_path in enumerate(sorted(failure_dir.glob("*.json"))):
        if index >= MAX_FAILURE_RECEIPTS:
            rejected += 1
            continue
        receipt = _failure_receipt(receipt_path, now=now)
        if receipt is None:
            rejected += 1
            continue
        matches = records.get(receipt["auth_file"], [])
        if len(matches) != 1:
            stale += 1
            continue
        record = matches[0]
        auth_path = pathlib.Path(str(record.get("path") or ""))
        try:
            digest = _sha256(auth_path)
        except OSError:
            stale += 1
            continue
        if digest != receipt["auth_sha256"]:
            stale += 1
            continue
        moved = runtime.quarantine(
            config,
            record,
            reason="runtime-%s" % receipt["reason"],
            moved_at=now.isoformat(),
        )
        archived.append(pathlib.Path(str(moved.get("moved_from") or auth_path)).name)
        try:
            receipt_path.unlink()
        except OSError:
            pass
    return archived, rejected, stale


def public_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        key: value
        for key, value in summary.items()
        if key not in {"archive_candidates", "archived_files"}
    }
    archived = summary.get("archived_files")
    candidates = summary.get("archive_candidates")
    result["archived_count"] = len(archived) if isinstance(archived, list) else 0
    result["pending_archive_candidates"] = len(candidates) if isinstance(candidates, dict) else 0
    return validate_public_document(result, "cloudx.cpa-health.v1 summary")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check", action="store_true", help="probe only; do not write state or isolate accounts")
    parser.add_argument("--auth-dir", type=pathlib.Path, default=DEFAULT_AUTH_DIR)
    parser.add_argument("--archive-dir", type=pathlib.Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--state-dir", type=pathlib.Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--failure-dir", type=pathlib.Path, default=DEFAULT_FAILURE_DIR)
    parser.add_argument(
        "--warning-available-accounts",
        type=int,
        default=int(
            os.environ.get(
                "CLOUDX_WARNING_AVAILABLE_ACCOUNTS",
                str(DEFAULT_WARNING_AVAILABLE_ACCOUNTS),
            )
        ),
    )
    parser.add_argument(
        "--failure-confirmations",
        type=int,
        default=int(
            os.environ.get("CLOUDX_FAILURE_CONFIRMATIONS", str(DEFAULT_FAILURE_CONFIRMATIONS))
        ),
    )


def add_restore_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("selector", help="exact quarantined filename")
    parser.add_argument("--confirm", required=True, help="repeat the exact quarantined filename")
    parser.add_argument("--auth-dir", type=pathlib.Path, default=DEFAULT_AUTH_DIR)
    parser.add_argument("--archive-dir", type=pathlib.Path, default=DEFAULT_ARCHIVE_DIR)


def run(args: argparse.Namespace, runtime: Optional[CpaRuntime] = None) -> int:
    active_runtime = runtime or native_runtime()
    config = cloudx_config(
        args.auth_dir,
        args.archive_dir,
        failure_confirmations=args.failure_confirmations,
    )
    if args.check:
        summary, unused_candidates = probe_accounts(
            active_runtime,
            config,
            warning_available_accounts=args.warning_available_accounts,
        )
        emit_json(public_summary(summary), ensure_ascii=False)
        return 0

    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.state_dir.chmod(0o700)
    state_path = args.state_dir / "state.json"
    lock_path = args.state_dir / "monitor.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        previous = load_state(state_path)
        static_archived = archive_static_failures(active_runtime, config, args.state_dir)
        runtime_archived, rejected_receipts, stale_receipts = archive_runtime_failures(
            active_runtime,
            config,
            args.failure_dir,
        )
        summary, login_candidates = probe_accounts(
            active_runtime,
            config,
            warning_available_accounts=args.warning_available_accounts,
        )
        live_archived, archive_candidates = archive_confirmed_login_failures(
            active_runtime,
            config,
            login_candidates,
            previous,
            confirmations=max(1, args.failure_confirmations),
        )
        summary["archived_files"] = sorted(set(static_archived + runtime_archived + live_archived))
        summary["archive_candidates"] = archive_candidates
        summary["runtime_failure_archived_count"] = len(runtime_archived)
        summary["rejected_failure_receipts"] = rejected_receipts
        summary["stale_failure_receipts"] = stale_receipts
        save_state(state_path, summary)
        emit_json(public_summary(summary), ensure_ascii=False)
    return 0


def restore_run(args: argparse.Namespace) -> int:
    if args.confirm != args.selector:
        raise CpaHealthUnavailable("CPA restore confirmation does not match")
    config = cloudx_config(args.auth_dir, args.archive_dir, failure_confirmations=1)
    cpa_auth.restore_quarantined_auth(config, args.selector)
    emit_json({
        "schema": "cloudx.cpa-quarantine-restore.v1",
        "status": "restored",
        "restored_count": 1,
    }, ensure_ascii=False)
    return 0
