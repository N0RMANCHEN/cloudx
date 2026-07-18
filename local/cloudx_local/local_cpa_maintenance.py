from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import LocalConfig
from .files import atomic_json, ensure_private_directory
from .local_cpa_import import _auth_dir, _auth_tokens, _decode_jwt_payload, _iso_from_epoch


FAILURE_SCHEMA = "cloudx.cpa-auth-failure.v1"
RESULT_SCHEMA = "cloudx.local-cpa-maintenance.v1"
MANIFEST_SCHEMA = "cloudx.local-cpa-archive.v1"
MAX_AUTH_FILE_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_AGE_SECONDS = 30 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60
MIN_FAILURE_CONFIRMATIONS = 2
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PERMANENT_FAILURE_REASONS = {
    "account_deactivated",
    "authentication_unauthorized",
    "missing_token",
    "refresh_invalid_grant",
    "refresh_token_reused",
    "refresh_token_revoked",
}


class LocalCpaMaintenanceRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthRecord:
    path: pathlib.Path
    digest: str
    static_reason: str = ""


@dataclass(frozen=True)
class ArchiveCandidate:
    record: AuthRecord
    reason: str
    receipt: Optional[pathlib.Path] = None


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    return _sha256_bytes(_safe_regular_file(path, MAX_AUTH_FILE_BYTES))


def _parse_time(raw: object) -> Optional[datetime]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _auth_expiry(document: Dict[str, Any], access_token: str, id_token: str) -> Optional[datetime]:
    raw = (
        document.get("expired")
        or document.get("expiry")
        or document.get("auth_expires_at")
        or document.get("expires_at")
        or _iso_from_epoch(_decode_jwt_payload(access_token).get("exp"))
        or _iso_from_epoch(_decode_jwt_payload(id_token).get("exp"))
    )
    return _parse_time(raw)


def _safe_regular_file(path: pathlib.Path, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise LocalCpaMaintenanceRejected("CPA auth file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise LocalCpaMaintenanceRejected("CPA auth file is unsafe")
        if info.st_size > maximum:
            raise LocalCpaMaintenanceRejected("CPA auth file is too large")
        chunks: List[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise LocalCpaMaintenanceRejected("CPA auth file is too large")
        return raw
    except OSError as exc:
        raise LocalCpaMaintenanceRejected("CPA auth file is unreadable") from exc
    finally:
        os.close(descriptor)


def _record(path: pathlib.Path, *, now: datetime) -> Optional[AuthRecord]:
    try:
        raw = _safe_regular_file(path, MAX_AUTH_FILE_BYTES)
    except LocalCpaMaintenanceRejected:
        return None
    digest = _sha256_bytes(raw)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return AuthRecord(path=path, digest=digest, static_reason="invalid-auth-json")
    if not isinstance(document, dict):
        return AuthRecord(path=path, digest=digest, static_reason="invalid-auth-json")
    provider = str(document.get("type") or document.get("provider") or "").strip().casefold()
    if provider and provider not in {"codex", "chatgpt", "openai"}:
        return None
    access_token, refresh_token, id_token = _auth_tokens(document)
    if not any((access_token, refresh_token, id_token)):
        return AuthRecord(path=path, digest=digest, static_reason="missing-refresh-and-access-token")
    expiry = _auth_expiry(document, access_token, id_token)
    if expiry is not None and expiry <= now and not refresh_token:
        return AuthRecord(path=path, digest=digest, static_reason="expired-without-refresh-token")
    return AuthRecord(path=path, digest=digest)


def scan_active_auth(auth_dir: pathlib.Path, *, now: Optional[datetime] = None) -> Dict[str, AuthRecord]:
    current = now or datetime.now(timezone.utc)
    if not auth_dir.is_dir() or auth_dir.is_symlink():
        return {}
    result: Dict[str, AuthRecord] = {}
    for path in sorted(auth_dir.glob("*.json")):
        record = _record(path, now=current)
        if record is not None:
            result[path.name] = record
    return result


def _configured_archive_dir(config: LocalConfig, auth_dir: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(config.local_cpa_archive_dir or auth_dir.with_name(auth_dir.name + "-archive")).expanduser()
    if not path.is_absolute():
        raise LocalCpaMaintenanceRejected("local CPA archive directory must be absolute")
    resolved_auth = auth_dir.resolve(strict=False)
    resolved_archive = path.resolve(strict=False)
    if resolved_archive == resolved_auth:
        raise LocalCpaMaintenanceRejected("local CPA archive directory must differ from auth directory")
    try:
        resolved_archive.relative_to(resolved_auth)
    except ValueError:
        pass
    else:
        raise LocalCpaMaintenanceRejected("local CPA archive directory cannot be inside auth directory")
    return path


def _configured_failure_dir(config: LocalConfig) -> pathlib.Path:
    path = pathlib.Path(config.local_cpa_failure_dir or config.state_dir / "cpa-auth-failures").expanduser()
    if not path.is_absolute():
        raise LocalCpaMaintenanceRejected("local CPA failure directory must be absolute")
    return path


def _receipt(path: pathlib.Path, *, now: datetime) -> Optional[Dict[str, Any]]:
    try:
        raw = _safe_regular_file(path, MAX_RECEIPT_BYTES)
        document = json.loads(raw.decode("utf-8"))
    except (LocalCpaMaintenanceRejected, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or document.get("schema") != FAILURE_SCHEMA:
        return None
    auth_file = str(document.get("authFile") or "")
    if pathlib.Path(auth_file).name != auth_file or not auth_file.endswith(".json"):
        return None
    digest = str(document.get("authSha256") or "")
    reason = str(document.get("reason") or "")
    observed = _parse_time(document.get("observedAt"))
    failure_count = document.get("failureCount")
    if (
        not SHA256_RE.fullmatch(digest)
        or reason not in PERMANENT_FAILURE_REASONS
        or document.get("permanentAuthFailure") is not True
        or document.get("weeklyQuota") is not False
        or not isinstance(failure_count, int)
        or isinstance(failure_count, bool)
        or failure_count < MIN_FAILURE_CONFIRMATIONS
        or observed is None
    ):
        return None
    age = (now - observed.astimezone(timezone.utc)).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > MAX_RECEIPT_AGE_SECONDS:
        return None
    return {
        "authFile": auth_file,
        "authSha256": digest,
        "reason": reason,
    }


def runtime_candidates(
    failure_dir: pathlib.Path,
    records: Dict[str, AuthRecord],
    *,
    now: Optional[datetime] = None,
) -> Tuple[List[ArchiveCandidate], int, int]:
    current = now or datetime.now(timezone.utc)
    if not failure_dir.is_dir() or failure_dir.is_symlink():
        return [], 0, 0
    candidates: List[ArchiveCandidate] = []
    rejected = 0
    stale = 0
    for path in sorted(failure_dir.glob("*.json")):
        document = _receipt(path, now=current)
        if document is None:
            rejected += 1
            continue
        record = records.get(document["authFile"])
        if record is None or record.digest != document["authSha256"]:
            stale += 1
            continue
        candidates.append(
            ArchiveCandidate(
                record=record,
                reason="runtime-%s" % document["reason"],
                receipt=path,
            )
        )
    return candidates, rejected, stale


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _manifest(path: pathlib.Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    try:
        document = json.loads(_safe_regular_file(path, MAX_MANIFEST_BYTES).decode("utf-8"))
    except (LocalCpaMaintenanceRejected, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalCpaMaintenanceRejected("local CPA archive manifest is invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != MANIFEST_SCHEMA
        or not isinstance(document.get("entries"), list)
    ):
        raise LocalCpaMaintenanceRejected("local CPA archive manifest is invalid")
    return document


def _unique_target(archive_dir: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    target = archive_dir / source.name
    if target.name not in {"manifest.json", ".archive.lock"} and not target.exists():
        return target
    index = 2
    while True:
        candidate = archive_dir / ("%s.%d%s" % (source.stem, index, source.suffix))
        if not candidate.exists():
            return candidate
        index += 1


def archive_candidates(
    archive_dir: pathlib.Path,
    candidates: Sequence[ArchiveCandidate],
    *,
    moved_at: str,
) -> int:
    if not candidates:
        return 0
    ensure_private_directory(archive_dir)
    archive_dir.chmod(0o700)
    lock_path = archive_dir / ".archive.lock"
    moved: List[Tuple[pathlib.Path, pathlib.Path]] = []
    with lock_path.open("a+", encoding="utf-8") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if candidates[0].record.path.parent.stat().st_dev != archive_dir.stat().st_dev:
            raise LocalCpaMaintenanceRejected("local CPA archive requires one filesystem")
        manifest_path = archive_dir / "manifest.json"
        document = _manifest(manifest_path)
        selected: List[Tuple[ArchiveCandidate, pathlib.Path]] = []
        for candidate in candidates:
            source = candidate.record.path
            if not source.is_file() or source.is_symlink():
                continue
            if _sha256_file(source) != candidate.record.digest:
                continue
            selected.append((candidate, _unique_target(archive_dir, source)))
        try:
            for candidate, target in selected:
                source = candidate.record.path
                os.replace(str(source), str(target))
                target.chmod(0o600)
                moved.append((source, target))
                document["entries"].append({
                    "sourceName": source.name,
                    "archiveName": target.name,
                    "reason": candidate.reason,
                    "movedAt": moved_at,
                    "authSha256": candidate.record.digest,
                })
            atomic_json(manifest_path, document, mode=0o600)
            _fsync_directory(archive_dir)
            _fsync_directory(candidates[0].record.path.parent)
        except Exception as exc:
            rollback_failed = False
            for source, target in reversed(moved):
                try:
                    if not source.exists() and target.is_file():
                        os.replace(str(target), str(source))
                except OSError:
                    rollback_failed = True
            if rollback_failed:
                raise LocalCpaMaintenanceRejected("local CPA archive failed and rollback was incomplete") from exc
            if isinstance(exc, LocalCpaMaintenanceRejected):
                raise
            raise LocalCpaMaintenanceRejected("local CPA archive transaction failed; credentials were restored") from exc
    archived_names = {target.name for unused_source, target in moved}
    for candidate, target in selected:
        if target.name in archived_names and candidate.receipt is not None:
            try:
                candidate.receipt.unlink()
            except OSError:
                pass
    return len(moved)


def refresh_document(config: LocalConfig, *, apply: bool) -> Dict[str, Any]:
    auth_dir = _auth_dir(config)
    archive_dir = _configured_archive_dir(config, auth_dir)
    failure_dir = _configured_failure_dir(config)
    now = datetime.now(timezone.utc)
    records = scan_active_auth(auth_dir, now=now)
    static = [
        ArchiveCandidate(record=record, reason=record.static_reason)
        for record in records.values()
        if record.static_reason
    ]
    runtime, rejected, stale = runtime_candidates(failure_dir, records, now=now)
    by_name: Dict[str, ArchiveCandidate] = {item.record.path.name: item for item in runtime}
    for item in static:
        by_name[item.record.path.name] = item
    candidates = [by_name[name] for name in sorted(by_name)]
    archived = archive_candidates(archive_dir, candidates, moved_at=now.isoformat()) if apply else 0
    return {
        "schema": RESULT_SCHEMA,
        "status": "accepted",
        "mode": "apply" if apply else "dry-run",
        "activeAuthFiles": len(records),
        "eligibleForArchive": len(candidates),
        "archived": archived,
        "rejectedFailureReceipts": rejected,
        "staleFailureReceipts": stale,
        "weeklyQuotaArchived": 0,
        "nestedAuthDirectoriesScanned": 0,
        "externalService": {"managed": False, "restarted": False},
    }


def refresh_run(config: LocalConfig, argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="codexx api refresh")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    document = refresh_document(config, apply=bool(args.apply))
    print(json.dumps(document, sort_keys=True))
    return 0


def restore_run(config: LocalConfig, argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="codexx api restore")
    parser.add_argument("selector")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(list(argv))
    if args.confirm != args.selector or pathlib.Path(args.selector).name != args.selector:
        raise LocalCpaMaintenanceRejected("local CPA restore confirmation does not match")
    auth_dir = _auth_dir(config)
    archive_dir = _configured_archive_dir(config, auth_dir)
    if not archive_dir.is_dir() or archive_dir.is_symlink():
        raise LocalCpaMaintenanceRejected("local CPA archive directory is unavailable")
    if not auth_dir.is_dir() or auth_dir.is_symlink():
        raise LocalCpaMaintenanceRejected("local CPA auth directory is unavailable")
    manifest_path = archive_dir / "manifest.json"
    lock_path = archive_dir / ".archive.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document = _manifest(manifest_path)
        matches = [
            (index, entry)
            for index, entry in enumerate(document["entries"])
            if isinstance(entry, dict) and entry.get("archiveName") == args.selector
        ]
        if len(matches) != 1:
            raise LocalCpaMaintenanceRejected("local CPA restore selector did not match exactly one entry")
        index, entry = matches[0]
        archive_name = str(entry.get("archiveName") or "")
        source_name = str(entry.get("sourceName") or "")
        if (
            pathlib.Path(archive_name).name != archive_name
            or pathlib.Path(source_name).name != source_name
            or not archive_name.endswith(".json")
            or not source_name.endswith(".json")
        ):
            raise LocalCpaMaintenanceRejected("local CPA restore manifest paths are invalid")
        source = archive_dir / archive_name
        target = auth_dir / source_name
        if source.is_symlink() or not source.is_file() or target.exists() or target.parent != auth_dir:
            raise LocalCpaMaintenanceRejected("local CPA restore paths are unavailable")
        if source.stat().st_dev != auth_dir.stat().st_dev:
            raise LocalCpaMaintenanceRejected("local CPA restore requires one filesystem")
        try:
            os.replace(str(source), str(target))
        except OSError as exc:
            raise LocalCpaMaintenanceRejected("local CPA restore move failed") from exc
        target.chmod(0o600)
        document["entries"].pop(index)
        try:
            atomic_json(manifest_path, document, mode=0o600)
        except Exception as exc:
            os.replace(str(target), str(source))
            raise LocalCpaMaintenanceRejected("local CPA restore manifest failed; credential remained archived") from exc
    print(json.dumps({"schema": RESULT_SCHEMA, "status": "restored", "restored": 1}, sort_keys=True))
    return 0
