from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from . import agent_identity, cpa_capabilities
from .config import LocalConfig
from .files import atomic_write, ensure_private_directory


MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_FILES = 1024
LOCK_TIMEOUT_SECONDS = 10.0
IMPORT_SUFFIXES = {"", ".json", ".jsonl", ".ndjson", ".txt", ".md", ".log", ".data"}
IGNORED_DIRECTORY_NAMES = {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__"}
CLIPROXY_AUTH_BUNDLE_TYPE = "codexx-cliproxy-auth-bundle"
OAUTH_TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
RAW_CARD_PATTERN = re.compile(r"^(.+?)-{8,}(app_[A-Za-z0-9_-]+)-{4,}(.+)$")
AUTH_MARKERS = (
    '"access_token"',
    '"refresh_token"',
    '"id_token"',
    '"credentials"',
    '"accounts"',
    '"agent_private_key"',
    '"agent_runtime_id"',
    CLIPROXY_AUTH_BUNDLE_TYPE,
)


class LocalImportError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RawCardCredential:
    line_number: int
    email: str
    client_id: str
    refresh_token: str


@dataclass(frozen=True)
class LocalImportResult:
    dry_run: bool
    discovered_files: int
    ignored_files: int
    parsed_objects: int
    duplicate_objects: int
    written_files: int
    unchanged_files: int
    verified_files: int

    @property
    def skipped_items(self) -> int:
        return self.ignored_files + self.duplicate_objects + self.unchanged_files

    def document(self) -> Dict[str, Any]:
        return {
            "schema": "cloudx.local-cpa-import.v1",
            "status": "preview" if self.dry_run else "accepted",
            "destination": "local_cpa",
            "dryRun": self.dry_run,
            "counts": {
                "discovered": self.discovered_files,
                "ignored": self.ignored_files,
                "parsed": self.parsed_objects,
                "duplicates": self.duplicate_objects,
                "written": self.written_files,
                "unchanged": self.unchanged_files,
                "skipped": self.skipped_items,
                "verified": self.verified_files,
            },
            "verification": "preview_only" if self.dry_run else "complete",
            "adapter": "cloudx_native_compatibility",
            "externalService": {"managed": False, "restarted": False},
            "errors": [],
        }


@dataclass(frozen=True)
class _PlannedFile:
    name: str
    payload: bytes


def failure_document(code: str, message: str, dry_run: bool) -> Dict[str, Any]:
    return {
        "schema": "cloudx.local-cpa-import.v1",
        "status": "rejected",
        "destination": "local_cpa",
        "dryRun": dry_run,
        "counts": {
            "discovered": 0,
            "ignored": 0,
            "parsed": 0,
            "duplicates": 0,
            "written": 0,
            "unchanged": 0,
            "skipped": 0,
            "verified": 0,
        },
        "verification": "not_performed",
        "adapter": "cloudx_native_compatibility",
        "externalService": {"managed": False, "restarted": False},
        "errors": [{"code": code, "message": message}],
    }


def _auth_dir(config: LocalConfig) -> pathlib.Path:
    configured = config.local_cpa_auth_dir
    path = pathlib.Path(configured or config.home / ".cli-proxy-api").expanduser()
    if not path.is_absolute():
        raise LocalImportError("target_unsafe", "local CPA auth directory must be an absolute path")
    resolved = path.resolve(strict=False)
    forbidden_roots = [
        (config.home / ".local/lib/cloudx").resolve(strict=False),
        config.state_dir.resolve(strict=False),
    ]
    for root in forbidden_roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise LocalImportError("target_unsafe", "local CPA auth directory cannot be inside Cloudx release or state")
    return path


def _auth_tokens(data: Mapping[str, Any]) -> Tuple[str, str, str]:
    token = data.get("token") if isinstance(data.get("token"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    return (
        str(data.get("access_token") or token.get("access_token") or tokens.get("access_token") or "").strip(),
        str(data.get("refresh_token") or token.get("refresh_token") or tokens.get("refresh_token") or "").strip(),
        str(data.get("id_token") or token.get("id_token") or tokens.get("id_token") or "").strip(),
    )


def _account_id(data: Mapping[str, Any]) -> str:
    token = data.get("token") if isinstance(data.get("token"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    return str(
        data.get("account_id")
        or data.get("chatgpt_account_id")
        or token.get("account_id")
        or tokens.get("account_id")
        or ""
    ).strip()


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    if token.count(".") < 2:
        return {}
    try:
        raw = token.split(".", 2)[1]
        raw += "=" * (-len(raw) % 4)
        value = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _iso_from_epoch(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return ""


def _sub2api_payload(entry: Mapping[str, Any]) -> Dict[str, Any]:
    credentials = entry.get("credentials")
    if not isinstance(credentials, dict) or not credentials:
        return {}
    payload = dict(credentials)
    if payload.get("expires_at") and not payload.get("auth_expires_at"):
        payload["auth_expires_at"] = payload.get("expires_at")
    for key in ("name", "type", "provider", "last_refresh", "plan_type", "status", "source", "label"):
        if key in entry and key not in payload:
            payload[key] = entry[key]
    if payload.get("chatgpt_account_id") and not payload.get("account_id"):
        payload["account_id"] = payload.get("chatgpt_account_id")
    if not payload.get("email") and "@" in str(entry.get("name") or ""):
        payload["email"] = entry.get("name")
    return payload


def _flat_auth(entry: Mapping[str, Any], label: str) -> Dict[str, Any]:
    sub2api = _sub2api_payload(entry)
    payload = sub2api or dict(entry)
    if agent_identity.is_agent_identity(payload):
        try:
            return agent_identity.normalize(payload)
        except agent_identity.AgentIdentityError as exc:
            raise LocalImportError(
                "credential_invalid", "Agent Identity credential is invalid: %s" % exc
            ) from exc
    auth_type = str(payload.get("type") or payload.get("provider") or "").strip().casefold()
    if not sub2api and auth_type and auth_type != "codex":
        raise LocalImportError("unsupported_provider", "%s is not a Codex credential" % label)
    access_token, refresh_token, id_token = _auth_tokens(payload)
    if not any((access_token, refresh_token, id_token)):
        raise LocalImportError("credential_invalid", "%s has no access, refresh, or ID token" % label)
    access_payload = _decode_jwt_payload(access_token)
    id_payload = _decode_jwt_payload(id_token)
    auth_claim = id_payload.get("https://api.openai.com/auth")
    if not isinstance(auth_claim, dict):
        auth_claim = access_payload.get("https://api.openai.com/auth")
    if not isinstance(auth_claim, dict):
        auth_claim = {}
    email = str(
        payload.get("email")
        or payload.get("user_email")
        or entry.get("name")
        or id_payload.get("email")
        or id_payload.get("preferred_username")
        or ""
    ).strip()
    account_id = str(_account_id(payload) or auth_claim.get("chatgpt_account_id") or "").strip()
    expires_at = str(
        payload.get("expired")
        or payload.get("expiry")
        or payload.get("auth_expires_at")
        or payload.get("expires_at")
        or _iso_from_epoch(access_payload.get("exp"))
        or _iso_from_epoch(id_payload.get("exp"))
        or ""
    ).strip()
    flat: Dict[str, Any] = {
        "type": "codex",
        "disabled": bool(payload.get("disabled")),
        "websockets": bool(payload.get("websockets")),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "account_id": account_id,
    }
    if email:
        flat["email"] = email
    if expires_at:
        flat["expired"] = expires_at
    for key in ("last_refresh", "plan_type", "status", "source", "label"):
        if key in payload:
            flat[key] = payload[key]
    return flat


def _expand_object(document: Mapping[str, Any], label: str) -> List[Dict[str, Any]]:
    if document.get("type") == CLIPROXY_AUTH_BUNDLE_TYPE:
        files = document.get("files")
        if not isinstance(files, list) or not files:
            raise LocalImportError("credential_invalid", "%s has no auth bundle files" % label)
        results = []
        for index, item in enumerate(files, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
                raise LocalImportError("credential_invalid", "%s bundle entry %d is invalid" % (label, index))
            results.append(_flat_auth(item["data"], "%s bundle entry %d" % (label, index)))
        return results
    if "accounts" in document:
        accounts = document.get("accounts")
        if not isinstance(accounts, list) or not accounts:
            raise LocalImportError("credential_invalid", "%s has no account entries" % label)
        results = []
        for index, item in enumerate(accounts, start=1):
            if not isinstance(item, dict):
                raise LocalImportError("credential_invalid", "%s account %d is invalid" % (label, index))
            results.append(_flat_auth(item, "%s account %d" % (label, index)))
        return results
    return [_flat_auth(document, label)]


def _json_documents(text: str) -> List[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        raise LocalImportError("source_empty", "import source is empty")
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        if not value or any(not isinstance(item, dict) for item in value):
            raise LocalImportError("invalid_json", "JSON arrays must contain one or more objects")
        return list(value)
    if value is not None:
        raise LocalImportError("invalid_json", "import JSON must be an object or array of objects")
    if "{" not in stripped:
        if stripped.startswith("["):
            raise LocalImportError("invalid_json", "import JSON array is malformed")
        return []
    decoder = json.JSONDecoder()
    documents = []
    index = 0
    while True:
        start = stripped.find("{", index)
        if start < 0:
            break
        try:
            item, index = decoder.raw_decode(stripped, start)
        except json.JSONDecodeError as exc:
            raise LocalImportError("invalid_json", "cannot parse JSON object at offset %d" % exc.pos) from exc
        if not isinstance(item, dict):
            raise LocalImportError("invalid_json", "every concatenated JSON value must be an object")
        documents.append(item)
    if not documents:
        raise LocalImportError("invalid_json", "no JSON objects were found")
    return documents


def _raw_cards(text: str) -> List[RawCardCredential]:
    cards = []
    invalid = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line == "卡密导出":
            continue
        match = RAW_CARD_PATTERN.match(line)
        if not match:
            invalid.append(line_number)
            continue
        email, client_id, refresh_token = (part.strip() for part in match.groups())
        if "@" not in email or not refresh_token.startswith("rt.") or refresh_token.count(".") < 2:
            invalid.append(line_number)
            continue
        cards.append(RawCardCredential(line_number, email, client_id or DEFAULT_CODEX_CLIENT_ID, refresh_token))
    if not cards:
        detail = ", ".join(str(item) for item in invalid[:5])
        message = "no JSON credentials or raw card lines were recognized"
        if detail:
            message += "; unrecognized lines: %s" % detail
        raise LocalImportError("unsupported_format", message)
    return cards


def _refresh_card(
    card: RawCardCredential,
    opener: Optional[Callable[..., Any]],
) -> Dict[str, Any]:
    request = urllib.request.Request(
        OAUTH_TOKEN_ENDPOINT,
        data=urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": card.refresh_token,
            "client_id": card.client_id,
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "codex-cli",
        },
        method="POST",
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=10.0) as response:
            raw = response.read(MAX_SOURCE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise LocalImportError(
            "refresh_rejected",
            "raw card line %d refresh was rejected (HTTP %d)" % (card.line_number, int(exc.code)),
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LocalImportError("refresh_unavailable", "raw card token refresh is unavailable") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise LocalImportError("refresh_invalid", "raw card token refresh response is too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalImportError("refresh_invalid", "raw card token refresh returned invalid JSON") from exc
    if not isinstance(payload, dict) or str(payload.get("access_token") or "").count(".") < 2:
        raise LocalImportError("refresh_invalid", "raw card token refresh returned no usable access token")
    return _flat_auth(
        {
            "type": "codex",
            "email": card.email,
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token") or card.refresh_token,
            "id_token": payload.get("id_token") or "",
        },
        "raw card line %d" % card.line_number,
    )


def _normalize_text(
    text: str,
    label: str,
    dry_run: bool,
    opener: Optional[Callable[..., Any]],
) -> List[Dict[str, Any]]:
    documents = _json_documents(text)
    if documents:
        results = []
        for index, document in enumerate(documents, start=1):
            results.extend(_expand_object(document, "%s object %d" % (label, index)))
        return results
    cards = _raw_cards(text)
    if dry_run:
        return [
            _flat_auth(
                {"type": "codex", "email": card.email, "refresh_token": card.refresh_token},
                "raw card line %d" % card.line_number,
            )
            for card in cards
        ]
    return [_refresh_card(card, opener) for card in cards]


def _read_text(path: pathlib.Path) -> str:
    if path.is_symlink():
        raise LocalImportError("source_unsafe", "import source must not be a symlink")
    try:
        size = path.stat().st_size
        raw = path.read_bytes()
    except OSError as exc:
        raise LocalImportError("source_unreadable", "import source could not be read") from exc
    if size > MAX_SOURCE_BYTES or len(raw) > MAX_SOURCE_BYTES:
        raise LocalImportError("source_too_large", "an import source exceeds the 16 MiB limit")
    if b"\x00" in raw and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise LocalImportError("source_not_text", "import source is not text")
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise LocalImportError("source_not_text", "import source is not UTF-8 or UTF-16 text")


def _marker_present(text: str) -> bool:
    folded = text.casefold()
    return any(marker.casefold() in folded for marker in AUTH_MARKERS) or any(
        RAW_CARD_PATTERN.match(line.strip().lstrip("\ufeff")) for line in text.splitlines()
    )


def _safe_name(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return cleaned.strip(".-")[:120] or "auth"


def _source_hint(path: pathlib.Path, index: int, total: int) -> str:
    stem = _safe_name(path.name)
    for suffix in (".jsonl", ".ndjson", ".json", ".txt", ".md", ".log", ".data"):
        if stem.casefold().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return "%s-%d" % (stem, index) if total > 1 else stem


def _discover_directory(
    directory: pathlib.Path,
    dry_run: bool,
    opener: Optional[Callable[..., Any]],
) -> Tuple[List[Dict[str, Any]], List[str], int, int]:
    candidates = []
    ignored = 0
    discovered = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts[:-1]):
            continue
        if path.suffix.casefold() not in IMPORT_SUFFIXES:
            continue
        discovered += 1
        if path.is_symlink():
            ignored += 1
            continue
        candidates.append(path)
    if len(candidates) > MAX_CANDIDATE_FILES:
        raise LocalImportError("too_many_sources", "import directory exceeds the 1024-file limit")
    try:
        total_bytes = sum(path.stat().st_size for path in candidates)
    except OSError as exc:
        raise LocalImportError("source_unreadable", "an import directory candidate could not be inspected") from exc
    if total_bytes > MAX_TOTAL_SOURCE_BYTES:
        raise LocalImportError("source_too_large", "import directory exceeds the 64 MiB total limit")
    flats = []
    hints = []
    for path in candidates:
        text = _read_text(path)
        if not text.strip() or not _marker_present(text):
            ignored += 1
            continue
        try:
            expanded = _normalize_text(text, path.name, dry_run, opener)
        except LocalImportError as exc:
            raise LocalImportError(exc.code, "invalid auth candidate %s: %s" % (path.relative_to(directory), exc)) from exc
        for index, flat in enumerate(expanded, start=1):
            flats.append(flat)
            hints.append(_source_hint(path, index, len(expanded)))
    if not flats:
        raise LocalImportError("no_credentials", "directory contains no importable CPA credentials")
    return flats, hints, discovered, ignored


def _fingerprint(flat: Mapping[str, Any]) -> str:
    parts = agent_identity.fingerprint_parts(flat) or _auth_tokens(flat)
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _deduplicate(
    flats: Sequence[Dict[str, Any]],
    hints: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[str], int]:
    unique = []
    unique_hints = []
    seen = set()
    duplicates = 0
    for flat, hint in zip(flats, hints):
        fingerprint = _fingerprint(flat)
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        unique.append(flat)
        unique_hints.append(hint)
    return unique, unique_hints, duplicates


def _plan_files(
    flats: Sequence[Dict[str, Any]],
    hints: Sequence[str],
    name_prefix: str,
) -> List[_PlannedFile]:
    used: Dict[str, int] = {}
    plans = []
    for index, (flat, hint) in enumerate(zip(flats, hints), start=1):
        email = str(flat.get("email") or "").strip()
        if email and "@" in email:
            stem = _safe_name("codex-%s" % email.replace("@", "-"))
        elif hint:
            stem = _safe_name(hint)
            stem = stem if stem.startswith("codex-") else "codex-%s" % stem
        else:
            prefix = _safe_name(name_prefix or "codexx-import")
            prefix = prefix if prefix.startswith("codex-") else "codex-%s" % prefix
            stem = _safe_name("%s-%d" % (prefix, index))
        count = used.get(stem, 0) + 1
        used[stem] = count
        filename = "%s%s.json" % (stem, "-%d" % count if count > 1 else "")
        payload = (json.dumps(flat, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        plans.append(_PlannedFile(filename, payload))
    return plans


def _canonical_json(raw: bytes) -> bytes:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalImportError("target_invalid", "an existing target auth file is invalid JSON") from exc
    if not isinstance(document, dict):
        raise LocalImportError("target_invalid", "an existing target auth file is not a JSON object")
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


@contextlib.contextmanager
def _import_lock(auth_dir: pathlib.Path) -> Iterator[None]:
    ensure_private_directory(auth_dir)
    lock_path = auth_dir / ".cloudx-import.lock"
    if lock_path.is_symlink():
        raise LocalImportError("target_unsafe", "local CPA import lock is a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(lock_path), flags, 0o600)
    except OSError as exc:
        raise LocalImportError("lock_unavailable", "local CPA import lock could not be opened") from exc
    try:
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LocalImportError("lock_busy", "another local CPA import is in progress")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _target_state(auth_dir: pathlib.Path, plan: _PlannedFile) -> Tuple[pathlib.Path, Optional[bytes], bool]:
    target = auth_dir / plan.name
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise LocalImportError("target_unsafe", "target auth path is not a regular file: %s" % plan.name)
    try:
        original = target.read_bytes() if target.is_file() else None
    except OSError as exc:
        raise LocalImportError("target_unreadable", "target auth file could not be read: %s" % plan.name) from exc
    unchanged = original is not None and _canonical_json(original) == plan.payload
    return target, original, unchanged


def _write_plans(
    auth_dir: pathlib.Path,
    plans: Sequence[_PlannedFile],
    force: bool,
    dry_run: bool,
) -> Tuple[int, int, int]:
    if auth_dir.is_symlink() or (auth_dir.exists() and not auth_dir.is_dir()):
        raise LocalImportError("target_unsafe", "local CPA auth directory is not a regular directory")
    if dry_run:
        states = [_target_state(auth_dir, plan) for plan in plans] if auth_dir.is_dir() else []
        unchanged = sum(1 for unused_target, unused_original, same in states if same)
        conflicts = [target.name for target, original, same in states if original is not None and not same]
        if conflicts and not force:
            raise LocalImportError("target_conflict", "target auth JSON already exists: %s" % conflicts[0])
        return len(plans) - unchanged, unchanged, 0

    with _import_lock(auth_dir):
        states = [_target_state(auth_dir, plan) for plan in plans]
        conflicts = [target.name for target, original, same in states if original is not None and not same]
        if conflicts and not force:
            raise LocalImportError("target_conflict", "target auth JSON already exists: %s" % conflicts[0])
        changes = [
            (plan, target, original)
            for plan, (target, original, same) in zip(plans, states)
            if not same
        ]
        unchanged = len(plans) - len(changes)
        completed: List[Tuple[pathlib.Path, Optional[bytes]]] = []
        try:
            for plan, target, original in changes:
                atomic_write(target, plan.payload, mode=0o600)
                completed.append((target, original))
            for plan, target, unused_original in changes:
                if target.read_bytes() != plan.payload:
                    raise LocalImportError("verification_failed", "written auth file failed byte verification")
                document = json.loads(plan.payload.decode("utf-8"))
                if not isinstance(document, dict) or not (
                    any(_auth_tokens(document)) or agent_identity.is_valid(document)
                ):
                    raise LocalImportError("verification_failed", "written auth file failed credential verification")
        except Exception as exc:
            rollback_failed = False
            for target, original in reversed(completed):
                try:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write(target, original, mode=0o600)
                except OSError:
                    rollback_failed = True
            if rollback_failed:
                raise LocalImportError("rollback_failed", "local CPA import failed and rollback was incomplete") from exc
            if isinstance(exc, LocalImportError):
                raise
            raise LocalImportError("write_failed", "local CPA auth files could not be written atomically") from exc
        return len(changes), unchanged, len(changes)


def _complete_import(
    config: LocalConfig,
    flats: Sequence[Dict[str, Any]],
    hints: Sequence[str],
    discovered: int,
    ignored: int,
    force: bool,
    dry_run: bool,
    name_prefix: str,
) -> LocalImportResult:
    parsed = len(flats)
    unique, unique_hints, duplicates = _deduplicate(flats, hints)
    if any(agent_identity.is_agent_identity(flat) for flat in unique):
        try:
            cpa_capabilities.attest(config, agent_identity.EXTERNAL_CAPABILITY)
        except cpa_capabilities.CpaCapabilityError as exc:
            raise LocalImportError(
                "external_capability_missing",
                "Agent Identity credentials require a hash-bound live external local CPA "
                "capability %s (%s); Cloudx does not install or restart that service"
                % (agent_identity.EXTERNAL_CAPABILITY, exc.reason),
            ) from exc
    plans = _plan_files(unique, unique_hints, name_prefix)
    written, unchanged, verified = _write_plans(_auth_dir(config), plans, force, dry_run)
    return LocalImportResult(
        dry_run=dry_run,
        discovered_files=discovered,
        ignored_files=ignored,
        parsed_objects=parsed,
        duplicate_objects=duplicates,
        written_files=written,
        unchanged_files=unchanged,
        verified_files=verified,
    )


def import_text(
    config: LocalConfig,
    text: str,
    *,
    force: bool = True,
    dry_run: bool = False,
    name_prefix: str = "codexx-import",
    url_opener: Optional[Callable[..., Any]] = None,
) -> LocalImportResult:
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise LocalImportError("source_too_large", "stdin import source exceeds the 16 MiB limit")
    flats = _normalize_text(text, "stdin", dry_run, url_opener)
    hints = ["" for unused in flats]
    return _complete_import(config, flats, hints, 0, 0, force, dry_run, name_prefix)


def import_path(
    config: LocalConfig,
    source: pathlib.Path,
    *,
    force: bool = True,
    dry_run: bool = False,
    name_prefix: str = "codexx-import",
    url_opener: Optional[Callable[..., Any]] = None,
) -> LocalImportResult:
    path = source.expanduser()
    if path.is_symlink():
        raise LocalImportError("source_unsafe", "import source must not be a symlink")
    if path.is_dir():
        flats, hints, discovered, ignored = _discover_directory(path, dry_run, url_opener)
        return _complete_import(config, flats, hints, discovered, ignored, force, dry_run, name_prefix)
    if not path.is_file():
        raise LocalImportError("source_missing", "import source does not exist")
    if path.suffix.casefold() not in IMPORT_SUFFIXES:
        raise LocalImportError("unsupported_format", "unsupported import file type: %s" % (path.suffix or "none"))
    text = _read_text(path)
    if not _marker_present(text):
        raise LocalImportError("no_credentials", "import file contains no CPA credential fields")
    flats = _normalize_text(text, path.name, dry_run, url_opener)
    hints = [_source_hint(path, index, len(flats)) for index in range(1, len(flats) + 1)]
    return _complete_import(config, flats, hints, 1, 0, force, dry_run, name_prefix)
