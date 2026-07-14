#!/usr/bin/env python3
"""Verify a staged release without activating it."""

from __future__ import annotations

import argparse
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_lib import load_manifest, validate_manifest, verify_artifacts, verify_signature, version_tuple  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=pathlib.Path)
    parser.add_argument("--identity", default="cloudx-release")
    parser.add_argument("--allowed-signers", type=pathlib.Path, default=ROOT / "release/allowed_signers")
    parser.add_argument("--current-version")
    parser.add_argument("--allow-downgrade", action="store_true")
    args = parser.parse_args()

    release_dir = args.release_dir.resolve()
    manifest_path = release_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)
    errors.extend(verify_artifacts(manifest, release_dir))
    if args.current_version and not args.allow_downgrade:
        if tuple(version_tuple(manifest["version"])) < tuple(version_tuple(args.current_version)):
            errors.append("release is a downgrade")
    if errors:
        for error in errors:
            print("release: %s" % error, file=sys.stderr)
        return 1
    verify_signature(
        manifest_path,
        release_dir / "manifest.json.sig",
        args.allowed_signers,
        args.identity,
    )
    print("release: verified %s" % manifest["version"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
