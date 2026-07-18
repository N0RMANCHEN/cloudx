from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


MAX_SOURCE_BYTES = 16 * 1024 * 1024
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
RAW_CARD = re.compile(r"^(.+?)-{8,}(app_[A-Za-z0-9_-]+)-{4,}(.+)$")


class ImportRejected(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ImportResult:
    request_id: str
    request_hash: str
    status: str
    dry_run: bool
    written: int
    skipped: int
    errors: Sequence[Dict[str, str]]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "cloudx.import.v1",
            "requestId": self.request_id,
            "requestHash": self.request_hash,
            "status": self.status,
            "dryRun": self.dry_run,
            "written": self.written,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


def request_identity(raw: bytes) -> Tuple[str, str]:
    digest = hashlib.sha256(raw).hexdigest()
    return digest[:16], digest


def read_limited(stream: Any, limit: int = MAX_SOURCE_BYTES) -> bytes:
    raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ImportRejected("source_too_large", "import source exceeds 16 MiB")
    if not raw:
        raise ImportRejected("source_empty", "import source is empty")
    return raw


def _decode_source(raw: bytes) -> str:
    if b"\x00" in raw and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ImportRejected("source_not_text", "import source must be text")
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportRejected("source_encoding", "import source must be UTF-8 or UTF-16")


def _json_documents(text: str) -> List[Any]:
    stripped = text.strip()
    if not stripped:
        raise ImportRejected("source_empty", "import source is empty")
    try:
        return [json.loads(stripped)]
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    documents: List[Any] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, index = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            raise ImportRejected("invalid_json", "import source contains invalid JSON")
        documents.append(value)
    return documents


def _tokens(data: Dict[str, Any]) -> Tuple[str, str, str]:
    token = data.get("token") if isinstance(data.get("token"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    return (
        str(data.get("access_token") or token.get("access_token") or tokens.get("access_token") or "").strip(),
        str(data.get("refresh_token") or token.get("refresh_token") or tokens.get("refresh_token") or "").strip(),
        str(data.get("id_token") or token.get("id_token") or tokens.get("id_token") or "").strip(),
    )


def _jwt_payload(token: str) -> Dict[str, Any]:
    if token.count(".") < 2:
        return {}
    try:
        payload = token.split(".", 2)[1]
        payload += "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _iso_epoch(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _flatten(entry: Dict[str, Any]) -> Dict[str, Any]:
    credentials = entry.get("credentials") if isinstance(entry.get("credentials"), dict) else None
    source = dict(credentials if credentials is not None else entry)
    access, refresh, identity = _tokens(source)
    if not any((access, refresh, identity)):
        raise ImportRejected("missing_token", "an import record has no supported token")
    access_claims = _jwt_payload(access)
    id_claims = _jwt_payload(identity)
    auth_claims = id_claims.get("https://api.openai.com/auth")
    if not isinstance(auth_claims, dict):
        auth_claims = access_claims.get("https://api.openai.com/auth")
    if not isinstance(auth_claims, dict):
        auth_claims = {}
    nested_auth_type = str(source.get("type") or source.get("provider") or "").casefold()
    outer_auth_type = str(entry.get("type") or "").casefold()
    outer_platform = str(entry.get("platform") or "").casefold()
    if nested_auth_type:
        auth_type = nested_auth_type
    elif credentials is not None and outer_auth_type == "oauth" and outer_platform == "openai":
        auth_type = "codex"
    else:
        auth_type = outer_auth_type or "codex"
    if auth_type not in ("", "codex"):
        raise ImportRejected("wrong_provider", "an import record is not a Codex credential")
    email = str(source.get("email") or source.get("user_email") or entry.get("name") or id_claims.get("email") or "").strip()
    account_id = str(
        source.get("account_id")
        or source.get("chatgpt_account_id")
        or auth_claims.get("chatgpt_account_id")
        or ""
    ).strip()
    expired = str(
        source.get("expired")
        or source.get("expiry")
        or source.get("auth_expires_at")
        or source.get("expires_at")
        or _iso_epoch(access_claims.get("exp"))
        or _iso_epoch(id_claims.get("exp"))
        or ""
    ).strip()
    flat: Dict[str, Any] = {
        "type": "codex",
        "disabled": bool(source.get("disabled", False)),
        "websockets": bool(source.get("websockets", False)),
        "access_token": access,
        "refresh_token": refresh,
        "id_token": identity,
        "account_id": account_id,
    }
    if email:
        flat["email"] = email
    if expired:
        flat["expired"] = expired
    for key in ("label", "source", "last_refresh", "plan_type", "status"):
        if key in source:
            flat[key] = source[key]
    return flat


def _expand(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield from _expand(item)
        return
    if not isinstance(value, dict):
        return
    result = value.get("result")
    if isinstance(result, dict) and isinstance(result.get("accounts"), list):
        yield from _expand(result["accounts"])
        return
    payload = value.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("accounts"), list):
        yield from _expand(payload["accounts"])
        return
    if isinstance(value.get("accounts"), list):
        yield from _expand(value["accounts"])
        return
    if value.get("type") in ("cliproxy-auth-bundle", "codexx-cliproxy-auth-bundle") and isinstance(value.get("files"), list):
        for item in value["files"]:
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                yield item["data"]
        return
    yield value


def _refresh_card(email: str, client_id: str, refresh_token: str, opener: Callable[..., Any]) -> Dict[str, Any]:
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token}
    ).encode("ascii")
    request = urllib.request.Request(TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise ImportRejected("refresh_failed", "a raw card credential could not be refreshed")
    if not isinstance(payload, dict):
        raise ImportRejected("refresh_failed", "a raw card credential could not be refreshed")
    return _flatten(
        {
            "email": email,
            "access_token": payload.get("access_token", ""),
            "refresh_token": payload.get("refresh_token") or refresh_token,
            "id_token": payload.get("id_token", ""),
        }
    )


def _normalize_text(text: str, opener: Callable[..., Any]) -> List[Dict[str, Any]]:
    documents = _json_documents(text)
    records: List[Dict[str, Any]] = []
    if documents:
        if len(documents) == 1 and isinstance(documents[0], dict) and documents[0].get("schema") == "cloudx.import-source.v1":
            files = documents[0].get("files")
            if not isinstance(files, list):
                raise ImportRejected("invalid_envelope", "directory import envelope is invalid")
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                    raise ImportRejected("invalid_envelope", "directory import envelope is invalid")
                records.extend(_normalize_text(item["content"], opener))
        else:
            for document in documents:
                for entry in _expand(document):
                    records.append(_flatten(entry))
    if not records:
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line in ("card export", "卡密导出"):
                continue
            match = RAW_CARD.match(line)
            if not match or "@" not in match.group(1):
                raise ImportRejected("unsupported_source", "import source has no supported credential records")
            records.append(_refresh_card(match.group(1).strip(), match.group(2).strip() or DEFAULT_CODEX_CLIENT_ID, match.group(3).strip(), opener))
    if not records:
        raise ImportRejected("unsupported_source", "import source has no supported credential records")
    return records


def normalize(raw: bytes, opener: Callable[..., Any] = urllib.request.urlopen) -> List[Dict[str, Any]]:
    text = _decode_source(raw)
    records = _normalize_text(text, opener)
    unique: Dict[str, Dict[str, Any]] = {}
    for record in records:
        fingerprint = hashlib.sha256("\0".join(_tokens(record)).encode("utf-8")).hexdigest()
        unique.setdefault(fingerprint, record)
    return list(unique.values())


@contextlib.contextmanager
def locked(path: pathlib.Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _target(auth_dir: pathlib.Path, record: Dict[str, Any]) -> pathlib.Path:
    fingerprint = hashlib.sha256("\0".join(_tokens(record)).encode("utf-8")).hexdigest()[:24]
    return auth_dir / ("codex-%s.json" % fingerprint)


def _serialized(record: Dict[str, Any]) -> bytes:
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=".cloudx-import-", dir=str(path.parent))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def import_records(raw: bytes, auth_dir: pathlib.Path, lock_path: pathlib.Path, dry_run: bool, force: bool) -> ImportResult:
    request_id, request_hash = request_identity(raw)
    records = normalize(raw)
    auth_dir.mkdir(parents=True, exist_ok=True)
    try:
        auth_dir.chmod(0o700)
    except OSError:
        pass
    written = 0
    skipped = 0
    with locked(lock_path):
        plan: List[Tuple[pathlib.Path, bytes, Optional[bytes]]] = []
        for record in records:
            target = _target(auth_dir, record)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ImportRejected("unsafe_target", "an import target is not a regular file")
            data = _serialized(record)
            previous = target.read_bytes() if target.exists() else None
            if previous == data:
                skipped += 1
                continue
            if previous is not None and not force:
                raise ImportRejected("target_exists", "an import target already exists; use --force to replace it")
            plan.append((target, data, previous))
        if dry_run:
            return ImportResult(request_id, request_hash, "accepted", True, len(plan), skipped, ())
        completed: List[Tuple[pathlib.Path, Optional[bytes]]] = []
        try:
            for target, data, previous in plan:
                _atomic_write(target, data)
                completed.append((target, previous))
                written += 1
        except Exception:
            for target, previous in reversed(completed):
                try:
                    if previous is None:
                        target.unlink()
                    else:
                        _atomic_write(target, previous)
                except OSError:
                    pass
            raise ImportRejected("write_failed", "credential transaction failed and was rolled back")
    return ImportResult(request_id, request_hash, "accepted", False, written, skipped, ())
