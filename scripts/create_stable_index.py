#!/usr/bin/env python3
"""Create and sign the small release/stable update index."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone


NAMESPACE = "cloudx-release"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=pathlib.Path)
    parser.add_argument("--signing-key", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = args.release_dir / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    version = data["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    index = {
        "schema": "cloudx.release-index.v1",
        "version": version,
        "manifestSha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "artifactRef": "refs/heads/release-artifacts/v%s" % version,
        "publishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    path = args.output / "index.json"
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(args.signing_key), "-n", NAMESPACE, str(path)],
        check=True,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
