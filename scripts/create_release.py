#!/usr/bin/env python3
"""Create immutable artifacts, a manifest, signature, and offline bundle."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build import build_all  # noqa: E402
from release_lib import RELEASE_NAMESPACE, artifact_record  # noqa: E402


def source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "uncommitted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "dist/release")
    parser.add_argument("--signing-key", type=pathlib.Path, required=True)
    parser.add_argument("--allowed-signers", type=pathlib.Path, required=True)
    parser.add_argument("--identity", default="cloudx-release")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    release_dir = args.output / version
    if release_dir.exists():
        raise SystemExit("release directory already exists: %s" % release_dir)
    release_dir.mkdir(parents=True)
    local_artifact, cloud_artifact = build_all(release_dir)
    manifest = {
        "schema": "cloudx.release-manifest.v1",
        "product": "cloudx",
        "version": version,
        "sourceCommit": source_commit(),
        "protocol": {"min": 1, "max": 1},
        "contracts": {
            "capacity": 1,
            "health": 1,
            "handshake": 1,
            "httpImporterStopGate": 1,
            "import": 1,
            "legacyHealthBridge": 1,
            "phiCloudConsumerCredential": 1,
            "phiCloudConsumerTrafficPolicy": 1,
            "phiMeshCompatibilityProfile": 1,
        },
        "artifacts": [
            artifact_record(local_artifact, "local"),
            artifact_record(cloud_artifact, "cloud"),
        ],
        "activation": {"automatic": False, "serviceRestartRequired": False},
    }
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(args.signing_key), "-n", RELEASE_NAMESPACE, str(manifest_path)],
        check=True,
    )
    generated_signature = manifest_path.with_suffix(".json.sig")
    if not generated_signature.exists():
        raise SystemExit("ssh-keygen did not create the expected signature")
    shutil.copy2(args.allowed_signers, release_dir / "allowed_signers")
    (release_dir / "SIGNING_IDENTITY").write_text(args.identity + "\n", encoding="utf-8")

    bundle = args.output / ("cloudx-%s-offline.tar.gz" % version)
    with tarfile.open(bundle, "w:gz") as archive:
        archive.add(release_dir, arcname="cloudx-%s" % version)
    print(release_dir)
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
