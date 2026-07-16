from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any, BinaryIO, Dict, Iterable, List, Mapping, Optional, Tuple


MAX_EVIDENCE_BYTES = 64 * 1024
EVIDENCE_SCHEMA = "cloudx.http-importer-stop-gate-evidence.v1"
RESULT_SCHEMA = "cloudx.http-importer-stop-gate.v1"
SERVICE_NAME = "codex-import.service"
LISTENER_PORT = 8780
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class EvidenceRejected(ValueError):
    pass


def _object(value: Any, keys: Iterable[str], section: str) -> Mapping[str, Any]:
    expected = set(keys)
    if not isinstance(value, dict):
        raise EvidenceRejected("%s must be an object" % section)
    if set(value) != expected:
        raise EvidenceRejected("%s has missing or unknown fields" % section)
    return value


def _boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise EvidenceRejected("%s must be a boolean" % field)
    return value


def _count(value: Any, field: str) -> int:
    if type(value) is not int or value < 0 or value > 1_000_000:
        raise EvidenceRejected("%s must be a bounded non-negative integer" % field)
    return value


def _string(value: Any, field: str, maximum: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EvidenceRejected("%s must be a non-empty bounded string" % field)
    return value


def _timestamp(value: Any, field: str, optional: bool = False) -> Tuple[Optional[str], Optional[dt.datetime]]:
    if value is None and optional:
        return None, None
    raw = _string(value, field, 64)
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise EvidenceRejected("%s must be an ISO-8601 timestamp" % field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceRejected("%s must include a timezone" % field)
    return raw, parsed


def _decode(raw: bytes) -> Mapping[str, Any]:
    if not raw:
        raise EvidenceRejected("evidence input is empty")
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise EvidenceRejected("evidence exceeds the 64 KiB limit")

    def unique_object(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        document: Dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise EvidenceRejected("evidence contains duplicate fields")
            document[key] = value
        return document

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except UnicodeDecodeError as exc:
        raise EvidenceRejected("evidence must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceRejected("evidence must be valid JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceRejected("evidence root must be an object")
    return value


def read_evidence(stream: BinaryIO) -> bytes:
    raw = stream.read(MAX_EVIDENCE_BYTES + 1)
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise EvidenceRejected("evidence exceeds the 64 KiB limit")
    return raw


def _blocker(blockers: List[Dict[str, str]], condition: bool, code: str, message: str) -> None:
    if condition:
        blockers.append({"code": code, "message": message})


def evaluate(raw: bytes) -> Dict[str, Any]:
    evidence = _object(
        _decode(raw),
        (
            "schema",
            "capturedAt",
            "service",
            "listener",
            "traffic",
            "transactions",
            "adapter",
            "consumers",
            "dependencies",
            "rollback",
        ),
        "evidence",
    )
    if evidence["schema"] != EVIDENCE_SCHEMA:
        raise EvidenceRejected("unsupported evidence schema")
    captured_raw, captured_at = _timestamp(evidence["capturedAt"], "capturedAt")

    service = _object(
        evidence["service"],
        ("name", "active", "enabled", "identityStable"),
        "service",
    )
    if service["name"] != SERVICE_NAME:
        raise EvidenceRejected("service.name must identify codex-import.service")
    service_active = _boolean(service["active"], "service.active")
    service_enabled = _boolean(service["enabled"], "service.enabled")
    service_stable = _boolean(service["identityStable"], "service.identityStable")

    listener = _object(
        evidence["listener"],
        ("port", "listening", "establishedConnections"),
        "listener",
    )
    listener_port = _count(listener["port"], "listener.port")
    listener_present = _boolean(listener["listening"], "listener.listening")
    established = _count(listener["establishedConnections"], "listener.establishedConnections")

    traffic = _object(
        evidence["traffic"],
        ("journalReadable", "lastRequestAt", "unattributedRequests", "activeHttpCallers", "laterRequests"),
        "traffic",
    )
    journal_readable = _boolean(traffic["journalReadable"], "traffic.journalReadable")
    _, last_request_at = _timestamp(traffic["lastRequestAt"], "traffic.lastRequestAt", optional=True)
    unattributed = _count(traffic["unattributedRequests"], "traffic.unattributedRequests")
    active_callers = _count(traffic["activeHttpCallers"], "traffic.activeHttpCallers")
    later_requests = _count(traffic["laterRequests"], "traffic.laterRequests")
    if last_request_at is not None and captured_at is not None and last_request_at > captured_at:
        raise EvidenceRejected("traffic.lastRequestAt cannot be later than capturedAt")

    transactions = _object(
        evidence["transactions"],
        ("lockHolders", "rawFailureInputs", "failureRecordsSanitized", "importStatus"),
        "transactions",
    )
    lock_holders = _count(transactions["lockHolders"], "transactions.lockHolders")
    raw_inputs = _count(transactions["rawFailureInputs"], "transactions.rawFailureInputs")
    failures_sanitized = _boolean(
        transactions["failureRecordsSanitized"], "transactions.failureRecordsSanitized"
    )
    import_status = _string(transactions["importStatus"], "transactions.importStatus", 32)
    if import_status not in ("ready", "busy", "unavailable"):
        raise EvidenceRejected("transactions.importStatus is unsupported")

    adapter = _object(
        evidence["adapter"],
        ("transport", "httpReferences", "sha256", "signedArtifactVerified"),
        "adapter",
    )
    transport = _string(adapter["transport"], "adapter.transport", 16)
    if transport not in ("ssh", "http", "unknown"):
        raise EvidenceRejected("adapter.transport is unsupported")
    http_references = _count(adapter["httpReferences"], "adapter.httpReferences")
    adapter_sha256 = _string(adapter["sha256"], "adapter.sha256", 64)
    if not SHA256_RE.fullmatch(adapter_sha256):
        raise EvidenceRejected("adapter.sha256 must be a lowercase SHA-256 digest")
    adapter_signed = _boolean(adapter["signedArtifactVerified"], "adapter.signedArtifactVerified")

    consumers = _object(
        evidence["consumers"],
        ("legacyHealthReaders", "goalWatchdogFormalHealth", "legacyExporterRetained"),
        "consumers",
    )
    legacy_readers = _count(consumers["legacyHealthReaders"], "consumers.legacyHealthReaders")
    goal_formal = _boolean(consumers["goalWatchdogFormalHealth"], "consumers.goalWatchdogFormalHealth")
    exporter_retained = _boolean(consumers["legacyExporterRetained"], "consumers.legacyExporterRetained")

    dependencies = _object(evidence["dependencies"], ("requiredUnits",), "dependencies")
    required_units = _count(dependencies["requiredUnits"], "dependencies.requiredUnits")

    rollback = _object(
        evidence["rollback"],
        (
            "unitSnapshot",
            "runtimeSnapshot",
            "tokenMetadataSnapshot",
            "failureReceiptsSnapshot",
            "restorePlan",
        ),
        "rollback",
    )
    rollback_checks = {
        "rollback_unit_missing": _boolean(rollback["unitSnapshot"], "rollback.unitSnapshot"),
        "rollback_runtime_missing": _boolean(rollback["runtimeSnapshot"], "rollback.runtimeSnapshot"),
        "rollback_token_metadata_missing": _boolean(
            rollback["tokenMetadataSnapshot"], "rollback.tokenMetadataSnapshot"
        ),
        "rollback_failure_receipts_missing": _boolean(
            rollback["failureReceiptsSnapshot"], "rollback.failureReceiptsSnapshot"
        ),
        "rollback_restore_plan_missing": _boolean(rollback["restorePlan"], "rollback.restorePlan"),
    }

    blockers: List[Dict[str, str]] = []
    _blocker(blockers, not service_active, "service_not_active", "The legacy importer baseline is not active.")
    _blocker(blockers, not service_enabled, "service_not_enabled", "The legacy importer baseline is not enabled.")
    _blocker(
        blockers, not service_stable, "service_identity_changed", "The importer identity changed during observation."
    )
    _blocker(
        blockers, listener_port != LISTENER_PORT, "listener_port_changed", "The importer is not on the accepted port."
    )
    _blocker(blockers, not listener_present, "listener_missing", "The active importer listener is not observable.")
    _blocker(blockers, established > 0, "established_connections", "An HTTP importer connection is established.")
    _blocker(blockers, not journal_readable, "journal_unreadable", "Importer request history was not readable.")
    _blocker(blockers, unattributed > 0, "unattributed_requests", "Importer requests remain unattributed.")
    _blocker(blockers, active_callers > 0, "active_http_callers", "An active HTTP importer caller remains.")
    _blocker(blockers, later_requests > 0, "later_requests", "Importer requests occurred after the accepted audit.")
    _blocker(blockers, lock_holders > 0, "import_lock_held", "An import transaction lock is held.")
    _blocker(blockers, raw_inputs > 0, "raw_failure_inputs", "A raw importer failure input remains.")
    _blocker(
        blockers,
        not failures_sanitized,
        "failure_records_unsanitized",
        "Importer failure records are not sanitized.",
    )
    _blocker(blockers, import_status != "ready", "import_not_ready", "The formal import status is not ready.")
    _blocker(blockers, transport != "ssh", "adapter_not_ssh", "The installed compatibility adapter is not SSH-backed.")
    _blocker(
        blockers, http_references > 0, "adapter_http_reference", "The active adapter still references HTTP import."
    )
    _blocker(
        blockers,
        not adapter_signed,
        "adapter_unsigned",
        "The active adapter was not verified against a signed artifact.",
    )
    _blocker(blockers, legacy_readers > 0, "legacy_health_readers", "A legacy importer-health reader remains.")
    _blocker(
        blockers,
        not goal_formal,
        "goal_watchdog_legacy_health",
        "The goal watchdog is not on formal Cloudx health.",
    )
    _blocker(
        blockers,
        not exporter_retained,
        "legacy_exporter_missing",
        "The legacy exporter rollback boundary is not retained.",
    )
    _blocker(blockers, required_units > 0, "required_units", "A systemd unit still requires the importer.")
    rollback_messages = {
        "rollback_unit_missing": "The importer unit snapshot is missing.",
        "rollback_runtime_missing": "The importer runtime snapshot is missing.",
        "rollback_token_metadata_missing": "The importer token metadata snapshot is missing.",
        "rollback_failure_receipts_missing": "The importer failure receipt snapshot is missing.",
        "rollback_restore_plan_missing": "The importer restore plan is missing.",
    }
    for code, present in rollback_checks.items():
        _blocker(blockers, not present, code, rollback_messages[code])

    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    accepted = not blockers
    return {
        "schema": RESULT_SCHEMA,
        "scope": "migration-only",
        "capturedAt": captured_raw,
        "evidenceDigest": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "status": "preconditions-satisfied" if accepted else "blocked",
        "preconditionsSatisfied": accepted,
        "automaticAction": False,
        "authorization": {
            "serviceStop": False,
            "required": "separate-operator-confirmation",
        },
        "blockers": blockers,
    }


def evaluate_stream(stream: BinaryIO) -> Dict[str, Any]:
    return evaluate(read_evidence(stream))
