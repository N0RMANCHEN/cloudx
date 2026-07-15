from __future__ import annotations

import json
import os
import pathlib
import stat
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict


MAX_STATE_BYTES = 1024 * 1024
COUNT_KEYS = ("total", "ready", "warning", "limited", "failed")


class AccountStateRejected(RuntimeError):
    pass


def _count(document: Dict[str, Any], name: str) -> int:
    value = document.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AccountStateRejected("credential health state contains invalid counts")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountStateRejected("credential health state has no observation timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise AccountStateRejected("credential health state has an invalid observation timestamp") from exc
    if parsed.tzinfo is None:
        raise AccountStateRejected("credential health state observation timestamp has no timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_state(path: pathlib.Path, limit: int = MAX_STATE_BYTES) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AccountStateRejected("credential health state is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise AccountStateRejected("credential health state must be a regular file")
    if metadata.st_size > limit:
        raise AccountStateRejected("credential health state exceeds the size limit")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise AccountStateRejected("credential health state must be a regular file")
            if opened.st_size > limit:
                raise AccountStateRejected("credential health state exceeds the size limit")
            raw = handle.read(limit + 1)
    except OSError as exc:
        raise AccountStateRejected("credential health state is unavailable") from exc
    if len(raw) > limit:
        raise AccountStateRejected("credential health state exceeds the size limit")
    return raw


def adapt_legacy_quota_state(raw: bytes) -> Dict[str, Any]:
    try:
        source = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AccountStateRejected("credential health state is not valid JSON") from exc
    if not isinstance(source, dict):
        raise AccountStateRejected("credential health state must be an object")
    counts = {name: _count(source, name) for name in COUNT_KEYS}
    if counts["total"] != sum(counts[name] for name in COUNT_KEYS if name != "total"):
        raise AccountStateRejected("credential health state counts do not add up")
    return {
        "schema": "cloudx.account-state.v1",
        "source": "credential-health-summary",
        "observedAt": _timestamp(source.get("checked_at")),
        "accountCounts": {
            "total": counts["total"],
            "available": counts["ready"] + counts["warning"],
            "limited": counts["limited"],
            "unavailable": 0,
        },
        "unobservedAccounts": counts["failed"],
    }


def publish(path: pathlib.Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temp_name = tempfile.mkstemp(prefix=".cloudx-account-state-", dir=str(path.parent))
    try:
        os.fchmod(descriptor, 0o644)
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


def adapt_file(source: pathlib.Path, destination: pathlib.Path) -> Dict[str, Any]:
    document = adapt_legacy_quota_state(read_state(source))
    publish(destination, document)
    return document
