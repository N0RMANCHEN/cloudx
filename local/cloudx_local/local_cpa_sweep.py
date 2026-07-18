from __future__ import annotations

import hashlib
import json
import os
import pathlib
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple


SCHEMA = "cloudx.cpa-sweep-trigger.v1"
TRIGGER_NAME = "trigger.json"
MAX_BYTES = 16 * 1024
MAX_AGE_SECONDS = 30 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60


@dataclass(frozen=True)
class Trigger:
    path: pathlib.Path
    digest: str


def _bytes(path: pathlib.Path) -> Optional[bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            return None
        raw = os.read(descriptor, MAX_BYTES + 1)
        return raw if len(raw) <= MAX_BYTES else None
    except OSError:
        return None
    finally:
        os.close(descriptor)


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


def load(sweep_dir: pathlib.Path, *, now: Optional[datetime] = None) -> Tuple[Optional[Trigger], str]:
    path = sweep_dir / TRIGGER_NAME
    if not path.exists():
        return None, "absent"
    raw = _bytes(path)
    if raw is None:
        return None, "rejected"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "rejected"
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "reason", "observedAt"}
        or document.get("schema") != SCHEMA
        or document.get("reason") != "auth_unavailable"
    ):
        return None, "rejected"
    observed = _time(document.get("observedAt"))
    if observed is None:
        return None, "rejected"
    current = now or datetime.now(timezone.utc)
    age = (current - observed.astimezone(timezone.utc)).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > MAX_AGE_SECONDS:
        return None, "stale"
    return Trigger(path, hashlib.sha256(raw).hexdigest()), "accepted"


def consume(trigger: Trigger) -> bool:
    raw = _bytes(trigger.path)
    if raw is None or hashlib.sha256(raw).hexdigest() != trigger.digest:
        return False
    try:
        trigger.path.unlink()
        descriptor = os.open(str(trigger.path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        return False
    return True
