from __future__ import annotations

import pathlib
import re
from typing import Any, Callable, Dict

import import_active_cloud_cpa_credential as base


ACTIVE_CLOUDX_VERSION = "0.1.33"
REQUIRED_CPA_VERSION = "7.2.71-cloudx-policy.8"
REQUIRED_CPA_SHA256 = "4dfa561451662ca5deae566f6fcfdc32bec7f42590439fa053000c4b84f915c0"
REQUIRED_CAPABILITY = "codex-agent-identity-v1"
PLAN_SCHEMA = "cloudx.active-agent-identity-promotion-plan.v1"
RESULT_SCHEMA = "cloudx.active-agent-identity-promotion.v1"
MAX_BATCH = 32
TRANSACTION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


Rejected = base.ActiveImportRejected


def confirmation(
    expected_sha256: str,
    expected_active: int,
    expected_new: int,
    allow_unavailable_baseline: bool = False,
) -> str:
    action = "RECOVER UNAVAILABLE CLOUD AGENT IDENTITY BATCH" if allow_unavailable_baseline else "PROMOTE CLOUD AGENT IDENTITY BATCH"
    return "%s %s %d+%d %s" % (
        action,
        ACTIVE_CLOUDX_VERSION,
        expected_active,
        expected_new,
        expected_sha256[:16],
    )


def recovery_confirmation(transaction_id: str) -> str:
    return "ROLL BACK CLOUD AGENT IDENTITY PROMOTION %s" % transaction_id


def validate_expectations(expected_sha256: str, expected_active: int, expected_new: int) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise Rejected("invalid_arguments", "expected request SHA-256 is invalid")
    if expected_active < 1 or expected_active > 128:
        raise Rejected("invalid_arguments", "expected active count is invalid")
    if expected_new < 1 or expected_new > MAX_BATCH:
        raise Rejected("invalid_arguments", "expected batch count is invalid")


def plan(
    expected_sha256: str,
    expected_active: int,
    expected_new: int,
    allow_unavailable_baseline: bool = False,
) -> Dict[str, Any]:
    validate_expectations(expected_sha256, expected_active, expected_new)
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": confirmation(
            expected_sha256, expected_active, expected_new, allow_unavailable_baseline
        ),
        "requiredActiveCloudxVersion": ACTIVE_CLOUDX_VERSION,
        "requiredCpaVersion": REQUIRED_CPA_VERSION,
        "requiredCpaSha256": REQUIRED_CPA_SHA256,
        "requiredCapability": REQUIRED_CAPABILITY,
        "requestSha256": expected_sha256,
        "activeBefore": expected_active,
        "newCredentials": expected_new,
        "activeAfter": expected_active + expected_new,
        "baselinePoolStateRequired": "unavailable" if allow_unavailable_baseline else "available",
        "signedImporterDryRun": True,
        "signedImporterApply": True,
        "baselineTemporarilyHeldForCohortCanary": True,
        "cohortCanaryRequests": expected_new,
        "automaticRollback": True,
        "manualRecoveryPreparedBeforeMutation": True,
        "rawCredentialStored": False,
        "serviceRestarted": False,
        "automaticAction": False,
    }


def recovery_plan(transaction_id: str) -> Dict[str, Any]:
    if not TRANSACTION_RE.fullmatch(transaction_id):
        raise Rejected("invalid_arguments", "transaction ID is invalid")
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": recovery_confirmation(transaction_id),
        "transactionId": transaction_id,
        "action": "restore-pre-promotion-active-pool",
        "serviceRestarted": False,
        "automaticAction": False,
    }


def pool_observation_state(
    root: pathlib.Path,
    json_file: Callable[[pathlib.Path, int], Dict[str, Any]],
) -> str:
    files = base.regular_files(root)
    if len(files) != 1 or files[0].name != "pool-state.json":
        raise Rejected("observation_invalid", "CPA pool observation inventory is invalid")
    document = json_file(files[0], 16 * 1024)
    if (
        document.get("schema") != "cloudx.cpa-pool-observation.v1"
        or document.get("state") not in ("available", "unavailable")
        or not isinstance(document.get("observedAt"), str)
        or set(document) != {"schema", "state", "observedAt"}
    ):
        raise Rejected("observation_invalid", "CPA pool observation is not identity-free state")
    return str(document["state"])


def verify_baseline_behavior(
    host: str,
    port: int,
    state: str,
    canaries: Callable[[str, int, int], Dict[str, int]],
) -> bool:
    if state == "available":
        return canaries(host, port, 1)["requests"] == 1
    if state != "unavailable":
        raise Rejected("recovery_incomplete", "promotion baseline state is invalid")
    try:
        base.live_canary(host, port)
    except Rejected as exc:
        result = exc.result or {}
        if exc.code == "live_model_failed" and result.get("httpStatus") == 503:
            return True
        raise Rejected("recovery_incomplete", "unavailable baseline behavior changed") from exc
    raise Rejected("recovery_incomplete", "unavailable baseline unexpectedly became usable")
