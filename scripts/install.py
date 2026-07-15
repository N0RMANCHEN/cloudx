#!/usr/bin/env python3
"""Endpoint-aware Cloudx installer with explicit activation confirmation."""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import platform
import pwd
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local"))
sys.path.insert(0, str(ROOT / "cloud"))
sys.path.insert(0, str(ROOT / "scripts"))

from backup_legacy_local import activate_recovery_paths, create_backup  # noqa: E402
from bootstrap_cloud_helper import confirmation_for as bootstrap_confirmation  # noqa: E402
from bootstrap_cloud_helper import main as bootstrap_cloud  # noqa: E402
from cloudx_cloud import release as cloud_release  # noqa: E402
from cloudx_local import updater  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


def detected_endpoint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "local"
    if system == "Linux":
        return "cloud"
    raise RuntimeError("Cloudx install supports macOS local and Linux cloud endpoints")


def confirmation(endpoint: str, version: str) -> str:
    return "INSTALL CLOUDX %s %s" % (endpoint.upper(), version)


def fetch_release(repository: str, version: str, destination: pathlib.Path) -> pathlib.Path:
    completed = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--depth=1",
            "--branch",
            "release-artifacts/v%s" % version,
            repository,
            str(destination),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120.0,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("could not fetch signed Cloudx release %s" % version)
    return destination


def release_bundle(directory: pathlib.Path, version: str) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        archive.add(directory, arcname="cloudx-%s" % version)
    return output.getvalue()


def maybe_backup_legacy(config: LocalConfig) -> Optional[str]:
    entrypoint = config.home / ".local/bin/codexx"
    if not entrypoint.is_file() or entrypoint.is_symlink():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = config.state_dir / "legacy-backups" / timestamp
    create_backup(config.home, destination)
    activate_recovery_paths(config.home, destination)
    return str(destination)


def install_local(version: str, seed_account: str, repository: str) -> Dict[str, Any]:
    config = LocalConfig.load()
    backup = maybe_backup_legacy(config)
    with tempfile.TemporaryDirectory(prefix="cloudx-install-local-") as value:
        source = fetch_release(repository, version, pathlib.Path(value) / "release")
        staged = updater.stage(config, source, local_only=True)
    activated = updater.apply(
        config,
        version,
        version,
        local_only=True,
        shell_hook=True,
        seed_account=seed_account,
    )
    return {
        "schema": "cloudx.install.v1",
        "endpoint": "local",
        "version": version,
        "status": "installed",
        "staged": staged,
        "activated": activated,
        "legacyBackup": backup,
        "shellSourceInstalled": True,
    }


def install_cloud(version: str, operator: str, repository: str) -> Dict[str, Any]:
    if os.geteuid() != 0:
        raise RuntimeError("cloud endpoint installation must run as root")
    required = [
        pathlib.Path("/etc/cloudx/client-credential"),
        pathlib.Path("/etc/cloudx/cloudx-shadow.env"),
    ]
    if not all(path.is_file() for path in required):
        raise RuntimeError("cloud scoped credential and environment must be provisioned before activation")
    with tempfile.TemporaryDirectory(prefix="cloudx-install-cloud-") as value:
        source = fetch_release(repository, version, pathlib.Path(value) / "release")
        staged = cloud_release.stage(release_bundle(source, version))
    current = pathlib.Path("/opt/cloudx/current")
    if current.is_symlink():
        activated = cloud_release.activate(version, version)
    else:
        bootstrap_cloud([
            "--apply",
            "--confirm",
            bootstrap_confirmation(version),
            "--release-version",
            version,
            "--operator",
            operator,
        ])
        activated = cloud_release.status()
    return {
        "schema": "cloudx.install.v1",
        "endpoint": "cloud",
        "version": version,
        "status": "installed",
        "staged": staged,
        "activated": activated,
        "serviceRestarted": False,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Install a signed Cloudx release on the local or cloud endpoint")
    root.add_argument("endpoint", nargs="?", choices=("local", "cloud"))
    root.add_argument("--version", default=(ROOT / "VERSION").read_text(encoding="utf-8").strip())
    root.add_argument("--repository", default="git@github.com:N0RMANCHEN/cloudx.git")
    root.add_argument("--seed-native-from", default="soul0")
    root.add_argument("--operator", default=os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    endpoint = args.endpoint or detected_endpoint()
    expected = confirmation(endpoint, args.version)
    if not args.apply:
        print(json.dumps({
            "schema": "cloudx.install-plan.v1",
            "status": "confirmation-required",
            "endpoint": endpoint,
            "version": args.version,
            "confirmation": expected,
            "releaseSource": "release-artifacts/v%s" % args.version,
            "localActions": ["stage signed artifact", "backup legacy path", "seed native profile", "install shell source", "activate links"] if endpoint == "local" else [],
            "cloudActions": ["stage signed artifact", "activate helper/current", "no service restart"] if endpoint == "cloud" else [],
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != expected:
        raise RuntimeError("install confirmation does not match")
    result = (
        install_local(args.version, args.seed_native_from, args.repository)
        if endpoint == "local"
        else install_cloud(args.version, args.operator, args.repository)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("install: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
