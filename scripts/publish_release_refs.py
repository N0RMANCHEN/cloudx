#!/usr/bin/env python3
"""Publish immutable artifact and signed stable-index branches."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(command, cwd: pathlib.Path, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        check=True,
    )
    return completed.stdout.strip() if capture else ""


def publish(source: pathlib.Path, branch: str, repository: str, message: str, force: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="cloudx-publish-") as value:
        work = pathlib.Path(value)
        run(["git", "init", "--quiet"], work)
        run(["git", "config", "user.name", "cloudx-release"], work)
        run(["git", "config", "user.email", "cloudx-release@users.noreply.github.com"], work)
        for item in source.iterdir():
            target = work / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        run(["git", "add", "."], work)
        run(["git", "commit", "--quiet", "-m", message], work)
        run(["git", "branch", "-M", branch], work)
        run(["git", "remote", "add", "origin", repository], work)
        command = ["git", "push"]
        if force:
            command.append("--force")
        command.extend(["origin", "HEAD:refs/heads/%s" % branch])
        run(command, work)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=pathlib.Path)
    parser.add_argument("stable_dir", type=pathlib.Path)
    parser.add_argument("--repository")
    args = parser.parse_args()
    manifest = __import__("json").loads((args.release_dir / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    repository = args.repository or run(["git", "remote", "get-url", "origin"], ROOT, capture=True)
    publish(
        args.release_dir,
        "release-artifacts/v%s" % version,
        repository,
        "release: Cloudx %s artifacts" % version,
        force=False,
    )
    publish(args.stable_dir, "release/stable", repository, "release: Cloudx %s stable index" % version, force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
