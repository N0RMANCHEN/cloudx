#!/usr/bin/env python3
"""Validate the Cloudx side of Phi dependency failure semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from check_phi_cloudx_privileged_boundary import (
    EVIDENCE_SCHEMA as PRIVILEGED_BOUNDARY_SCHEMA,
    evaluate as evaluate_privileged_boundary,
    load_evidence as load_privileged_boundary_evidence,
)
from check_phi_cloudx_release_ordering import (
    EVIDENCE_SCHEMA as RELEASE_ORDERING_SCHEMA,
    evaluate as evaluate_release_ordering,
    load_evidence as load_release_ordering_evidence,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "config/governance/phi_cloudx_failure_semantics.v1.json"
EVIDENCE_SCHEMA = "cloudx.phi-failure-semantics-evidence.v1"
RESULT_SCHEMA = "cloudx.phi-failure-semantics-check.v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

PHI_REQUIREMENTS = ["ACCEPT-MESH-CLOUDX-001", "QA-MESH-CLOUDX-DEGRADE-001"]
PHI_ROADMAP_ITEMS = ["INT/P1-1", "CT/P1-3"]
PHI_FILES = [
    "docs/architecture/personal-agent-mesh.md",
    "docs/standards/product-acceptance.md",
    "docs/roadmap/roadmap.json",
]
CONTRACTS = {
    "capacity": "cloudx.capacity.v1",
    "credential": "cloudx.phi-cloud-consumer-credential.v1",
    "traffic": "cloudx.phi-cloud-consumer-traffic-policy.v1",
    "compatibility": "cloudx.phi-mesh-compatibility-profile.v1",
}
GOVERNANCE = {
    "releaseOrdering": RELEASE_ORDERING_SCHEMA,
    "privilegedBoundary": PRIVILEGED_BOUNDARY_SCHEMA,
}
OWNER_MATRIX = {
    "phiOwned": [
        "device",
        "task",
        "session",
        "route",
        "lease",
        "approval",
        "local_action",
        "transfer",
        "model_request_semantics",
        "result_use",
    ],
    "cloudxOwned": [
        "gateway",
        "provider_accounts",
        "account_import",
        "capacity",
        "health",
        "consumer_credential",
        "release",
        "rollback",
    ],
    "cloudxNoVisibility": [
        "phi_task",
        "phi_session",
        "phi_device",
        "phi_lease",
        "phi_approval",
        "local_path",
        "transfer_content",
        "artifact_metadata",
    ],
}
PRESERVED_PHI_TRUTH = [
    "device_registry",
    "task",
    "writer_lease",
    "execution_lease",
    "approval",
    "revocation",
    "notification",
    "completed_local_action_receipt",
]
ALLOWED_PHASE_OUTCOMES = ["continue", "wait", "degrade", "fail"]
EXPECTED_SCENARIOS = [
    {
        "id": "gateway_unavailable",
        "contracts": ["cloudx.capacity.v1"],
        "trigger": "gateway_network_failure",
        "disposition": "probe_failure",
        "permittedPhiPhaseOutcomes": ["wait", "degrade", "fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "capacity_unknown",
        "contracts": ["cloudx.capacity.v1"],
        "trigger": "missing_health_observation",
        "disposition": "unknown_observation",
        "permittedPhiPhaseOutcomes": ["wait", "degrade", "fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "capacity_exhausted",
        "contracts": ["cloudx.capacity.v1"],
        "trigger": "no_available_accounts",
        "disposition": "exhausted_capacity",
        "permittedPhiPhaseOutcomes": ["wait", "fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "stale_health",
        "contracts": ["cloudx.capacity.v1"],
        "trigger": "stale_health_observation",
        "disposition": "stale_contract",
        "permittedPhiPhaseOutcomes": ["wait", "degrade", "fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "incompatible_protocol",
        "contracts": ["cloudx.capacity.v1", "cloudx.phi-mesh-compatibility-profile.v1"],
        "trigger": "protocol_range_mismatch",
        "disposition": "incompatible_producer",
        "permittedPhiPhaseOutcomes": ["fail"],
        "compatibilityGateRequired": True,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "revoked_credential",
        "contracts": ["cloudx.phi-cloud-consumer-credential.v1", "cloudx.capacity.v1"],
        "trigger": "gateway_credential_invalid",
        "disposition": "probe_failure",
        "permittedPhiPhaseOutcomes": ["fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "rate_limit",
        "contracts": ["cloudx.phi-cloud-consumer-traffic-policy.v1"],
        "trigger": "http_429",
        "disposition": "consumer_rate_limited",
        "permittedPhiPhaseOutcomes": ["wait", "fail"],
        "compatibilityGateRequired": False,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "cloudx_rollback",
        "contracts": ["cloudx.phi-mesh-compatibility-profile.v1"],
        "trigger": "cloudx_release_rollback",
        "disposition": "revalidate_current_previous_compatibility",
        "permittedPhiPhaseOutcomes": ["continue", "wait", "degrade", "fail"],
        "compatibilityGateRequired": True,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
    {
        "id": "independent_release_ordering",
        "contracts": ["cloudx.phi-mesh-compatibility-profile.v1"],
        "trigger": "independent_release_change",
        "disposition": "revalidate_before_use",
        "permittedPhiPhaseOutcomes": ["continue", "wait", "degrade", "fail"],
        "compatibilityGateRequired": True,
        "phiTruthMutationAllowed": False,
        "cloudxRuntimeMutationAuthorized": False,
    },
]


class EvidenceRejected(RuntimeError):
    pass


def _object(value: Any, keys: Iterable[str], label: str) -> Mapping[str, Any]:
    expected = set(keys)
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceRejected("%s has missing or unknown fields" % label)
    return value


def _text(value: Any, label: str, maximum: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise EvidenceRejected("%s must be a bounded non-empty string" % label)
    return value.strip()


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceRejected("%s must be boolean" % label)
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise EvidenceRejected("%s must be an ISO-8601 timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceRejected("%s must include a timezone" % label)
    return text


def _text_list(value: Any, label: str, maximum: int = 64) -> List[str]:
    if not isinstance(value, list):
        raise EvidenceRejected("%s must be a list" % label)
    result = [_text(item, "%s[]" % label, maximum) for item in value]
    if len(result) != len(set(result)):
        raise EvidenceRejected("%s must not contain duplicates" % label)
    return result


def _protocol(value: Any, label: str) -> Dict[str, int]:
    document = _object(value, ("min", "max"), label)
    minimum = document["min"]
    maximum = document["max"]
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or minimum < 1
        or maximum < minimum
    ):
        raise EvidenceRejected("%s is invalid" % label)
    return {"min": minimum, "max": maximum}


def _file_records(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        raise EvidenceRejected("phiSnapshot.files must be a list")
    records = []
    for index, item in enumerate(value):
        document = _object(item, ("path", "sha256"), "phiSnapshot.files[%d]" % index)
        path = _text(document["path"], "phiSnapshot.files.path", 128)
        digest = _text(document["sha256"], "phiSnapshot.files.sha256", 64)
        if not SHA256_RE.fullmatch(digest):
            raise EvidenceRejected("phiSnapshot file digest is invalid")
        records.append({"path": path, "sha256": digest})
    if [item["path"] for item in records] != PHI_FILES:
        raise EvidenceRejected("phiSnapshot files do not match the required canonical set")
    return records


def _scenarios(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise EvidenceRejected("scenarios must be a list")
    normalized = []
    keys = (
        "id",
        "contracts",
        "trigger",
        "disposition",
        "permittedPhiPhaseOutcomes",
        "compatibilityGateRequired",
        "phiTruthMutationAllowed",
        "cloudxRuntimeMutationAuthorized",
    )
    for index, item in enumerate(value):
        document = _object(item, keys, "scenarios[%d]" % index)
        normalized.append({
            "id": _text(document["id"], "scenario.id", 64),
            "contracts": _text_list(document["contracts"], "scenario.contracts", 96),
            "trigger": _text(document["trigger"], "scenario.trigger", 96),
            "disposition": _text(document["disposition"], "scenario.disposition", 96),
            "permittedPhiPhaseOutcomes": _text_list(
                document["permittedPhiPhaseOutcomes"], "scenario.permittedPhiPhaseOutcomes", 32
            ),
            "compatibilityGateRequired": _bool(
                document["compatibilityGateRequired"], "scenario.compatibilityGateRequired"
            ),
            "phiTruthMutationAllowed": _bool(
                document["phiTruthMutationAllowed"], "scenario.phiTruthMutationAllowed"
            ),
            "cloudxRuntimeMutationAuthorized": _bool(
                document["cloudxRuntimeMutationAuthorized"],
                "scenario.cloudxRuntimeMutationAuthorized",
            ),
        })
    if normalized != EXPECTED_SCENARIOS:
        raise EvidenceRejected("failure scenario matrix differs from the required v1 semantics")
    return normalized


def load_evidence(path: pathlib.Path = DEFAULT_EVIDENCE) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceRejected("failure-semantics evidence is unavailable or invalid") from exc
    root = _object(
        document,
        ("schema", "capturedAt", "expectedStatus", "phiSnapshot", "cloudx", "invariants", "scenarios", "acceptance"),
        "evidence",
    )
    if root["schema"] != EVIDENCE_SCHEMA:
        raise EvidenceRejected("failure-semantics evidence schema is unsupported")
    expected_status = _text(root["expectedStatus"], "expectedStatus", 16)
    if expected_status not in {"accepted", "blocked"}:
        raise EvidenceRejected("expectedStatus is invalid")

    phi = _object(
        root["phiSnapshot"],
        ("sourceRef", "requirements", "roadmapItems", "roadmapStatuses", "files"),
        "phiSnapshot",
    )
    source_ref = _text(phi["sourceRef"], "phiSnapshot.sourceRef", 40)
    if not SHA_RE.fullmatch(source_ref):
        raise EvidenceRejected("phiSnapshot.sourceRef is invalid")
    requirements = _text_list(phi["requirements"], "phiSnapshot.requirements")
    roadmap_items = _text_list(phi["roadmapItems"], "phiSnapshot.roadmapItems")
    if requirements != PHI_REQUIREMENTS or roadmap_items != PHI_ROADMAP_ITEMS:
        raise EvidenceRejected("Phi requirement or roadmap binding is incomplete")
    statuses = _object(phi["roadmapStatuses"], PHI_ROADMAP_ITEMS, "phiSnapshot.roadmapStatuses")
    roadmap_statuses = {}
    for item_id in PHI_ROADMAP_ITEMS:
        status = _text(statuses[item_id], "phiSnapshot.roadmapStatuses.%s" % item_id, 16)
        if status not in {"planned", "blocked", "in_progress", "complete"}:
            raise EvidenceRejected("Phi roadmap status is invalid")
        roadmap_statuses[item_id] = status

    cloudx = _object(root["cloudx"], ("version", "protocol", "contracts", "governance"), "cloudx")
    version = _text(cloudx["version"], "cloudx.version", 32)
    if not VERSION_RE.fullmatch(version):
        raise EvidenceRejected("cloudx.version is invalid")
    contracts = dict(_object(cloudx["contracts"], CONTRACTS, "cloudx.contracts"))
    governance = dict(_object(cloudx["governance"], GOVERNANCE, "cloudx.governance"))
    if contracts != CONTRACTS or governance != GOVERNANCE:
        raise EvidenceRejected("Cloudx contract or governance binding differs from v1")

    invariants = _object(
        root["invariants"],
        (
            "ownerMatrix",
            "preservedPhiTruth",
            "allowedProviderPhaseOutcomes",
            "cloudxOwnsPhiTruth",
            "synchronizedReleaseRequired",
            "runtimeMutationAuthorized",
            "secretFree",
        ),
        "invariants",
    )
    owner_matrix = dict(_object(invariants["ownerMatrix"], OWNER_MATRIX, "invariants.ownerMatrix"))
    owner_matrix = {
        name: _text_list(owner_matrix[name], "invariants.ownerMatrix.%s" % name)
        for name in OWNER_MATRIX
    }
    if owner_matrix != OWNER_MATRIX:
        raise EvidenceRejected("owner matrix differs from the frozen Phi/Cloudx boundary")
    if _text_list(invariants["preservedPhiTruth"], "invariants.preservedPhiTruth") != PRESERVED_PHI_TRUTH:
        raise EvidenceRejected("preserved Phi truth set is incomplete")
    if _text_list(
        invariants["allowedProviderPhaseOutcomes"], "invariants.allowedProviderPhaseOutcomes"
    ) != ALLOWED_PHASE_OUTCOMES:
        raise EvidenceRejected("provider phase outcome set is invalid")
    if (
        _bool(invariants["cloudxOwnsPhiTruth"], "invariants.cloudxOwnsPhiTruth")
        or _bool(invariants["synchronizedReleaseRequired"], "invariants.synchronizedReleaseRequired")
        or _bool(invariants["runtimeMutationAuthorized"], "invariants.runtimeMutationAuthorized")
        or not _bool(invariants["secretFree"], "invariants.secretFree")
    ):
        raise EvidenceRejected("failure-semantics invariants grant forbidden authority")

    acceptance = _object(root["acceptance"], ("phiRuntimeFixturesAccepted",), "acceptance")
    return {
        "schema": EVIDENCE_SCHEMA,
        "capturedAt": _timestamp(root["capturedAt"], "capturedAt"),
        "expectedStatus": expected_status,
        "phiSnapshot": {
            "sourceRef": source_ref,
            "requirements": requirements,
            "roadmapItems": roadmap_items,
            "roadmapStatuses": roadmap_statuses,
            "files": _file_records(phi["files"]),
        },
        "cloudx": {
            "version": version,
            "protocol": _protocol(cloudx["protocol"], "cloudx.protocol"),
            "contracts": contracts,
            "governance": governance,
        },
        "invariants": {
            "ownerMatrix": owner_matrix,
            "preservedPhiTruth": PRESERVED_PHI_TRUTH,
            "allowedProviderPhaseOutcomes": ALLOWED_PHASE_OUTCOMES,
            "cloudxOwnsPhiTruth": False,
            "synchronizedReleaseRequired": False,
            "runtimeMutationAuthorized": False,
            "secretFree": True,
        },
        "scenarios": _scenarios(root["scenarios"]),
        "acceptance": {
            "phiRuntimeFixturesAccepted": _bool(
                acceptance["phiRuntimeFixturesAccepted"], "acceptance.phiRuntimeFixturesAccepted"
            )
        },
    }


def _load_json(path: pathlib.Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceRejected("%s is unavailable or invalid" % label) from exc
    if not isinstance(value, dict):
        raise EvidenceRejected("%s must be an object" % label)
    return value


def validate_contract_bindings(evidence: Mapping[str, Any]) -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if evidence["cloudx"]["version"] != version:
        raise EvidenceRejected("Cloudx source version differs from failure-semantics evidence")

    capacity = _load_json(ROOT / "shared/contracts/cloudx.capacity.v1.schema.json", "capacity schema")
    properties = capacity.get("properties", {})
    states = set(properties.get("state", {}).get("enum", []))
    reasons = set(properties.get("reason", {}).get("enum", []))
    required_states = {
        "probe_failure",
        "unknown_observation",
        "exhausted_capacity",
        "stale_contract",
        "incompatible_producer",
    }
    required_reasons = {
        "gateway_network_failure",
        "missing_health_observation",
        "no_available_accounts",
        "stale_health_observation",
        "protocol_range_mismatch",
        "gateway_credential_invalid",
    }
    if not required_states.issubset(states) or not required_reasons.issubset(reasons):
        raise EvidenceRejected("capacity contract no longer covers the v1 failure matrix")

    credential = _load_json(
        ROOT / "shared/contracts/examples/phi-cloud-consumer-credential.json", "credential policy"
    )
    denied = set(credential.get("scope", {}).get("deniedOperations", []))
    required_denied = {
        "account_import",
        "gateway_configuration_mutation",
        "release_activation",
        "release_rollback",
        "release_staging",
        "device_identity_assertion",
    }
    if (
        credential.get("lifecycle", {}).get("revocable") is not True
        or credential.get("enforcement", {}).get("cloudxAuthRead") is not False
        or not required_denied.issubset(denied)
    ):
        raise EvidenceRejected("credential policy no longer provides scoped revocation semantics")

    traffic = _load_json(
        ROOT / "shared/contracts/examples/phi-cloud-consumer-traffic-policy.json", "traffic policy"
    )
    if (
        429 not in traffic.get("retry", {}).get("retryableHttpStatuses", [])
        or traffic.get("retry", {}).get("maxAttempts") != 3
        or traffic.get("limits", {}).get("everyAttemptConsumesRateBudget") is not True
        or traffic.get("outcomes", {}).get("rateLimited") != "consumer_rate_limited"
    ):
        raise EvidenceRejected("traffic policy no longer provides bounded rate-limit semantics")

    compatibility = _load_json(
        ROOT / "shared/contracts/examples/phi-mesh-compatibility-profile.json",
        "compatibility profile",
    )
    if (
        compatibility.get("protocol") != evidence["cloudx"]["protocol"]
        or compatibility.get("compatibility", {}).get("independentReleaseOrdering") is not True
        or compatibility.get("compatibility", {}).get("synchronizedDeploymentRequired") is not False
        or compatibility.get("contracts", {}).get("rollback", {}).get("currentAndPreviousRequired") is not True
    ):
        raise EvidenceRejected("compatibility profile no longer provides independent rollback semantics")


def _git_head(root: pathlib.Path) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise EvidenceRejected("Phi snapshot root is not a readable Git checkout")
    return process.stdout.strip()


def verify_phi_snapshot(evidence: Mapping[str, Any], phi_root: pathlib.Path) -> bool:
    root = phi_root.resolve()
    snapshot = evidence["phiSnapshot"]
    if _git_head(root) != snapshot["sourceRef"]:
        raise EvidenceRejected("Phi checkout HEAD differs from the recorded snapshot")
    for record in snapshot["files"]:
        path = (root / record["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise EvidenceRejected("Phi snapshot path escapes its checkout") from exc
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise EvidenceRejected("Phi snapshot file is unavailable") from exc
        if len(payload) > 2 * 1024 * 1024:
            raise EvidenceRejected("Phi snapshot file exceeds the audit bound")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise EvidenceRejected("Phi snapshot file digest differs from recorded evidence")

    roadmap = _load_json(root / "docs/roadmap/roadmap.json", "Phi roadmap")
    items = roadmap.get("items")
    if not isinstance(items, list):
        raise EvidenceRejected("Phi roadmap items are invalid")
    statuses = {
        item.get("id"): item.get("status")
        for item in items
        if isinstance(item, dict) and item.get("id") in PHI_ROADMAP_ITEMS
    }
    if statuses != snapshot["roadmapStatuses"]:
        raise EvidenceRejected("Phi roadmap statuses differ from recorded evidence")
    return True


def evaluate(
    evidence: Mapping[str, Any],
    release_result: Optional[Mapping[str, Any]] = None,
    privileged_result: Optional[Mapping[str, Any]] = None,
    phi_snapshot_verified: bool = False,
) -> Dict[str, Any]:
    validate_contract_bindings(evidence)
    release = release_result or evaluate_release_ordering(load_release_ordering_evidence())
    privileged = privileged_result or evaluate_privileged_boundary(load_privileged_boundary_evidence())
    blockers = []
    if release.get("status") != "compatible":
        blockers.append("release_ordering_not_compatible")
    if privileged.get("status") != "secure":
        blockers.append("privileged_boundary_not_secure")
    for item_id, status in evidence["phiSnapshot"]["roadmapStatuses"].items():
        if status != "complete":
            normalized_id = item_id.lower().replace("/", "_").replace("-", "_")
            blockers.append("phi_%s_not_complete" % normalized_id)
    if not evidence["acceptance"]["phiRuntimeFixturesAccepted"]:
        blockers.append("phi_runtime_fixtures_not_accepted")
    status = "accepted" if not blockers else "blocked"
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "capturedAt": evidence["capturedAt"],
        "cloudxContractMatrixReady": True,
        "scenarioCount": len(evidence["scenarios"]),
        "scenarioIds": [item["id"] for item in evidence["scenarios"]],
        "releaseOrderingStatus": release.get("status"),
        "privilegedBoundaryStatus": privileged.get("status"),
        "phiRoadmapStatuses": evidence["phiSnapshot"]["roadmapStatuses"],
        "phiSnapshotVerified": phi_snapshot_verified,
        "crossRepositoryRuntimeAccepted": status == "accepted",
        "blockers": blockers,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=pathlib.Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--phi-root", type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-accepted", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = load_evidence(args.evidence)
        phi_snapshot_verified = bool(args.phi_root) and verify_phi_snapshot(evidence, args.phi_root)
        result = evaluate(evidence, phi_snapshot_verified=phi_snapshot_verified)
        if result["status"] != evidence["expectedStatus"]:
            raise EvidenceRejected("computed status does not match expectedStatus")
    except EvidenceRejected as exc:
        print("phi-failure-semantics: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        snapshot = "verified" if result["phiSnapshotVerified"] else "recorded"
        print(
            "phi-failure-semantics: %s (%d blockers; %d scenarios; phi-snapshot=%s)"
            % (result["status"], len(result["blockers"]), result["scenarioCount"], snapshot)
        )
    if args.require_accepted and result["status"] != "accepted":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
