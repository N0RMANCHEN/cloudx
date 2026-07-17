from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

from .public_metadata import validate_public_document


MAX_HEALTH_BYTES = 64 * 1024
FORMAL_SCHEMA = "cloudx.health.v1"
LEGACY_CONTRACT = "cloudx.health"
LEGACY_SCHEMA_VERSION = 1
REVISION_RE = re.compile(r"^[a-f0-9]{7,64}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")
GATEWAY_STATES = {
    "healthy": "ready",
    "degraded": "degraded",
    "unavailable": "offline",
    "unknown": "unknown",
}
IMPORT_STATES = {
    "ready": "unknown",
    "busy": "degraded",
    "degraded": "degraded",
    "unavailable": "offline",
    "unknown": "unknown",
}
PROCESS_STATES = {"active", "activating", "deactivating", "failed", "inactive", "unknown"}
SERVICE_STATES = {"ready", "degraded", "offline", "unknown"}
CAPACITY_STATES = {"ready", "degraded", "unavailable", "unknown"}


class LegacyHealthRejected(RuntimeError):
    pass


def _exact(value: Any, keys: Set[str], label: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise LegacyHealthRejected("%s has missing or unknown fields" % label)
    return value


def _count(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LegacyHealthRejected("%s must be a non-negative integer" % label)
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise LegacyHealthRejected("%s must be a bounded timestamp" % label)
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise LegacyHealthRejected("%s must be an ISO-8601 timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LegacyHealthRejected("%s must include a timezone" % label)
    return parsed.astimezone(timezone.utc)


def _optional_timestamp(value: Any, label: str) -> None:
    if value is not None:
        _timestamp(value, label)


def _bounded_text(value: Any, label: str, maximum: int = 64) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise LegacyHealthRejected("%s must be bounded text" % label)
    return value.strip()


def _canonical(document: Dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(document: Dict[str, Any]) -> str:
    unsigned = dict(document)
    unsigned.pop("digest", None)
    return "sha256:%s" % hashlib.sha256(_canonical(unsigned)).hexdigest()


def read_formal_health(path: pathlib.Path, limit: int = MAX_HEALTH_BYTES) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LegacyHealthRejected("formal health input is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise LegacyHealthRejected("formal health input must be a regular file")
    if metadata.st_size > limit:
        raise LegacyHealthRejected("formal health input exceeds the size limit")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
                raise LegacyHealthRejected("formal health input changed during validation")
            raw = handle.read(limit + 1)
    except OSError as exc:
        raise LegacyHealthRejected("formal health input is unavailable") from exc
    if len(raw) > limit:
        raise LegacyHealthRejected("formal health input exceeds the size limit")
    return raw


def parse_formal_health(raw: bytes) -> Dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyHealthRejected("formal health input is invalid JSON") from exc
    root = _exact(
        document,
        {
            "schema",
            "cloudxVersion",
            "protocolVersion",
            "gatewayStatus",
            "importStatus",
            "accountCounts",
            "checkedAt",
            "freshness",
        },
        "formal health",
    )
    if root["schema"] != FORMAL_SCHEMA:
        raise LegacyHealthRejected("formal health schema is unsupported")
    protocol = _count(root["protocolVersion"], "formal health protocolVersion")
    if protocol != 1:
        raise LegacyHealthRejected("formal health protocol is unsupported")
    version = _bounded_text(root["cloudxVersion"], "formal health cloudxVersion")
    if not VERSION_RE.fullmatch(version):
        raise LegacyHealthRejected("formal health cloudxVersion is invalid")
    if root["gatewayStatus"] not in GATEWAY_STATES:
        raise LegacyHealthRejected("formal health gatewayStatus is invalid")
    if root["importStatus"] not in IMPORT_STATES:
        raise LegacyHealthRejected("formal health importStatus is invalid")
    _timestamp(root["checkedAt"], "formal health checkedAt")
    counts = _exact(
        root["accountCounts"],
        {"total", "available", "limited", "unavailable"},
        "formal health accountCounts",
    )
    parsed_counts = {
        name: _count(counts[name], "formal health accountCounts.%s" % name)
        for name in ("total", "available", "limited", "unavailable")
    }
    if sum(parsed_counts[name] for name in ("available", "limited", "unavailable")) > parsed_counts["total"]:
        raise LegacyHealthRejected("formal health account counts do not add up")
    freshness = _exact(root["freshness"], {"state", "ageSeconds"}, "formal health freshness")
    if freshness["state"] not in {"fresh", "stale", "unknown"}:
        raise LegacyHealthRejected("formal health freshness state is invalid")
    _count(freshness["ageSeconds"], "formal health freshness.ageSeconds")
    return root


def _capacity_state(total: int, ready: int, blocked: int) -> str:
    if total > 0 and ready == total:
        return "ready"
    if ready > 0:
        return "degraded"
    if blocked > 0:
        return "unavailable"
    return "unknown"


def _revision(value: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if REVISION_RE.fullmatch(candidate) else "unknown"


def build_legacy_health(
    formal: Dict[str, Any],
    *,
    producer_revision: str = "unknown",
) -> Dict[str, Any]:
    source = parse_formal_health(_canonical(formal))
    checked_at = _timestamp(source["checkedAt"], "formal health checkedAt")
    counts = source["accountCounts"]
    total = int(counts["total"])
    ready = int(counts["available"])
    limited = int(counts["limited"])
    unavailable = int(counts["unavailable"])
    blocked = limited + unavailable
    unknown = total - ready - blocked
    freshness = source["freshness"]
    observed = None
    if freshness["state"] != "unknown":
        try:
            observed = (checked_at - timedelta(seconds=int(freshness["ageSeconds"]))).isoformat()
        except OverflowError as exc:
            raise LegacyHealthRejected("formal health freshness age is out of range") from exc
    gateway_state = GATEWAY_STATES[str(source["gatewayStatus"])]
    imports_state = IMPORT_STATES[str(source["importStatus"])]
    document = {
        "contract": LEGACY_CONTRACT,
        "schemaVersion": LEGACY_SCHEMA_VERSION,
        "generatedAt": checked_at.isoformat(),
        "producer": {
            "name": "cloudx",
            "version": str(source["cloudxVersion"]),
            "revision": _revision(producer_revision),
        },
        "gateway": {
            "state": gateway_state,
            "processState": "unknown",
            "endpointState": gateway_state,
            "httpStatus": None,
            "observedAt": checked_at.isoformat(),
        },
        "capacity": {
            "state": _capacity_state(total, ready, blocked),
            "available": ready > 0,
            "accounts": {
                "total": total,
                "ready": ready,
                "warning": 0,
                "blocked": blocked,
                "unknown": unknown,
            },
            "blockedReasons": {
                "quota": limited,
                "login": 0,
                "cooldown": 0,
                "other": unavailable,
            },
            "activeSessions": None,
            "observedAt": observed,
            "earliestRecoveryAt": None,
        },
        "imports": {
            "state": imports_state,
            "processState": "unknown",
            "pendingFailures": 0,
            "lastFailureAt": None,
        },
    }
    document["digest"] = _digest(document)
    validate_legacy_health(document)
    return validate_public_document(document, "legacy Cloudx health publication")


def validate_legacy_health(document: Dict[str, Any]) -> None:
    root = _exact(
        document,
        {"contract", "schemaVersion", "generatedAt", "producer", "gateway", "capacity", "imports", "digest"},
        "legacy health",
    )
    if root["contract"] != LEGACY_CONTRACT or root["schemaVersion"] != LEGACY_SCHEMA_VERSION:
        raise LegacyHealthRejected("legacy health identity is unsupported")
    _timestamp(root["generatedAt"], "legacy health generatedAt")
    producer = _exact(root["producer"], {"name", "version", "revision"}, "legacy health producer")
    if producer["name"] != "cloudx":
        raise LegacyHealthRejected("legacy health producer is invalid")
    version = _bounded_text(producer["version"], "legacy health producer.version")
    if not VERSION_RE.fullmatch(version):
        raise LegacyHealthRejected("legacy health producer.version is invalid")
    revision = _bounded_text(producer["revision"], "legacy health producer.revision")
    if revision != "unknown" and not REVISION_RE.fullmatch(revision):
        raise LegacyHealthRejected("legacy health producer.revision is invalid")
    gateway = _exact(
        root["gateway"],
        {"state", "processState", "endpointState", "httpStatus", "observedAt"},
        "legacy health gateway",
    )
    if gateway["state"] not in SERVICE_STATES or gateway["endpointState"] not in SERVICE_STATES:
        raise LegacyHealthRejected("legacy health gateway state is invalid")
    if gateway["processState"] not in PROCESS_STATES:
        raise LegacyHealthRejected("legacy health gateway process state is invalid")
    if gateway["httpStatus"] is not None and not 100 <= _count(gateway["httpStatus"], "legacy health gateway.httpStatus") <= 599:
        raise LegacyHealthRejected("legacy health gateway.httpStatus is invalid")
    _timestamp(gateway["observedAt"], "legacy health gateway.observedAt")
    capacity = _exact(
        root["capacity"],
        {"state", "available", "accounts", "blockedReasons", "activeSessions", "observedAt", "earliestRecoveryAt"},
        "legacy health capacity",
    )
    if capacity["state"] not in CAPACITY_STATES or not isinstance(capacity["available"], bool):
        raise LegacyHealthRejected("legacy health capacity state is invalid")
    accounts = _exact(capacity["accounts"], {"total", "ready", "warning", "blocked", "unknown"}, "legacy health accounts")
    reasons = _exact(capacity["blockedReasons"], {"quota", "login", "cooldown", "other"}, "legacy health blockedReasons")
    parsed_accounts = {name: _count(value, "legacy health accounts.%s" % name) for name, value in accounts.items()}
    parsed_reasons = {name: _count(value, "legacy health blockedReasons.%s" % name) for name, value in reasons.items()}
    if parsed_accounts["total"] != sum(parsed_accounts[name] for name in ("ready", "warning", "blocked", "unknown")):
        raise LegacyHealthRejected("legacy health account counts do not add up")
    if parsed_accounts["blocked"] != sum(parsed_reasons.values()):
        raise LegacyHealthRejected("legacy health blocked reasons do not add up")
    if capacity["available"] != (parsed_accounts["ready"] + parsed_accounts["warning"] > 0):
        raise LegacyHealthRejected("legacy health available state is inconsistent")
    expected = _capacity_state(parsed_accounts["total"], parsed_accounts["ready"], parsed_accounts["blocked"])
    if capacity["state"] != expected:
        raise LegacyHealthRejected("legacy health capacity state is inconsistent")
    if capacity["activeSessions"] is not None:
        _count(capacity["activeSessions"], "legacy health activeSessions")
    _optional_timestamp(capacity["observedAt"], "legacy health capacity.observedAt")
    _optional_timestamp(capacity["earliestRecoveryAt"], "legacy health capacity.earliestRecoveryAt")
    imports = _exact(root["imports"], {"state", "processState", "pendingFailures", "lastFailureAt"}, "legacy health imports")
    if imports["state"] not in SERVICE_STATES or imports["processState"] not in PROCESS_STATES:
        raise LegacyHealthRejected("legacy health import state is invalid")
    _count(imports["pendingFailures"], "legacy health imports.pendingFailures")
    _optional_timestamp(imports["lastFailureAt"], "legacy health imports.lastFailureAt")
    digest = _bounded_text(root["digest"], "legacy health digest", 80)
    if digest != _digest(root):
        raise LegacyHealthRejected("legacy health digest is invalid")


def publish(path: pathlib.Path, document: Dict[str, Any]) -> None:
    if not path.is_absolute():
        raise LegacyHealthRejected("legacy health output path must be absolute")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise LegacyHealthRejected("legacy health output must be a regular file")
    validate_legacy_health(document)
    validate_public_document(document, "legacy Cloudx health publication")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".cloudx-legacy-health-", dir=str(path.parent))
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def bridge_file(
    source: pathlib.Path,
    destination: Optional[pathlib.Path] = None,
    *,
    producer_revision: str = "unknown",
) -> Dict[str, Any]:
    document = build_legacy_health(
        parse_formal_health(read_formal_health(source)),
        producer_revision=producer_revision,
    )
    if destination is not None:
        publish(destination, document)
    return document
