#!/usr/bin/env python3
"""Validate secret-free evidence for the Phi-to-Cloudx privileged boundary."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "config/governance/phi_cloudx_privileged_boundary.v1.json"
EVIDENCE_SCHEMA = "cloudx.phi-privileged-boundary-evidence.v1"
RESULT_SCHEMA = "cloudx.phi-privileged-boundary-check.v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
CAPABILITY_NAMES = ("authRead", "importInvoke", "gatewayMutate", "releaseMutate")
REQUIRED_SURFACES = {"interactive_cli", "mail_command", "orchestrator"}
CAPABILITY_BLOCKERS = {
    "authRead": "auth_read",
    "importInvoke": "import_invoke",
    "gatewayMutate": "gateway_mutate",
    "releaseMutate": "release_mutate",
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


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceRejected("%s must be a boolean" % label)
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


def _capabilities(value: Any, label: str) -> Dict[str, bool]:
    document = _object(value, CAPABILITY_NAMES, label)
    return {
        name: _boolean(document[name], "%s.%s" % (label, name))
        for name in CAPABILITY_NAMES
    }


def _identity(value: Any, label: str) -> Dict[str, Any]:
    document = _object(value, ("name", "elevation", "elevatedCapabilities"), label)
    name = _text(document["name"], "%s.name" % label, 32)
    if not NAME_RE.fullmatch(name):
        raise EvidenceRejected("%s.name is invalid" % label)
    elevation = _text(document["elevation"], "%s.elevation" % label, 32)
    if elevation not in {"none", "scoped", "unrestricted_root"}:
        raise EvidenceRejected("%s.elevation is invalid" % label)
    capabilities = _capabilities(
        document["elevatedCapabilities"], "%s.elevatedCapabilities" % label
    )
    if elevation == "none" and any(capabilities.values()):
        raise EvidenceRejected("%s declares elevated capabilities without elevation" % label)
    if elevation == "unrestricted_root" and not all(capabilities.values()):
        raise EvidenceRejected("%s unrestricted root capabilities are incomplete" % label)
    return {
        "name": name,
        "elevation": elevation,
        "elevatedCapabilities": capabilities,
    }


def _surface(value: Any, label: str) -> Dict[str, Any]:
    document = _object(
        value,
        (
            "name",
            "available",
            "agentControlsCommands",
            "arbitraryCommandExecution",
            "identity",
            "noNewPrivileges",
            "cloudxSensitivePathsMasked",
            "directCapabilities",
        ),
        label,
    )
    name = _text(document["name"], "%s.name" % label, 32)
    identity = _text(document["identity"], "%s.identity" % label, 32)
    if not NAME_RE.fullmatch(name) or not NAME_RE.fullmatch(identity):
        raise EvidenceRejected("%s name or identity is invalid" % label)
    agent_controls = _boolean(
        document["agentControlsCommands"], "%s.agentControlsCommands" % label
    )
    arbitrary = _boolean(
        document["arbitraryCommandExecution"], "%s.arbitraryCommandExecution" % label
    )
    if arbitrary and not agent_controls:
        raise EvidenceRejected("%s cannot expose arbitrary commands without Agent control" % label)
    return {
        "name": name,
        "available": _boolean(document["available"], "%s.available" % label),
        "agentControlsCommands": agent_controls,
        "arbitraryCommandExecution": arbitrary,
        "identity": identity,
        "noNewPrivileges": _boolean(
            document["noNewPrivileges"], "%s.noNewPrivileges" % label
        ),
        "cloudxSensitivePathsMasked": _boolean(
            document["cloudxSensitivePathsMasked"],
            "%s.cloudxSensitivePathsMasked" % label,
        ),
        "directCapabilities": _capabilities(
            document["directCapabilities"], "%s.directCapabilities" % label
        ),
    }


def load_evidence(path: pathlib.Path = DEFAULT_EVIDENCE) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceRejected("privileged-boundary evidence is unavailable or invalid") from exc
    root = _object(
        document,
        (
            "schema",
            "capturedAt",
            "expectedStatus",
            "deployedRefs",
            "consumerCredential",
            "identities",
            "agentSurfaces",
        ),
        "evidence",
    )
    if root["schema"] != EVIDENCE_SCHEMA:
        raise EvidenceRejected("privileged-boundary evidence schema is unsupported")
    expected = _text(root["expectedStatus"], "expectedStatus", 16)
    if expected not in {"secure", "blocked"}:
        raise EvidenceRejected("expectedStatus is invalid")

    refs_raw = _object(
        root["deployedRefs"], ("agentRuntime", "mailCommand", "orchestrator"), "deployedRefs"
    )
    refs = {}
    for name, value in refs_raw.items():
        ref = _text(value, "deployedRefs.%s" % name, 40)
        if not SHA_RE.fullmatch(ref):
            raise EvidenceRejected("deployedRefs.%s is invalid" % name)
        refs[name] = ref

    credential_raw = _object(
        root["consumerCredential"], ("class", "privilegeElevation"), "consumerCredential"
    )
    credential_class = _text(credential_raw["class"], "consumerCredential.class", 40)
    if credential_class not in {"scoped_phi_consumer", "cloudx_admin_gateway_key"}:
        raise EvidenceRejected("consumerCredential.class is invalid")
    credential_elevation = _boolean(
        credential_raw["privilegeElevation"], "consumerCredential.privilegeElevation"
    )
    if credential_class == "scoped_phi_consumer" and credential_elevation:
        raise EvidenceRejected("scoped Phi consumer credential cannot require elevation")

    if not isinstance(root["identities"], list) or not 1 <= len(root["identities"]) <= 8:
        raise EvidenceRejected("identities must be a bounded non-empty list")
    identities = [
        _identity(value, "identities[%d]" % index)
        for index, value in enumerate(root["identities"])
    ]
    identity_names = [item["name"] for item in identities]
    if len(set(identity_names)) != len(identity_names):
        raise EvidenceRejected("identity names must be unique")

    if not isinstance(root["agentSurfaces"], list) or not 1 <= len(root["agentSurfaces"]) <= 12:
        raise EvidenceRejected("agentSurfaces must be a bounded non-empty list")
    surfaces = [
        _surface(value, "agentSurfaces[%d]" % index)
        for index, value in enumerate(root["agentSurfaces"])
    ]
    surface_names = [item["name"] for item in surfaces]
    if len(set(surface_names)) != len(surface_names):
        raise EvidenceRejected("Agent surface names must be unique")
    if set(surface_names) != REQUIRED_SURFACES:
        raise EvidenceRejected("Agent surface inventory is incomplete or unknown")
    unknown_identities = sorted({item["identity"] for item in surfaces} - set(identity_names))
    if unknown_identities:
        raise EvidenceRejected("Agent surface references an unknown identity")

    return {
        "schema": EVIDENCE_SCHEMA,
        "capturedAt": _timestamp(root["capturedAt"], "capturedAt"),
        "expectedStatus": expected,
        "deployedRefs": refs,
        "consumerCredential": {
            "class": credential_class,
            "privilegeElevation": credential_elevation,
        },
        "identities": identities,
        "agentSurfaces": surfaces,
    }


def evaluate(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    identities = {item["name"]: item for item in evidence["identities"]}
    blockers: List[str] = []
    credential = evidence["consumerCredential"]
    credential_scoped = (
        credential["class"] == "scoped_phi_consumer"
        and not credential["privilegeElevation"]
    )
    if not credential_scoped:
        blockers.append("consumer_credential_not_scoped")

    surfaces = []
    for surface in evidence["agentSurfaces"]:
        identity = identities[surface["identity"]]
        effective = dict(surface["directCapabilities"])
        elevation_reachable = (
            surface["available"]
            and surface["agentControlsCommands"]
            and surface["arbitraryCommandExecution"]
            and not surface["noNewPrivileges"]
            and identity["elevation"] != "none"
        )
        if elevation_reachable:
            for name in CAPABILITY_NAMES:
                effective[name] = effective[name] or identity["elevatedCapabilities"][name]
        surface_blockers = []
        if surface["available"] and surface["agentControlsCommands"]:
            surface_blockers = [
                "%s_%s" % (surface["name"], CAPABILITY_BLOCKERS[name])
                for name in CAPABILITY_NAMES
                if effective[name]
            ]
            blockers.extend(surface_blockers)
        surfaces.append({
            "name": surface["name"],
            "available": surface["available"],
            "cloudxSensitivePathsMasked": surface["cloudxSensitivePathsMasked"],
            "noNewPrivileges": surface["noNewPrivileges"],
            "elevationReachable": elevation_reachable,
            "effectiveCapabilities": effective,
            "blockers": surface_blockers,
        })

    return {
        "schema": RESULT_SCHEMA,
        "status": "secure" if not blockers else "blocked",
        "capturedAt": evidence["capturedAt"],
        "credentialScoped": credential_scoped,
        "surfaces": surfaces,
        "blockers": blockers,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=pathlib.Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-secure", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = load_evidence(args.evidence)
        result = evaluate(evidence)
        if result["status"] != evidence["expectedStatus"]:
            raise EvidenceRejected("computed status does not match expectedStatus")
    except EvidenceRejected as exc:
        print("phi-privileged-boundary: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "phi-privileged-boundary: %s (%d blockers)"
            % (result["status"], len(result["blockers"]))
        )
    if args.require_secure and result["status"] != "secure":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
