from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, TextIO, Tuple


LOCAL_CPA_DESTINATION = "local CPA"
CLOUD_DESTINATION = "cloud gateway"
LEGACY_ADAPTER = "migration compatibility (codexx-legacy)"
_LEGACY_COUNT_KEYS = {"discovered", "skipped", "parsed", "duplicates", "imported", "verified"}
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_INPUT_SNIPPET = re.compile(r"(?i)\s+near\s+`[^`]*`")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\b")
_API_TOKEN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_SENSITIVE_VALUE = re.compile(
    r"(?i)([\"']?(?:access_token|refresh_token|id_token|api[_-]?key)[\"']?\s*[:=]\s*)"
    r"[\"']?[^\"'\s,}]+[\"']?"
)


@dataclass(frozen=True)
class ImportReason:
    code: str
    message: str


@dataclass(frozen=True)
class ImportReport:
    status: str
    destination: str
    imported: Optional[int] = None
    skipped: Optional[int] = None
    imported_label: str = "Imported"
    skipped_label: str = "Skipped"
    verification: str = ""
    details: Sequence[Tuple[str, str]] = ()
    reasons: Sequence[ImportReason] = ()
    request_id: str = ""
    adapter: str = ""


def human_output() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def render(report: ImportReport, stream: Optional[TextIO] = None) -> None:
    target = stream if stream is not None else sys.stdout
    print("Credential import", file=target)
    print("  Status: %s" % report.status, file=target)
    print("  Destination: %s" % report.destination, file=target)
    for reason in report.reasons:
        label = "Reason (%s)" % reason.code if reason.code else "Reason"
        print("  %s: %s" % (label, reason.message), file=target)
    if report.imported is not None:
        print("  %s: %d" % (report.imported_label, report.imported), file=target)
    if report.skipped is not None:
        print("  %s: %d" % (report.skipped_label, report.skipped), file=target)
    if report.verification:
        print("  Verification: %s" % report.verification, file=target)
    for label, value in report.details:
        print("  %s: %s" % (label, value), file=target)
    if report.request_id:
        print("  Request ID: %s" % report.request_id, file=target)
    if report.adapter:
        print("  Adapter: %s" % report.adapter, file=target)


def failure_report(destination: str, reason: str, code: str = "") -> ImportReport:
    return ImportReport(
        status="failed",
        destination=destination,
        reasons=(ImportReason(code, sanitize_reason(reason)),),
    )


def _counted(count: int, singular: str, plural: Optional[str] = None) -> str:
    return "%d %s" % (count, singular if count == 1 else (plural or singular + "s"))


def _count(document: Dict[str, Any], name: str) -> int:
    value = document.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError("remote import result has an invalid %s count" % name)
    return value


def _cloud_reasons(document: Dict[str, Any]) -> Sequence[ImportReason]:
    errors = document.get("errors")
    if not isinstance(errors, list):
        raise RuntimeError("remote import result has invalid errors")
    reasons = []
    for error in errors:
        if not isinstance(error, dict):
            raise RuntimeError("remote import result has an invalid error entry")
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        if not code or not message:
            raise RuntimeError("remote import result has an incomplete error entry")
        reasons.append(ImportReason(code, sanitize_reason(message)))
    return tuple(reasons)


def cloud_report(document: Dict[str, Any]) -> ImportReport:
    status = str(document.get("status") or "").strip()
    if status not in ("accepted", "partial", "rejected"):
        raise RuntimeError("remote import result has an unsupported status")
    dry_run = document.get("dryRun")
    if not isinstance(dry_run, bool):
        raise RuntimeError("remote import result has an invalid dry-run flag")
    written = _count(document, "written")
    skipped = _count(document, "skipped")
    reasons = _cloud_reasons(document)
    if status == "accepted" and reasons:
        raise RuntimeError("remote import result reports success with errors")
    if status != "accepted" and not reasons:
        raise RuntimeError("remote import result reports failure without a reason")

    details = []
    if dry_run:
        display_status = "preview succeeded (no changes written)" if status == "accepted" else (
            "preview partially succeeded" if status == "partial" else "preview failed"
        )
        imported_label = "Would import"
        skipped_label = "Would skip"
        verification = "not performed for a preview"
    else:
        if status == "accepted":
            display_status = "succeeded" if written else "succeeded (no changes)"
        elif status == "partial":
            display_status = "partially succeeded"
        else:
            display_status = "failed"
        imported_label = "Imported"
        skipped_label = "Skipped"
        verification = (
            "not performed during import; cloud health checks live account validity separately"
            if status != "rejected"
            else ""
        )
    if skipped:
        verb = "was" if skipped == 1 else "were"
        details.append(
            ("Skip reason", "%s %s already present and identical" % (_counted(skipped, "credential"), verb))
        )
    elif status == "accepted" and written == 0:
        details.append(("Details", "no credential changes were required"))

    request_id = str(document.get("requestId") or "").strip()
    if request_id == "unavailable":
        request_id = ""
    return ImportReport(
        status=display_status,
        destination=CLOUD_DESTINATION,
        imported=written,
        skipped=skipped,
        imported_label=imported_label,
        skipped_label=skipped_label,
        verification=verification,
        details=tuple(details),
        reasons=reasons,
        request_id=request_id,
    )


def _legacy_counts(raw: bytes) -> Optional[Dict[str, int]]:
    text = raw.decode("utf-8", errors="replace")
    counts: Dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*([a-z]+)\s*:\s*([0-9]+)\s*", line)
        if match and match.group(1) in _LEGACY_COUNT_KEYS:
            counts[match.group(1)] = int(match.group(2))
    if not {"parsed", "duplicates", "imported", "verified"}.issubset(counts):
        return None
    return counts


def legacy_success_report(stdout: bytes) -> ImportReport:
    counts = _legacy_counts(stdout)
    if counts is None:
        return ImportReport(
            status="succeeded",
            destination=LOCAL_CPA_DESTINATION,
            verification="reported by the migration compatibility adapter",
            details=(("Details", "adapter completed without standard import counts"),),
            adapter=LEGACY_ADAPTER,
        )
    discovered = counts.get("discovered", 0)
    ignored = counts.get("skipped", 0)
    parsed = counts["parsed"]
    duplicates = counts["duplicates"]
    imported = counts["imported"]
    verified = counts["verified"]
    status = "succeeded" if imported else "succeeded (no changes)"
    details = []
    if "discovered" in counts or "skipped" in counts:
        details.append(("Source files", "%d discovered, %d ignored" % (discovered, ignored)))
    details.append(("Credentials", "%d parsed, %d duplicates" % (parsed, duplicates)))
    if ignored or duplicates:
        details.append(
            (
                "Skip reason",
                "%s, %s"
                % (
                    _counted(ignored, "ignored source file"),
                    _counted(duplicates, "duplicate credential"),
                ),
            )
        )
    verification = "complete (%d verified)" % verified if imported else "complete (no new credentials to verify)"
    return ImportReport(
        status=status,
        destination=LOCAL_CPA_DESTINATION,
        imported=imported,
        skipped=ignored + duplicates,
        verification=verification,
        details=tuple(details),
        adapter=LEGACY_ADAPTER,
    )


def sanitize_reason(value: str) -> str:
    reason = _ANSI_ESCAPE.sub("", str(value or "")).strip()
    for prefix in ("codexx:", "cloudx:", "cloud:"):
        if reason.casefold().startswith(prefix):
            reason = reason[len(prefix):].strip()
            break
    reason = _INPUT_SNIPPET.sub(" near <redacted input>", reason)
    reason = _JWT.sub("<redacted token>", reason)
    reason = _API_TOKEN.sub("<redacted token>", reason)
    reason = _SENSITIVE_VALUE.sub(r"\1<redacted>", reason)
    if len(reason) > 300:
        reason = reason[:297].rstrip() + "..."
    return reason or "import failed without a reported reason"


def legacy_failure_report(returncode: int, stdout: bytes, stderr: bytes) -> ImportReport:
    raw = stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace")
    reasons = []
    for line in raw.splitlines():
        message = sanitize_reason(line)
        if message and message not in {item.message for item in reasons}:
            reasons.append(ImportReason("", message))
        if len(reasons) == 3:
            break
    if not reasons:
        reasons.append(ImportReason("", "migration compatibility adapter exited with status %d" % returncode))
    return ImportReport(
        status="cancelled" if returncode == 130 else "failed",
        destination=LOCAL_CPA_DESTINATION,
        reasons=tuple(reasons),
        adapter=LEGACY_ADAPTER,
    )
