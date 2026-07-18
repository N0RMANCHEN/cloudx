from __future__ import annotations

import hashlib
import json
import os
import pathlib
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .cpa_auth import auth_account_id, auth_tokens


TRIGGER_SCHEMA = "cloudx.cpa-sweep-trigger.v1"
POOL_SCHEMA = "cloudx.cpa-pool-observation.v1"
TRIGGER_NAME = "trigger.json"
POOL_NAME = "pool-state.json"
MAX_DOCUMENT_BYTES = 16 * 1024
MAX_TRIGGER_AGE_SECONDS = 30 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60


@dataclass(frozen=True)
class SweepTrigger:
    path: pathlib.Path
    digest: str
    observed_at: datetime


def credential_key(auth: Dict[str, Any]) -> str:
    access_token, refresh_token, unused_id_token = auth_tokens(auth)
    value = {
        "authMode": str(auth.get("auth_mode") or "").strip().lower(),
        "accessToken": access_token,
        "accountId": auth_account_id(auth),
        "hasRefreshToken": bool(refresh_token),
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_bytes(path: pathlib.Path) -> Optional[bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT_BYTES:
            return None
        raw = os.read(descriptor, MAX_DOCUMENT_BYTES + 1)
        return raw if len(raw) <= MAX_DOCUMENT_BYTES else None
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _document(path: pathlib.Path) -> Tuple[Optional[Dict[str, Any]], bytes]:
    raw = _safe_bytes(path)
    if raw is None:
        return None, b""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, raw
    return (value if isinstance(value, dict) else None), raw


def _time(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def load_trigger(
    sweep_dir: pathlib.Path,
    *,
    now: Optional[datetime] = None,
) -> Tuple[Optional[SweepTrigger], str]:
    path = sweep_dir / TRIGGER_NAME
    if not path.exists():
        return None, "absent"
    document, raw = _document(path)
    if (
        document is None
        or set(document) != {"schema", "reason", "observedAt"}
        or document.get("schema") != TRIGGER_SCHEMA
        or document.get("reason") != "auth_unavailable"
    ):
        return None, "rejected"
    observed = _time(document.get("observedAt"))
    if observed is None:
        return None, "rejected"
    current = now or datetime.now(timezone.utc)
    age = (current - observed.astimezone(timezone.utc)).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > MAX_TRIGGER_AGE_SECONDS:
        return None, "stale"
    return SweepTrigger(path, hashlib.sha256(raw).hexdigest(), observed), "accepted"


def consume_trigger(trigger: SweepTrigger) -> bool:
    raw = _safe_bytes(trigger.path)
    if raw is None or hashlib.sha256(raw).hexdigest() != trigger.digest:
        return False
    try:
        trigger.path.unlink()
    except OSError:
        return False
    try:
        descriptor = os.open(str(trigger.path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        return False
    return True


def load_pool_observation(sweep_dir: pathlib.Path) -> Optional[Dict[str, Any]]:
    document, unused_raw = _document(sweep_dir / POOL_NAME)
    if (
        document is None
        or set(document) != {"schema", "state", "observedAt"}
        or document.get("schema") != POOL_SCHEMA
        or document.get("state") not in {"available", "unavailable"}
    ):
        return None
    observed = _time(document.get("observedAt"))
    if observed is None:
        return None
    return {"state": document["state"], "observed_at": observed}
