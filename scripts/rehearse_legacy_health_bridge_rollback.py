#!/usr/bin/env python3
"""Rehearse the fixed-artifact legacy health bridge across isolated Cloudx rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

import build as build_module  # noqa: E402
from check_phi_cloudx_legacy_health_bridge import (  # noqa: E402
    load_evidence as load_bridge_evidence,
    verify_phi_previous,
)
from cloudx_cloud import release as cloud_release  # noqa: E402


SCHEMA = "cloudx.legacy-health-bridge-rollback-rehearsal.v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")


class RehearsalRejected(RuntimeError):
    pass


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit() -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    value = completed.stdout.strip().lower()
    if completed.returncode != 0 or not SHA_RE.fullmatch(value):
        raise RehearsalRejected("repository source commit is unavailable")
    return value


def _seed_release(root: pathlib.Path, version: str) -> pathlib.Path:
    release = root / "releases" / version
    release.mkdir(parents=True)
    artifact = release / "cloudx-cloud.pyz"
    artifact.write_bytes(("isolated rollback placeholder %s\n" % version).encode("utf-8"))
    artifact.chmod(0o755)
    return release


def _selector(root: pathlib.Path, name: str, target: pathlib.Path) -> None:
    link = root / name
    link.symlink_to(target, target_is_directory=True)


def _selector_state(root: pathlib.Path) -> Dict[str, str]:
    values = {}
    for name in ("current", "previous"):
        path = root / name
        if not path.is_symlink():
            raise RehearsalRejected("isolated %s selector is missing" % name)
        target = path.resolve()
        if target.parent != (root / "releases").resolve():
            raise RehearsalRejected("isolated selector escapes the release root")
        values[name] = target.name
    return values


def _run_json(
    command: List[str],
    *,
    environment: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise RehearsalRejected("candidate bridge command failed")
    try:
        document = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RehearsalRejected("candidate bridge returned invalid JSON") from exc
    if not isinstance(document, dict):
        raise RehearsalRejected("candidate bridge returned a non-object")
    return document


def _run_bridge(
    artifact: pathlib.Path,
    source: pathlib.Path,
    output: pathlib.Path,
) -> Tuple[Dict[str, Any], bytes]:
    environment = dict(os.environ)
    environment["CLOUDX_BUILD_COMMIT"] = "unknown"
    document = _run_json(
        [
            sys.executable,
            str(artifact),
            "legacy-health-bridge",
            "--source",
            str(source),
            "--publish-to",
            str(output),
        ],
        environment=environment,
    )
    persisted = output.read_bytes()
    if json.loads(persisted) != document:
        raise RehearsalRejected("candidate bridge stdout and persisted output differ")
    return document, persisted


def _rollback(root: pathlib.Path, confirmation: str) -> Dict[str, Any]:
    previous = os.environ.get("CLOUDX_RELEASE_ROOT")
    os.environ["CLOUDX_RELEASE_ROOT"] = str(root)
    try:
        return cloud_release.rollback(confirmation)
    finally:
        if previous is None:
            os.environ.pop("CLOUDX_RELEASE_ROOT", None)
        else:
            os.environ["CLOUDX_RELEASE_ROOT"] = previous


def rehearse(phi_root: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    source_commit = _source_commit()
    with tempfile.TemporaryDirectory(prefix="cloudx-legacy-bridge-rollback-") as value:
        root = pathlib.Path(value)
        release_root = root / "cloudx"
        current_release = _seed_release(release_root, "0.1.13")
        previous_release = _seed_release(release_root, "0.1.12")
        candidate_release = release_root / "releases" / version
        candidate_release.mkdir()
        built = build_module.build_component("cloud", root / "build", version)
        bridge_artifact = candidate_release / "cloudx-cloud.pyz"
        shutil.copy2(built, bridge_artifact)
        bridge_artifact.chmod(0o755)
        self_check = _run_json([sys.executable, str(bridge_artifact), "self-check"])
        if self_check.get("status") != "ok" or self_check.get("version") != version:
            raise RehearsalRejected("candidate bridge artifact self-check failed")

        _selector(release_root, "current", current_release)
        _selector(release_root, "previous", previous_release)
        formal = root / "formal-health.json"
        shutil.copy2(ROOT / "shared/contracts/examples/health.json", formal)
        legacy = root / "legacy-health.json"

        selectors: List[Dict[str, str]] = []
        documents: List[Dict[str, Any]] = []
        payloads: List[bytes] = []
        selectors.append(_selector_state(release_root))
        document, payload = _run_bridge(bridge_artifact, formal, legacy)
        documents.append(document)
        payloads.append(payload)

        first_rollback = _rollback(release_root, "0.1.12")
        if first_rollback.get("status") != "active":
            raise RehearsalRejected("isolated rollback did not activate the previous release")
        selectors.append(_selector_state(release_root))
        document, payload = _run_bridge(bridge_artifact, formal, legacy)
        documents.append(document)
        payloads.append(payload)

        second_rollback = _rollback(release_root, "0.1.13")
        if second_rollback.get("status") != "active":
            raise RehearsalRejected("isolated rollback did not restore the original release")
        selectors.append(_selector_state(release_root))
        document, payload = _run_bridge(bridge_artifact, formal, legacy)
        documents.append(document)
        payloads.append(payload)

        expected_selectors = [
            {"current": "0.1.13", "previous": "0.1.12"},
            {"current": "0.1.12", "previous": "0.1.13"},
            {"current": "0.1.13", "previous": "0.1.12"},
        ]
        if selectors != expected_selectors:
            raise RehearsalRejected("isolated selector round trip differs from the expected order")
        if len(set(payloads)) != 1 or any(document != documents[0] for document in documents[1:]):
            raise RehearsalRejected("bridge output changed across isolated selector rollback")
        if bridge_artifact.resolve().parent == (release_root / "current").resolve():
            raise RehearsalRejected("bridge artifact incorrectly follows the current selector")

        phi_verification = None
        if phi_root is not None:
            evidence = load_bridge_evidence()
            phi_verification = verify_phi_previous(phi_root, evidence, documents[-1])
        result = {
            "schema": SCHEMA,
            "status": "passed",
            "version": version,
            "sourceCommit": source_commit,
            "artifactSha256": _sha256(bridge_artifact),
            "legacyOutputSha256": hashlib.sha256(payloads[0]).hexdigest(),
            "selectors": selectors,
            "rollbackRoundTrip": True,
            "fixedArtifactIndependent": True,
            "outputByteStable": True,
            "phiPreviousVerified": phi_verification is not None,
            "phiPrevious": phi_verification,
            "automaticAction": False,
            "authorization": {
                "publication": False,
                "endpointStage": False,
                "unitInstall": False,
                "serviceStart": False,
                "productionSelectorMutation": False,
            },
        }
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phi-root", type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = rehearse(args.phi_root)
    except (OSError, ValueError, RehearsalRejected) as exc:
        print("legacy-health-bridge-rehearsal: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("legacy-health-bridge-rehearsal: passed (3 selector states)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
