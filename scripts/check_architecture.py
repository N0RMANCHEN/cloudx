#!/usr/bin/env python3
"""Small architecture gate for the Cloudx ownership and safety boundaries."""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from typing import Iterable, List


ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config/governance/architecture_rules.json"

FROZEN_PHI_MESH_TOPOLOGY = {
    "schema": "cloudx.phi-mesh-topology.v1",
    "status": "frozen",
    "trusted_device_ingress": "phi_cloud",
    "normal_cloudx_consumers": ["phi_cloud"],
    "cloudx_role": "gateway_capacity_dependency",
    "cloudx_mesh_control_plane": False,
    "direct_device_to_cloudx": False,
    "synchronized_release_required": False,
    "direct_endpoint_access_requires": [
        "separate_roadmap_milestone",
        "separate_threat_model",
        "separate_credential_contract",
        "operator_approval",
    ],
}


def iter_watched(roots: Iterable[str], suffixes: Iterable[str]) -> Iterable[pathlib.Path]:
    allowed = set(suffixes)
    for name in roots:
        base = ROOT / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in allowed:
                yield path


def relative(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check_phi_mesh_topology(document: object) -> List[str]:
    if document != FROZEN_PHI_MESH_TOPOLOGY:
        return [
            "initial Phi Mesh topology differs from the frozen v1 boundary; "
            "trusted devices must terminate at Phi cloud and Phi cloud must remain "
            "the only normal Cloudx consumer"
        ]
    return []


def check_cloud_public_output_guards() -> List[str]:
    errors: List[str] = []
    guard = ROOT / "cloud/cloudx_cloud/public_metadata.py"
    for path in ROOT.glob("cloud/**/*.py"):
        if path == guard:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append("could not inspect cloud public output path %s: %s" % (relative(path), exc))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                errors.append("cloud public output bypasses metadata guard: %s" % relative(path))
                break
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "write"
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "sys"
                and node.func.value.attr in {"stdout", "stderr"}
            ):
                errors.append("cloud public output bypasses metadata guard: %s" % relative(path))
                break
    for name in (
        "cloud/cloudx_cloud/health.py",
        "cloud/cloudx_cloud/account_state.py",
        "cloud/cloudx_cloud/legacy_health_bridge.py",
    ):
        path = ROOT / name
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if "validate_public_document" not in text:
            errors.append("published Cloudx state lacks metadata guard: %s" % name)
    return errors


def check() -> List[str]:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    errors: List[str] = []

    for name in rules["required_paths"]:
        if not (ROOT / name).exists():
            errors.append("missing required path: %s" % name)

    topology_path = ROOT / rules["phi_mesh_topology_path"]
    if topology_path.is_file():
        topology = json.loads(topology_path.read_text(encoding="utf-8"))
        errors.extend(check_phi_mesh_topology(topology))
    errors.extend(check_cloud_public_output_guards())

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for path in (ROOT / "local/cloudx_local/version.py", ROOT / "cloud/cloudx_cloud/version.py"):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if 'VERSION = "%s"' % version not in text:
            errors.append("endpoint version does not match VERSION: %s" % relative(path))

    frozen = rules.get("frozen_files", {})
    default_limit = int(rules["max_watched_lines"])
    for path in iter_watched(rules["watched_roots"], rules["watched_suffixes"]):
        name = relative(path)
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        limit = int(frozen.get(name, default_limit))
        if line_count > limit:
            errors.append("%s has %d lines; limit is %d" % (name, line_count, limit))

    python_files = list(ROOT.glob("local/**/*.py"))
    for path in python_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(?:from|import)\s+cloud(?:\.|\s|$)", text, re.MULTILINE):
            errors.append("local endpoint imports cloud implementation: %s" % relative(path))

    python_files = list(ROOT.glob("cloud/**/*.py"))
    for path in python_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(?:from|import)\s+local(?:\.|\s|$)", text, re.MULTILINE):
            errors.append("cloud endpoint imports local implementation: %s" % relative(path))

    runtime_roots = [ROOT / "local", ROOT / "cloud", ROOT / "scripts"]
    for base in runtime_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".service", ".timer"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for fragment in rules["forbidden_runtime_fragments"]:
                if fragment in text:
                    errors.append("forbidden runtime fragment %r in %s" % (fragment, relative(path)))
            if re.search(r"^\s*(?:from|import)\s+phi(?:\.|\s|$)", text, re.MULTILINE):
                errors.append("Cloudx runtime depends on Phi: %s" % relative(path))

    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print("architecture: %s" % error, file=sys.stderr)
        return 1
    print("architecture: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
