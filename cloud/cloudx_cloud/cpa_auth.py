from __future__ import annotations

import base64
import fcntl
import json
import os
import pathlib
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import agent_identity


MAX_AUTH_FILE_BYTES = 1024 * 1024
MAX_AUTH_FILES = 4096
MAX_MANIFEST_BYTES = 1024 * 1024
MANIFEST_SCHEMA = "cloudx.cpa-quarantine.v1"


class CpaAuthRejected(RuntimeError):
    pass


def _cliproxy(config: Dict[str, Any]) -> Dict[str, Any]:
    value = config.get("cliproxy")
    return value if isinstance(value, dict) else {}


def _configured_path(config: Dict[str, Any], key: str) -> pathlib.Path:
    raw = str(_cliproxy(config).get(key) or "").strip()
    path = pathlib.Path(raw)
    if not raw or not path.is_absolute():
        raise CpaAuthRejected("CPA credential path is not configured safely")
    return path


def configured_auth_dir(config: Dict[str, Any]) -> pathlib.Path:
    return _configured_path(config, "auth_dir")


def configured_archive_dir(config: Dict[str, Any]) -> pathlib.Path:
    return _configured_path(config, "quarantine_dir")


def failure_confirmations(config: Dict[str, Any]) -> int:
    raw = _cliproxy(config).get("failure_confirmations")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3


def _ensure_real_directory(path: pathlib.Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        info = path.lstat()
    except OSError as exc:
        raise CpaAuthRejected("CPA credential directory is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CpaAuthRejected("CPA credential directory is unsafe")


def _iter_json_files(root: pathlib.Path) -> Iterator[pathlib.Path]:
    if not root.exists():
        return
    _ensure_real_directory(root)
    count = 0
    for base, directory_names, file_names in os.walk(str(root), topdown=True, followlinks=False):
        base_path = pathlib.Path(base)
        safe_directories: List[str] = []
        for name in sorted(directory_names):
            candidate = base_path / name
            try:
                info = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in sorted(file_names):
            if not name.lower().endswith(".json"):
                continue
            count += 1
            if count > MAX_AUTH_FILES:
                raise CpaAuthRejected("CPA credential file count exceeds the safety limit")
            yield base_path / name


def read_auth_json(path: pathlib.Path) -> Tuple[Dict[str, Any], str]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return {}, "auth-file-unreadable"
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return {}, "auth-file-not-regular"
        if info.st_size > MAX_AUTH_FILE_BYTES:
            return {}, "auth-file-too-large"
        chunks: List[bytes] = []
        remaining = MAX_AUTH_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_AUTH_FILE_BYTES:
            return {}, "auth-file-too-large"
    except OSError:
        return {}, "auth-file-unreadable"
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, "invalid-auth-json"
    if not isinstance(payload, dict):
        return {}, "auth-json-not-object"
    return payload, ""


def auth_tokens(data: Dict[str, Any]) -> Tuple[str, str, str]:
    token = data.get("token") if isinstance(data.get("token"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    access_token = str(
        data.get("access_token")
        or token.get("access_token")
        or tokens.get("access_token")
        or ""
    ).strip()
    refresh_token = str(
        data.get("refresh_token")
        or token.get("refresh_token")
        or tokens.get("refresh_token")
        or ""
    ).strip()
    id_token = str(
        data.get("id_token")
        or token.get("id_token")
        or tokens.get("id_token")
        or ""
    ).strip()
    return access_token, refresh_token, id_token


def auth_account_id(data: Dict[str, Any]) -> str:
    token = data.get("token") if isinstance(data.get("token"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    return str(
        data.get("account_id")
        or data.get("chatgpt_account_id")
        or token.get("account_id")
        or tokens.get("account_id")
        or ""
    ).strip()


def _sub2api_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    credentials = entry.get("credentials")
    if not isinstance(credentials, dict) or not credentials:
        return {}
    payload = dict(credentials)
    if payload.get("expires_at") and not payload.get("auth_expires_at"):
        payload["auth_expires_at"] = payload.pop("expires_at")
    for key in (
        "name",
        "platform",
        "type",
        "extra",
        "concurrency",
        "priority",
        "rate_multiplier",
        "auto_pause_on_expired",
    ):
        if key in entry and key not in payload:
            payload[key] = entry[key]
    if payload.get("chatgpt_account_id") and not payload.get("account_id"):
        payload["account_id"] = payload.get("chatgpt_account_id")
    if payload.get("name") and not payload.get("label"):
        payload["label"] = payload.get("name")
    if not payload.get("email"):
        name = str(entry.get("name") or "").strip()
        if "@" in name:
            payload["email"] = name
    return payload


def payload_records(
    source: pathlib.Path,
    data: Dict[str, Any],
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    accounts = data.get("accounts")
    records: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    if isinstance(accounts, list):
        for index, entry in enumerate(accounts, start=1):
            if not isinstance(entry, dict):
                continue
            payload = _sub2api_payload(entry)
            access_token, refresh_token, id_token = auth_tokens(payload)
            if not any((access_token, refresh_token, id_token)):
                continue
            name = str(entry.get("name") or payload.get("email") or "account-%d" % index).strip()
            records.append(({
                "path": str(source),
                "name": name,
                "type": "codex",
                "label": name,
                "email": str(payload.get("email") or "").strip(),
                "account_id": auth_account_id(payload),
                "bundle_account": name,
                "source": "sub2api",
                "codexx_account": "",
                "disabled": False,
                "has_access_token": bool(access_token),
                "has_refresh_token": bool(refresh_token),
                "has_id_token": bool(id_token),
                "expires_at": str(payload.get("auth_expires_at") or "").strip(),
                "status": "active",
                "reason": "",
            }, payload))
    if records:
        return records

    access_token, refresh_token, id_token = auth_tokens(data)
    if not any((access_token, refresh_token, id_token)):
        return []
    name = str(
        data.get("codexx_account")
        or data.get("label")
        or data.get("email")
        or data.get("user_email")
        or source.stem
    ).strip()
    return [({
        "path": str(source),
        "name": name,
        "type": str(data.get("type") or "codex"),
        "label": str(data.get("label") or ""),
        "email": str(data.get("email") or data.get("user_email") or ""),
        "account_id": auth_account_id(data),
        "source": str(data.get("source") or ""),
        "codexx_account": str(data.get("codexx_account") or ""),
        "disabled": bool(data.get("disabled")),
        "has_access_token": bool(access_token),
        "has_refresh_token": bool(refresh_token),
        "has_id_token": bool(id_token),
        "expires_at": str(
            data.get("expired")
            or data.get("expiry")
            or data.get("auth_expires_at")
            or ""
        ).strip(),
        "status": "active",
        "reason": "",
    }, data)]


def payload_auth(payload: Dict[str, Any]) -> Dict[str, Any]:
    access_token, refresh_token, id_token = auth_tokens(payload)
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "account_id": auth_account_id(payload),
    }
    auth: Dict[str, Any] = {
        "auth_mode": "chatgpt",
        "tokens": {key: value for key, value in tokens.items() if value},
    }
    for key in ("email", "user_email", "last_refresh", "plan_label", "renews_at", "plan_expires_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            auth[key] = value.strip()
    return auth


def auth_contexts(config: Dict[str, Any], proxy_account: str) -> List[Dict[str, Any]]:
    configured_account = str(_cliproxy(config).get("account_name") or "api").strip() or "api"
    if proxy_account and proxy_account != configured_account:
        return []
    auth_dir = configured_auth_dir(config)
    contexts: List[Dict[str, Any]] = []
    for path in _iter_json_files(auth_dir):
        data, error = read_auth_json(path)
        if error:
            continue
        for index, (record, payload) in enumerate(payload_records(path, data), start=1):
            selector = str(record.get("bundle_account") or record.get("name") or index)
            try:
                relative = path.relative_to(auth_dir).as_posix()
            except ValueError:
                continue
            contexts.append({
                "proxy_account": configured_account,
                "state_key": "cliproxy:%s:%s#%s" % (configured_account, relative, selector),
                "path": path,
                "record": record,
                "payload": payload,
            })
    return sorted(contexts, key=lambda item: str(item.get("state_key") or ""))


def _decode_jwt_payload(token: object) -> Dict[str, Any]:
    if not isinstance(token, str) or token.count(".") < 2:
        return {}
    try:
        encoded = token.split(".", 2)[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_from_epoch(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def scan_auth_records(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    auth_dir = configured_auth_dir(config)
    records: List[Dict[str, Any]] = []
    for path in _iter_json_files(auth_dir):
        data, error = read_auth_json(path)
        if error:
            records.append({
                "path": str(path),
                "name": path.stem,
                "type": "-",
                "status": "invalid",
                "reason": error,
            })
            continue
        bundled = payload_records(path, data) if isinstance(data.get("accounts"), list) else []
        if bundled:
            records.extend(record for record, unused_payload in bundled)
            continue
        auth_type = str(data.get("type") or data.get("provider") or "").strip().lower()
        if auth_type and auth_type != "codex":
            continue
        agent_identity_mode = agent_identity.is_agent_identity(data)
        valid_agent_identity = agent_identity.is_valid(data) if agent_identity_mode else False
        if agent_identity_mode and not valid_agent_identity:
            records.append({
                "path": str(path),
                "name": path.stem,
                "type": auth_type or "codex",
                "status": "invalid",
                "reason": "invalid-agent-identity",
            })
            continue
        access_token, refresh_token, id_token = auth_tokens(data)
        if not (auth_type == "codex" or data.get("codexx_account") or access_token or refresh_token or id_token):
            continue
        expires_at = str(
            data.get("expired")
            or data.get("expiry")
            or data.get("auth_expires_at")
            or ""
        ).strip()
        if not expires_at:
            expires_at = (
                _iso_from_epoch(_decode_jwt_payload(access_token).get("exp"))
                or _iso_from_epoch(_decode_jwt_payload(id_token).get("exp"))
            )
        records.append({
            "path": str(path),
            "name": str(data.get("codexx_account") or data.get("label") or path.stem),
            "type": auth_type or "codex",
            "label": str(data.get("label") or ""),
            "source": str(data.get("source") or ""),
            "codexx_account": str(data.get("codexx_account") or ""),
            "disabled": bool(data.get("disabled")),
            "has_access_token": bool(access_token),
            "has_refresh_token": bool(refresh_token),
            "has_id_token": bool(id_token),
            "has_agent_identity": valid_agent_identity,
            "expires_at": expires_at,
            "status": "active",
            "reason": "",
        })

    def rank(record: Dict[str, Any]) -> Tuple[int, str]:
        path = pathlib.Path(str(record.get("path") or ""))
        try:
            depth = len(path.relative_to(auth_dir).parts)
        except ValueError:
            depth = 999
        return depth, str(path)

    deduped: Dict[str, Dict[str, Any]] = {}
    for record in sorted(records, key=rank):
        account = str(record.get("codexx_account") or "").strip()
        key = "codexx:%s" % account if account else str(record.get("path") or "")
        if key not in deduped:
            deduped[key] = record
    return sorted(deduped.values(), key=lambda record: str(record.get("path") or ""))


def _parse_time(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def static_failure_reason(record: Dict[str, Any]) -> Tuple[str, bool]:
    if record.get("status") == "invalid":
        return str(record.get("reason") or "invalid-auth-json"), True
    if bool(record.get("disabled")):
        return "disabled", False
    if bool(record.get("has_agent_identity")):
        return "unknown", False
    if not record.get("has_access_token") and not record.get("has_refresh_token"):
        return "missing-refresh-and-access-token", True
    expires_at = _parse_time(record.get("expires_at"))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc) and not record.get("has_refresh_token"):
        return "expired-without-refresh-token", True
    return "unknown", False


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(str(temporary), str(path))
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _read_private_json(path: pathlib.Path, *, strict: bool = False) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise OSError("unsafe private state")
        if info.st_size > MAX_MANIFEST_BYTES:
            raise OSError("private state too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if strict:
            raise CpaAuthRejected("CPA quarantine manifest is invalid") from exc
        return {}
    if not isinstance(payload, dict):
        if strict:
            raise CpaAuthRejected("CPA quarantine manifest is invalid")
        return {}
    return payload


def _manifest(archive_dir: pathlib.Path) -> Dict[str, Any]:
    path = archive_dir / "manifest.json"
    if not path.exists():
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    payload = _read_private_json(path, strict=True)
    if not isinstance(payload.get("entries"), list):
        raise CpaAuthRejected("CPA quarantine manifest is invalid")
    payload.setdefault("schema", MANIFEST_SCHEMA)
    return payload


@contextmanager
def _quarantine_lock(archive_dir: pathlib.Path) -> Iterator[None]:
    _ensure_real_directory(archive_dir, create=True)
    archive_dir.chmod(0o700)
    lock_path = archive_dir / ".quarantine.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        lock_path.chmod(0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _contained_relative(path: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CpaAuthRejected("CPA credential file is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CpaAuthRejected("CPA credential file is unsafe")
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise CpaAuthRejected("CPA credential file is outside the configured directory") from exc


def _safe_reason(reason: str) -> str:
    value = str(reason or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{1,128}", value):
        return "unspecified"
    return value


def _unique_archive_path(archive_dir: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    target = archive_dir / source.name
    reserved = {"manifest.json", ".quarantine.lock"}
    if target.name not in reserved and not target.exists():
        return target
    index = 2
    while True:
        candidate = archive_dir / ("%s.%d%s" % (source.stem, index, source.suffix))
        if candidate.name not in reserved and not candidate.exists():
            return candidate
        index += 1


def quarantine_auth_record(
    config: Dict[str, Any],
    record: Dict[str, Any],
    *,
    reason: str,
    moved_at: str,
) -> Dict[str, Any]:
    auth_dir = configured_auth_dir(config)
    archive_dir = configured_archive_dir(config)
    source = pathlib.Path(str(record.get("path") or ""))
    _ensure_real_directory(auth_dir)
    relative = _contained_relative(source, auth_dir)
    with _quarantine_lock(archive_dir):
        if source.stat().st_dev != archive_dir.stat().st_dev:
            raise CpaAuthRejected("CPA quarantine requires one filesystem")
        manifest = _manifest(archive_dir)
        target = _unique_archive_path(archive_dir, source)
        os.replace(str(source), str(target))
        target.chmod(0o600)
        _fsync_directory(source.parent)
        _fsync_directory(archive_dir)
        entry = {
            "source_relative": relative.as_posix(),
            "quarantine_name": target.name,
            "reason": _safe_reason(reason),
            "moved_at": str(moved_at or ""),
        }
        manifest.setdefault("entries", []).append(entry)
        try:
            _atomic_write_json(archive_dir / "manifest.json", manifest)
        except OSError as exc:
            try:
                os.replace(str(target), str(source))
                _fsync_directory(source.parent)
                _fsync_directory(archive_dir)
            except OSError as rollback_exc:
                raise CpaAuthRejected("CPA quarantine transaction and rollback failed") from rollback_exc
            raise CpaAuthRejected("CPA quarantine manifest write failed; credential was restored") from exc
    return {**record, "path": str(target), "moved_from": str(source), "reason": entry["reason"]}


def _refresh_state_path(meta: Dict[str, Any]) -> pathlib.Path:
    config_path = meta.get("global_config_path")
    if isinstance(config_path, pathlib.Path):
        return config_path.parent / "cliproxy-refresh.json"
    return pathlib.Path("/var/lib/cloudx/cpa-health/cliproxy-refresh.json")


def refresh_auth_accounts(
    config: Dict[str, Any],
    meta: Dict[str, Any],
    *,
    apply: bool = False,
) -> Dict[str, Any]:
    records = scan_auth_records(config)
    state_path = _refresh_state_path(meta)
    state = _read_private_json(state_path)
    accounts_state = state.get("accounts")
    if not isinstance(accounts_state, dict):
        accounts_state = {}
        state["accounts"] = accounts_state
    confirmations = failure_confirmations(config)
    now = datetime.now(timezone.utc).isoformat()
    actions: List[Dict[str, Any]] = []
    active: List[Dict[str, Any]] = []
    for record in records:
        reason, permanent = static_failure_reason(record)
        key = str(record.get("path") or record.get("name") or "")
        entry = accounts_state.get(key)
        if not isinstance(entry, dict):
            entry = {}
            accounts_state[key] = entry
        if reason in {"unknown", "disabled"}:
            entry["failure_count"] = 0
            entry["last_reason"] = reason
            active.append({**record, "refresh_status": reason})
            continue
        failure_count = confirmations if permanent else int(entry.get("failure_count") or 0) + 1
        entry["failure_count"] = failure_count
        entry["last_reason"] = reason
        entry["last_failed_at"] = now
        eligible = permanent or failure_count >= confirmations
        action = {
            **record,
            "refresh_status": "quarantine" if eligible else "pending",
            "reason": reason,
            "failure_count": failure_count,
        }
        if eligible and apply:
            moved = quarantine_auth_record(config, record, reason=reason, moved_at=now)
            action["path"] = moved["path"]
            action["moved_from"] = moved["moved_from"]
        actions.append(action)
    if apply:
        _atomic_write_json(state_path, state)
    return {
        "apply": apply,
        "active": active,
        "actions": actions,
        "auth_count": len(records),
        "quarantine_dir": str(configured_archive_dir(config)),
        "state_path": str(state_path),
    }


def _legacy_entry_paths(
    entry: Dict[str, Any],
    auth_dir: pathlib.Path,
    archive_dir: pathlib.Path,
) -> Tuple[pathlib.Path, pathlib.Path]:
    if entry.get("source_relative") and entry.get("quarantine_name"):
        relative = pathlib.PurePosixPath(str(entry.get("source_relative") or ""))
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise CpaAuthRejected("CPA quarantine manifest is invalid")
        quarantine_name = pathlib.Path(str(entry.get("quarantine_name") or ""))
        if quarantine_name.name != str(entry.get("quarantine_name") or ""):
            raise CpaAuthRejected("CPA quarantine manifest is invalid")
        return auth_dir.joinpath(*relative.parts), archive_dir / quarantine_name
    source = pathlib.Path(str(entry.get("source_path") or ""))
    quarantine = pathlib.Path(str(entry.get("quarantine_path") or ""))
    try:
        source.relative_to(auth_dir)
        quarantine.relative_to(archive_dir)
    except ValueError as exc:
        raise CpaAuthRejected("CPA quarantine manifest is invalid") from exc
    return source, quarantine


def restore_quarantined_auth(config: Dict[str, Any], selector: str) -> Dict[str, Any]:
    auth_dir = configured_auth_dir(config)
    archive_dir = configured_archive_dir(config)
    _ensure_real_directory(auth_dir)
    with _quarantine_lock(archive_dir):
        manifest = _manifest(archive_dir)
        matches: List[Tuple[int, Dict[str, Any]]] = []
        for index, entry in enumerate(manifest.get("entries") or []):
            if not isinstance(entry, dict):
                raise CpaAuthRejected("CPA quarantine manifest is invalid")
            unused_target, source = _legacy_entry_paths(entry, auth_dir, archive_dir)
            candidates = {
                source.name,
                str(entry.get("account") or ""),
                str(entry.get("codexx_account") or ""),
            } - {""}
            if selector in candidates:
                matches.append((index, entry))
        if len(matches) != 1:
            raise CpaAuthRejected("CPA quarantine selector did not match exactly one entry")
        selected_index, selected = matches[0]
        target, source = _legacy_entry_paths(selected, auth_dir, archive_dir)
        relative = _contained_relative(source, archive_dir)
        if relative.name != source.name:
            raise CpaAuthRejected("CPA quarantine manifest is invalid")
        if not target.parent.is_dir() or target.exists():
            raise CpaAuthRejected("CPA restore target is unavailable")
        if source.stat().st_dev != target.parent.stat().st_dev:
            raise CpaAuthRejected("CPA restore requires one filesystem")
        os.replace(str(source), str(target))
        target.chmod(0o600)
        _fsync_directory(source.parent)
        _fsync_directory(target.parent)
        entries = list(manifest.get("entries") or [])
        entries.pop(selected_index)
        manifest["entries"] = entries
        try:
            _atomic_write_json(archive_dir / "manifest.json", manifest)
        except OSError as exc:
            try:
                os.replace(str(target), str(source))
                _fsync_directory(source.parent)
                _fsync_directory(target.parent)
            except OSError as rollback_exc:
                raise CpaAuthRejected("CPA restore transaction and rollback failed") from rollback_exc
            raise CpaAuthRejected("CPA restore manifest write failed; credential remained quarantined") from exc
    return {"restored": str(target), "quarantine_name": source.name}
