#!/usr/bin/env python3
"""Explicit first activation for the staged Cloudx cloud helper."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import pwd
import re
import subprocess
import sys
from typing import Any, Dict, Optional, Sequence


DEFAULT_ROOT = pathlib.Path("/opt/cloudx")
DEFAULT_HELPER = pathlib.Path("/usr/local/bin/cloudx-remote")
DEFAULT_RUNNER = pathlib.Path("/usr/local/libexec/cloudx-remote-runner")
DEFAULT_SUDOERS = pathlib.Path("/etc/sudoers.d/cloudx-remote")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$", re.IGNORECASE)


def confirmation_for(version: str) -> str:
    return "ACTIVATE CLOUDX CLOUD HELPER %s" % version


def run_document(command: Sequence[str], label: str) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("%s could not run" % label) from exc
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "%s returned invalid JSON (exit=%d, stdout=%r, stderr=%r)"
            % (label, completed.returncode, completed.stdout[:200], completed.stderr[:200])
        ) from exc
    if completed.returncode != 0 or not isinstance(document, dict):
        raise RuntimeError("%s failed" % label)
    return document


def verify_artifact(artifact: pathlib.Path, version: str, direct: bool = False) -> None:
    command = [str(artifact), "self-check"] if direct else [sys.executable, str(artifact), "self-check"]
    document = run_document(command, "cloud artifact self-check")
    if (
        document.get("schema") != "cloudx.self-check.v1"
        or document.get("component") != "cloud"
        or document.get("version") != version
        or document.get("status") != "ok"
    ):
        raise RuntimeError("staged cloud artifact does not match the requested release")


def atomic_write(path: pathlib.Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary = path.parent / (".%s.%d" % (path.name, os.getpid()))
    temporary.unlink(missing_ok=True)
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, 0, 0)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def atomic_link(link: pathlib.Path, target: pathlib.Path) -> None:
    temporary = link.parent / (".%s.%d" % (link.name, os.getpid()))
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(str(temporary), str(link))


def previous_release(root: pathlib.Path, version: str) -> Optional[pathlib.Path]:
    releases = root / "releases"
    target = tuple(int(part) for part in version.split("."))
    candidates = []
    for path in releases.iterdir() if releases.is_dir() else ():
        if not path.is_dir() or not (path / "cloudx-cloud.pyz").is_file() or not VERSION_RE.match(path.name):
            continue
        parsed = tuple(int(part) for part in path.name.split("."))
        if parsed < target:
            candidates.append((parsed, path))
    return max(candidates, default=(None, None), key=lambda item: item[0])[1]


def launcher_documents(operator: str) -> tuple[bytes, bytes, bytes]:
    runner = b"""#!/bin/sh
set -eu
set -a
. /etc/cloudx/cloudx-shadow.env
set +a
exec /usr/bin/python3 /opt/cloudx/current/cloudx-cloud.pyz "$@"
"""
    helper = b"""#!/bin/sh
set -eu
case "${1:-}" in
  release-stage|release-activate|release-rollback) user=root ;;
  *) user=cloudx ;;
esac
exec /usr/bin/sudo -n -u "$user" /usr/local/libexec/cloudx-remote-runner "$@"
"""
    sudoers = (
        "%s ALL=(cloudx) NOPASSWD: /usr/local/libexec/cloudx-remote-runner *\n"
        "%s ALL=(root) NOPASSWD: /usr/local/libexec/cloudx-remote-runner release-stage, "
        "/usr/local/libexec/cloudx-remote-runner release-activate *, "
        "/usr/local/libexec/cloudx-remote-runner release-rollback *\n"
    ) % (operator, operator)
    return runner, helper, sudoers.encode("utf-8")


def install_sudoers(path: pathlib.Path, data: bytes) -> None:
    temporary = path.parent / (".%s.%d" % (path.name, os.getpid()))
    atomic_write(temporary, data, 0o440)
    try:
        completed = subprocess.run(
            ["/usr/sbin/visudo", "-cf", str(temporary)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20.0,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("generated Cloudx sudo policy is invalid")
        os.replace(str(temporary), str(path))
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Bootstrap the first Cloudx cloud helper activation")
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    root.add_argument("--operator", required=True)
    root.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    root.add_argument("--helper", type=pathlib.Path, default=DEFAULT_HELPER)
    root.add_argument("--runner", type=pathlib.Path, default=DEFAULT_RUNNER)
    root.add_argument("--sudoers", type=pathlib.Path, default=DEFAULT_SUDOERS)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    version = args.release_version
    if not VERSION_RE.match(version):
        raise RuntimeError("release version must be an exact semantic version")
    if not USER_RE.match(args.operator):
        raise RuntimeError("operator must be an exact local user name")
    artifact = args.root / "releases" / version / "cloudx-cloud.pyz"
    confirmation = confirmation_for(version)
    if not args.apply:
        print(json.dumps({
            "schema": "cloudx.cloud-helper-bootstrap-plan.v1",
            "status": "confirmation-required",
            "confirmation": confirmation,
            "releaseVersion": version,
            "artifact": str(artifact),
            "current": str(args.root / "current"),
            "helper": str(args.helper),
            "runner": str(args.runner),
            "sudoers": str(args.sudoers),
            "operator": args.operator,
            "normalIdentity": "cloudx",
            "releaseIdentity": "root",
            "serviceRestartRequired": False,
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != confirmation:
        raise RuntimeError("cloud helper activation confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("cloud helper bootstrap must run as root")
    if (
        args.root != DEFAULT_ROOT
        or args.helper != DEFAULT_HELPER
        or args.runner != DEFAULT_RUNNER
        or args.sudoers != DEFAULT_SUDOERS
    ):
        raise RuntimeError("cloud helper bootstrap is restricted to the declared production paths")
    try:
        pwd.getpwnam(args.operator)
        pwd.getpwnam("cloudx")
    except KeyError as exc:
        raise RuntimeError("operator or cloudx service identity does not exist") from exc
    current = args.root / "current"
    managed_paths = (args.helper, args.runner, args.sudoers)
    if current.exists() or current.is_symlink() or any(path.exists() or path.is_symlink() for path in managed_paths):
        raise RuntimeError("cloud helper bootstrap is only for a first activation")
    verify_artifact(artifact, version)

    activated = False
    previous_created = False
    created = []
    try:
        runner, helper, sudoers = launcher_documents(args.operator)
        atomic_write(args.runner, runner, 0o755)
        created.append(args.runner)
        atomic_write(args.helper, helper, 0o755)
        created.append(args.helper)
        install_sudoers(args.sudoers, sudoers)
        created.append(args.sudoers)
        document = run_document(
            [sys.executable, str(artifact), "release-activate", "--version", version, "--confirm", version],
            "cloud release activation",
        )
        if (
            document.get("schema") != "cloudx.release-activate.v1"
            or document.get("version") != version
            or document.get("status") != "active"
        ):
            raise RuntimeError("cloud release activation returned an unexpected result")
        activated = True
        previous = args.root / "previous"
        if not previous.is_symlink():
            fallback = previous_release(args.root, version)
            if fallback:
                atomic_link(previous, fallback)
                previous_created = True
        verify_artifact(args.helper, version, direct=True)
        handshake = run_document([str(args.helper), "handshake", "--json"], "cloud helper handshake")
        if (
            handshake.get("schema") != "cloudx.handshake.v1"
            or handshake.get("productVersion") != version
            or not isinstance(handshake.get("gateway"), dict)
            or handshake["gateway"].get("status") != "healthy"
        ):
            raise RuntimeError("cloud helper handshake did not report the activated healthy release")
        status = run_document([str(args.helper), "release-status"], "cloud release status")
        if status.get("currentVersion") != version or status.get("status") != "active":
            raise RuntimeError("cloud helper did not report the activated release")
    except Exception as exc:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        if activated and (current.exists() or current.is_symlink()):
            current.unlink(missing_ok=True)
        if previous_created:
            (args.root / "previous").unlink(missing_ok=True)
        raise RuntimeError("cloud helper bootstrap failed and was rolled back: %s" % exc) from exc

    print(json.dumps({
        "schema": "cloudx.cloud-helper-bootstrap.v1",
        "status": "active",
        "releaseVersion": version,
        "current": str(current),
        "helper": str(args.helper),
        "runner": str(args.runner),
        "sudoers": str(args.sudoers),
        "operator": args.operator,
        "serviceRestarted": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("bootstrap_cloud_helper.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
