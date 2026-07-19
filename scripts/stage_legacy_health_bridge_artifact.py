#!/usr/bin/env python3
"""Stage the exact signed legacy-health compatibility artifact without selectors."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))
sys.path.insert(0, str(ROOT / "scripts"))

from check_phi_cloudx_legacy_health_bridge import load_evidence  # noqa: E402
from cloudx_cloud import release as cloud_release  # noqa: E402


DEFAULT_REPOSITORY = "https://github.com/N0RMANCHEN/cloudx.git"
DEFAULT_LOCK = pathlib.Path("/run/lock/cloudx-legacy-health-bridge-artifact-stage.lock")
MAX_REPOSITORY_TEXT = 512


def confirmation(version: str) -> str:
    return "STAGE CLOUDX LEGACY HEALTH BRIDGE ARTIFACT %s WITHOUT ACTIVATION" % version


def _identity(version: str) -> Mapping[str, Any]:
    evidence = load_evidence()
    cloudx = evidence["cloudx"]
    if cloudx["version"] != version:
        raise RuntimeError("legacy health bridge version does not match the pinned evidence")
    return cloudx


def _plan(version: str, identity: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-health-bridge-artifact-stage-plan.v1",
        "status": "confirmation-required",
        "confirmation": confirmation(version),
        "releaseVersion": version,
        "releaseRef": identity["artifactRef"],
        "releaseRefCommit": identity["artifactRefCommit"],
        "manifestSha256": identity["manifestSha256"],
        "releaseArtifact": "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % version,
        "automaticAction": False,
        "authorization": {
            "networkFetch": False,
            "releaseDirectoryWrite": False,
            "releaseActivation": False,
            "selectorMutation": False,
            "serviceRestart": False,
        },
    }


def _validate_directory(path: pathlib.Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("%s must be a real directory" % label)
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RuntimeError("%s must be root-owned and not group/world writable" % label)


def _validate_release_root() -> None:
    root = cloud_release.release_root()
    _validate_directory(root, "Cloudx release root")
    releases = root / "releases"
    _validate_directory(releases, "Cloudx releases directory")


@contextmanager
def _transaction_lock() -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("legacy bridge artifact staging lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("legacy bridge artifact staging lock is not root-owned")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("legacy bridge artifact staging lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _run(command: Sequence[str], *, timeout: float, label: str) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    if completed.returncode != 0:
        raise RuntimeError("%s failed" % label)
    return completed


def _fetch_bundle(repository: str, identity: Mapping[str, Any]) -> Tuple[bytes, str]:
    if not repository or len(repository) > MAX_REPOSITORY_TEXT or "\x00" in repository:
        raise RuntimeError("release repository is invalid")
    reference = str(identity["artifactRef"])
    prefix = "refs/heads/"
    if not reference.startswith(prefix):
        raise RuntimeError("pinned release reference is not a branch")
    branch = reference[len(prefix):]
    with tempfile.TemporaryDirectory(prefix="cloudx-legacy-bridge-fetch-") as value:
        temporary = pathlib.Path(value)
        checkout = temporary / "release"
        _run(
            (
                "git",
                "clone",
                "--quiet",
                "--depth=1",
                "--branch",
                branch,
                "--single-branch",
                repository,
                str(checkout),
            ),
            timeout=120.0,
            label="pinned signed release fetch",
        )
        completed = _run(
            ("git", "-C", str(checkout), "rev-parse", "HEAD"),
            timeout=10.0,
            label="pinned signed release identity check",
        )
        commit = completed.stdout.decode("ascii", errors="replace").strip()
        if commit != identity["artifactRefCommit"]:
            raise RuntimeError("fetched release reference does not match the pinned commit")
        bundle = temporary / "release.tar.gz"
        _run(
            (
                "git",
                "-C",
                str(checkout),
                "archive",
                "--format=tar.gz",
                "-o",
                str(bundle),
                "HEAD",
            ),
            timeout=30.0,
            label="pinned signed release bundle creation",
        )
        with bundle.open("rb") as handle:
            raw = cloud_release.read_bundle(handle)
    return raw, commit


def _selector_snapshot() -> Dict[str, Any]:
    status = cloud_release.status()
    return {
        "currentVersion": status["currentVersion"],
        "previousVersion": status["previousVersion"],
        "currentArtifactSha256": status["currentArtifactSha256"],
    }


def _validate_staged_artifact(artifact: pathlib.Path) -> None:
    metadata = artifact.lstat()
    if artifact.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("staged compatibility artifact is not a regular file")
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RuntimeError("staged compatibility artifact is not root-owned and immutable to non-root")


def _apply(version: str, repository: str, identity: Mapping[str, Any]) -> Dict[str, Any]:
    if os.geteuid() != 0:
        raise RuntimeError("legacy bridge compatibility artifact staging requires root")
    _validate_release_root()
    with _transaction_lock():
        selectors_before = _selector_snapshot()
        raw, release_ref_commit = _fetch_bundle(repository, identity)
        staged = cloud_release.stage_pinned_compatibility(
            raw,
            expected_version=version,
            expected_source_commit=str(identity["sourceRef"]),
            expected_manifest_sha256=str(identity["manifestSha256"]),
        )
        selectors_after = _selector_snapshot()
        if selectors_after != selectors_before:
            raise RuntimeError("Cloudx release selectors changed during compatibility staging")
    artifact = cloud_release.release_root() / "releases" / version / "cloudx-cloud.pyz"
    _validate_staged_artifact(artifact)
    return {
        "schema": "cloudx.legacy-health-bridge-artifact-stage.v1",
        "status": staged["status"],
        "releaseVersion": version,
        "releaseRefCommit": release_ref_commit,
        "sourceCommit": identity["sourceRef"],
        "manifestSha256": staged["manifestSha256"],
        "artifactSha256": staged["artifactSha256"],
        "releaseArtifact": str(artifact),
        "selectorsBefore": selectors_before,
        "selectorsAfter": selectors_after,
        "releaseActivated": False,
        "serviceRestarted": False,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Stage the pinned signed legacy-health bridge artifact without activation"
    )
    root.add_argument("--release-version", default="0.1.15")
    root.add_argument("--repository", default=DEFAULT_REPOSITORY)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    identity = _identity(args.release_version)
    if not args.apply:
        print(json.dumps(_plan(args.release_version, identity), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != confirmation(args.release_version):
        raise RuntimeError("legacy bridge artifact staging confirmation does not match")
    print(json.dumps(_apply(args.release_version, args.repository, identity), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("stage_legacy_health_bridge_artifact.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
