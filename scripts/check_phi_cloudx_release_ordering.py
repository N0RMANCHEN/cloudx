#!/usr/bin/env python3
"""Validate current/N-1 Phi and Cloudx compatibility and release ordering evidence."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "config/governance/phi_cloudx_release_ordering.v1.json"
EVIDENCE_SCHEMA = "cloudx.phi-release-ordering-evidence.v1"
RESULT_SCHEMA = "cloudx.phi-release-ordering-check.v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ORDER_STATES: Mapping[str, Sequence[Tuple[str, str]]] = {
    "cloudx_first_upgrade": (
        ("previous", "previous"),
        ("current", "previous"),
        ("current", "current"),
    ),
    "phi_first_upgrade": (
        ("previous", "previous"),
        ("previous", "current"),
        ("current", "current"),
    ),
    "cloudx_rollback": (("current", "current"), ("previous", "current")),
    "phi_rollback": (("current", "current"), ("current", "previous")),
}


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


def _cloudx_release(value: Any, label: str) -> Dict[str, Any]:
    document = _object(value, ("version", "sourceRef", "protocol", "healthContract"), label)
    version = _text(document["version"], "%s.version" % label, 32)
    source_ref = _text(document["sourceRef"], "%s.sourceRef" % label, 40)
    if not VERSION_RE.fullmatch(version) or not SHA_RE.fullmatch(source_ref):
        raise EvidenceRejected("%s release identity is invalid" % label)
    return {
        "version": version,
        "sourceRef": source_ref,
        "protocol": _protocol(document["protocol"], "%s.protocol" % label),
        "healthContract": _text(document["healthContract"], "%s.healthContract" % label),
    }


def _phi_release(value: Any, label: str) -> Dict[str, Any]:
    document = _object(value, ("releaseRef", "consumerProtocol", "healthContract"), label)
    release_ref = _text(document["releaseRef"], "%s.releaseRef" % label, 40)
    if not SHA_RE.fullmatch(release_ref):
        raise EvidenceRejected("%s release identity is invalid" % label)
    return {
        "releaseRef": release_ref,
        "consumerProtocol": _protocol(document["consumerProtocol"], "%s.consumerProtocol" % label),
        "healthContract": _text(document["healthContract"], "%s.healthContract" % label),
    }


def load_evidence(path: pathlib.Path = DEFAULT_EVIDENCE) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceRejected("release-ordering evidence is unavailable or invalid") from exc
    root = _object(document, ("schema", "capturedAt", "expectedStatus", "cloudx", "phi"), "evidence")
    if root["schema"] != EVIDENCE_SCHEMA:
        raise EvidenceRejected("release-ordering evidence schema is unsupported")
    expected = _text(root["expectedStatus"], "expectedStatus", 16)
    if expected not in {"compatible", "blocked"}:
        raise EvidenceRejected("expectedStatus is invalid")
    cloudx_raw = _object(root["cloudx"], ("current", "previous"), "cloudx")
    phi_raw = _object(root["phi"], ("current", "previous"), "phi")
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "capturedAt": _timestamp(root["capturedAt"], "capturedAt"),
        "expectedStatus": expected,
        "cloudx": {
            name: _cloudx_release(cloudx_raw[name], "cloudx.%s" % name)
            for name in ("current", "previous")
        },
        "phi": {
            name: _phi_release(phi_raw[name], "phi.%s" % name)
            for name in ("current", "previous")
        },
    }
    if tuple(int(part) for part in evidence["cloudx"]["current"]["version"].split(".")) <= tuple(
        int(part) for part in evidence["cloudx"]["previous"]["version"].split(".")
    ):
        raise EvidenceRejected("Cloudx current release must be newer than previous")
    if evidence["cloudx"]["current"]["sourceRef"] == evidence["cloudx"]["previous"]["sourceRef"]:
        raise EvidenceRejected("Cloudx current and previous source refs must differ")
    if evidence["phi"]["current"]["releaseRef"] == evidence["phi"]["previous"]["releaseRef"]:
        raise EvidenceRejected("Phi current and previous release refs must differ")
    return evidence


def _overlap(producer: Mapping[str, int], consumer: Mapping[str, int]) -> bool:
    return max(producer["min"], consumer["min"]) <= min(producer["max"], consumer["max"])


def evaluate(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    matrix: List[Dict[str, Any]] = []
    by_pair: Dict[Tuple[str, str], bool] = {}
    blockers: List[str] = []
    for cloudx_name in ("current", "previous"):
        for phi_name in ("current", "previous"):
            cloudx = evidence["cloudx"][cloudx_name]
            phi = evidence["phi"][phi_name]
            reasons = []
            if not _overlap(cloudx["protocol"], phi["consumerProtocol"]):
                reasons.append("protocol_range_mismatch")
            if cloudx["healthContract"] != phi["healthContract"]:
                reasons.append("health_contract_mismatch")
            compatible = not reasons
            by_pair[(cloudx_name, phi_name)] = compatible
            matrix.append({
                "cloudxRelease": cloudx_name,
                "phiRelease": phi_name,
                "compatible": compatible,
                "reasons": reasons,
            })
            for reason in reasons:
                blocker = "%s_%s_%s" % (cloudx_name, phi_name, reason)
                if blocker not in blockers:
                    blockers.append(blocker)

    orders = []
    for name, states in ORDER_STATES.items():
        orders.append({
            "name": name,
            "compatible": all(by_pair[state] for state in states),
            "states": [
                {"cloudxRelease": cloudx_name, "phiRelease": phi_name}
                for cloudx_name, phi_name in states
            ],
        })
    status = "compatible" if all(item["compatible"] for item in orders) else "blocked"
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "capturedAt": evidence["capturedAt"],
        "matrix": matrix,
        "orders": orders,
        "blockers": blockers,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=pathlib.Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-compatible", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = load_evidence(args.evidence)
        result = evaluate(evidence)
        if result["status"] != evidence["expectedStatus"]:
            raise EvidenceRejected("computed status does not match expectedStatus")
    except EvidenceRejected as exc:
        print("release-ordering: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("release-ordering: %s (%d blockers)" % (result["status"], len(result["blockers"])))
    if args.require_compatible and result["status"] != "compatible":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
