#!/usr/bin/env python3
"""Validate the source-ready legacy health bridge and optional exact Phi N-1 parser."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "config/governance/phi_cloudx_legacy_health_bridge.v1.json"
EVIDENCE_SCHEMA = "cloudx.phi-legacy-health-bridge-evidence.v1"
RESULT_SCHEMA = "cloudx.phi-legacy-health-bridge-check.v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
RUNTIME_BLOCKERS = {
    "signedArtifactPublished": "signed_artifact_not_published",
    "bridgeUnitInstalled": "bridge_unit_not_installed",
    "rollbackRehearsed": "rollback_not_rehearsed",
}


class BridgeEvidenceRejected(RuntimeError):
    pass


def _object(value: Any, keys: Iterable[str], label: str) -> Mapping[str, Any]:
    expected = set(keys)
    if not isinstance(value, dict) or set(value) != expected:
        raise BridgeEvidenceRejected("%s has missing or unknown fields" % label)
    return value


def _text(value: Any, label: str, maximum: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BridgeEvidenceRejected("%s must be bounded text" % label)
    return value.strip()


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise BridgeEvidenceRejected("%s must be boolean" % label)
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise BridgeEvidenceRejected("%s must be an ISO-8601 timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BridgeEvidenceRejected("%s must include a timezone" % label)
    return text


def load_evidence(path: pathlib.Path = DEFAULT_EVIDENCE) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeEvidenceRejected("legacy bridge evidence is unavailable or invalid") from exc
    root = _object(
        document,
        (
            "schema",
            "capturedAt",
            "expectedStatus",
            "cloudx",
            "phiPrevious",
            "sourceAcceptance",
            "runtimeAcceptance",
        ),
        "evidence",
    )
    if root["schema"] != EVIDENCE_SCHEMA:
        raise BridgeEvidenceRejected("legacy bridge evidence schema is unsupported")
    expected_status = _text(root["expectedStatus"], "expectedStatus", 24)
    if expected_status not in {"source-incomplete", "source-ready", "runtime-accepted"}:
        raise BridgeEvidenceRejected("expectedStatus is invalid")
    cloudx = _object(
        root["cloudx"],
        (
            "version",
            "formalSchema",
            "legacyContract",
            "legacySchemaVersion",
            "capability",
            "command",
            "serviceTemplate",
            "timerTemplate",
            "fixedArtifactSelection",
        ),
        "cloudx",
    )
    version = _text(cloudx["version"], "cloudx.version", 32)
    if not VERSION_RE.fullmatch(version):
        raise BridgeEvidenceRejected("cloudx.version is invalid")
    if cloudx["legacySchemaVersion"] != 1 or isinstance(cloudx["legacySchemaVersion"], bool):
        raise BridgeEvidenceRejected("cloudx.legacySchemaVersion is invalid")
    phi = _object(
        root["phiPrevious"],
        ("releaseRef", "consumerFile", "consumerSha256", "healthContract"),
        "phiPrevious",
    )
    release_ref = _text(phi["releaseRef"], "phiPrevious.releaseRef", 40)
    digest = _text(phi["consumerSha256"], "phiPrevious.consumerSha256", 64)
    if not SHA_RE.fullmatch(release_ref) or not DIGEST_RE.fullmatch(digest):
        raise BridgeEvidenceRejected("Phi previous release identity is invalid")
    runtime = _object(root["runtimeAcceptance"], RUNTIME_BLOCKERS, "runtimeAcceptance")
    source_acceptance = _object(
        root["sourceAcceptance"],
        ("exactPhiPreviousParser", "isolatedSelectorRollback"),
        "sourceAcceptance",
    )
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "capturedAt": _timestamp(root["capturedAt"], "capturedAt"),
        "expectedStatus": expected_status,
        "cloudx": {
            "version": version,
            "formalSchema": _text(cloudx["formalSchema"], "cloudx.formalSchema"),
            "legacyContract": _text(cloudx["legacyContract"], "cloudx.legacyContract"),
            "legacySchemaVersion": 1,
            "capability": _text(cloudx["capability"], "cloudx.capability"),
            "command": _text(cloudx["command"], "cloudx.command"),
            "serviceTemplate": _text(cloudx["serviceTemplate"], "cloudx.serviceTemplate"),
            "timerTemplate": _text(cloudx["timerTemplate"], "cloudx.timerTemplate"),
            "fixedArtifactSelection": _boolean(cloudx["fixedArtifactSelection"], "cloudx.fixedArtifactSelection"),
        },
        "phiPrevious": {
            "releaseRef": release_ref,
            "consumerFile": _text(phi["consumerFile"], "phiPrevious.consumerFile", 160),
            "consumerSha256": digest,
            "healthContract": _text(phi["healthContract"], "phiPrevious.healthContract"),
        },
        "sourceAcceptance": {
            "exactPhiPreviousParser": _boolean(
                source_acceptance["exactPhiPreviousParser"],
                "sourceAcceptance.exactPhiPreviousParser",
            ),
            "isolatedSelectorRollback": _boolean(
                source_acceptance["isolatedSelectorRollback"],
                "sourceAcceptance.isolatedSelectorRollback",
            ),
        },
        "runtimeAcceptance": {
            name: _boolean(runtime[name], "runtimeAcceptance.%s" % name)
            for name in RUNTIME_BLOCKERS
        },
    }
    return evidence


def validate_cloudx_source(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT / "cloud"))
    from cloudx_cloud.legacy_health_bridge import validate_legacy_health  # noqa: WPS433

    cloudx = evidence["cloudx"]
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != cloudx["version"]:
        raise BridgeEvidenceRejected("bridge evidence version does not match repository VERSION")
    if (
        cloudx["formalSchema"] != "cloudx.health.v1"
        or cloudx["legacyContract"] != "cloudx.health"
        or cloudx["legacySchemaVersion"] != 1
        or cloudx["capability"] != "legacy-health-bridge.v1"
        or cloudx["command"] != "legacy-health-bridge"
        or cloudx["fixedArtifactSelection"] is not True
    ):
        raise BridgeEvidenceRejected("Cloudx bridge contract identity is invalid")
    example = json.loads(
        (ROOT / "shared/contracts/examples/legacy-health.json").read_text(encoding="utf-8")
    )
    validate_legacy_health(example)
    systemd = ROOT / "cloud/cloudx_cloud/data/systemd"
    service = (systemd / cloudx["serviceTemplate"]).read_text(encoding="utf-8")
    timer = (systemd / cloudx["timerTemplate"]).read_text(encoding="utf-8")
    environment = (systemd / "cloudx-legacy-health-bridge.env.example").read_text(encoding="utf-8")
    required_service = (
        "${CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT} legacy-health-bridge",
        "/run/cloudx/health.json",
        "/var/lib/cloudx/health/v1.json",
        "RestrictAddressFamilies=AF_UNIX",
    )
    if any(fragment not in service for fragment in required_service):
        raise BridgeEvidenceRejected("legacy bridge service template is incomplete")
    if "/opt/cloudx/current" in service or "/home/" in service:
        raise BridgeEvidenceRejected("legacy bridge service is not fixed to immutable release data")
    if "Unit=%s" % cloudx["serviceTemplate"] not in timer:
        raise BridgeEvidenceRejected("legacy bridge timer targets the wrong service")
    expected_artifact = "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % version
    if expected_artifact not in environment:
        raise BridgeEvidenceRejected("legacy bridge environment does not select the source version")
    if not (ROOT / "scripts/rehearse_legacy_health_bridge_rollback.py").is_file():
        raise BridgeEvidenceRejected("legacy bridge rollback rehearsal is unavailable")
    handshake = json.loads((ROOT / "shared/contracts/examples/handshake.json").read_text(encoding="utf-8"))
    if cloudx["capability"] not in handshake.get("capabilities", []):
        raise BridgeEvidenceRejected("handshake example omits the legacy bridge capability")
    profile = json.loads(
        (ROOT / "shared/contracts/examples/phi-mesh-compatibility-profile.json").read_text(encoding="utf-8")
    )
    bridge = profile.get("contracts", {}).get("legacyHealthBridge", {})
    if (
        bridge.get("contract") != cloudx["legacyContract"]
        or bridge.get("sourceSchema") != cloudx["formalSchema"]
        or bridge.get("migrationOnly") is not True
        or bridge.get("automaticInstallation") is not False
    ):
        raise BridgeEvidenceRejected("compatibility profile omits the non-authorizing bridge contract")
    return example


def _git_show(root: pathlib.Path, revision: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), "show", "%s:%s" % (revision, relative)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise BridgeEvidenceRejected("exact Phi previous consumer source is unavailable")
    return completed.stdout


def verify_phi_previous(phi_root: pathlib.Path, evidence: Mapping[str, Any], example: Dict[str, Any]) -> Dict[str, Any]:
    phi = evidence["phiPrevious"]
    source = _git_show(phi_root, phi["releaseRef"], phi["consumerFile"])
    if hashlib.sha256(source).hexdigest() != phi["consumerSha256"]:
        raise BridgeEvidenceRejected("exact Phi previous consumer digest does not match evidence")
    with tempfile.TemporaryDirectory(prefix="cloudx-phi-legacy-bridge-") as value:
        root = pathlib.Path(value)
        module_path = root / "phi_cloudx_health.py"
        module_path.write_bytes(source)
        spec = importlib.util.spec_from_file_location("phi_previous_cloudx_health", module_path)
        if spec is None or spec.loader is None:
            raise BridgeEvidenceRejected("exact Phi previous consumer could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        health_path = root / "legacy-health.json"
        health_path.write_text(json.dumps(example), encoding="utf-8")
        generated = datetime.fromisoformat(str(example["generatedAt"]))
        now = generated + timedelta(seconds=1)
        summary = module.load_health_summary(health_path, now=now)
        snapshot = module.goal_capacity_snapshot(health_path, now=now)
    if summary.get("state") in {"invalid", "incompatible", "stale"}:
        raise BridgeEvidenceRejected("Phi previous consumer rejected the generated legacy health")
    if snapshot.get("state") not in {"healthy", "low_capacity"}:
        raise BridgeEvidenceRejected("Phi previous goal capacity parser rejected the bridge output")
    return {
        "releaseRef": phi["releaseRef"],
        "consumerSha256": phi["consumerSha256"],
        "summaryState": summary.get("state"),
        "capacityState": snapshot.get("state"),
    }


def evaluate(evidence: Mapping[str, Any], phi_verification: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    source_ready = all(evidence["sourceAcceptance"].values())
    blockers = [
        blocker
        for field, blocker in RUNTIME_BLOCKERS.items()
        if evidence["runtimeAcceptance"][field] is not True
    ]
    if not source_ready:
        status = "source-incomplete"
    elif blockers:
        status = "source-ready"
    else:
        status = "runtime-accepted"
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "capturedAt": evidence["capturedAt"],
        "sourceReady": source_ready,
        "sourceAcceptance": dict(evidence["sourceAcceptance"]),
        "phiPreviousVerified": phi_verification is not None,
        "phiPrevious": dict(phi_verification) if phi_verification is not None else None,
        "runtimeAcceptance": dict(evidence["runtimeAcceptance"]),
        "blockers": blockers,
        "automaticAction": False,
        "authorization": {
            "publication": False,
            "unitInstall": False,
            "serviceStart": False,
            "rollback": False,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=pathlib.Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--phi-root", type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-runtime-accepted", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = load_evidence(args.evidence)
        example = validate_cloudx_source(evidence)
        phi_verification = verify_phi_previous(args.phi_root, evidence, example) if args.phi_root else None
        result = evaluate(evidence, phi_verification)
        if result["status"] != evidence["expectedStatus"]:
            raise BridgeEvidenceRejected("computed status does not match expectedStatus")
    except (BridgeEvidenceRejected, OSError, ValueError, TypeError) as exc:
        print("legacy-health-bridge: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("legacy-health-bridge: %s (%d blockers)" % (result["status"], len(result["blockers"])))
    if args.require_runtime_accepted and result["status"] != "runtime-accepted":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
