#!/usr/bin/env python3
"""Install fixed-artifact legacy health bridge units without starting them."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence

from install_scoped_gateway_key import Snapshot, atomic_write, verify_artifact


CONFIRMATION = "INSTALL cloudx-legacy-health-bridge UNITS WITHOUT START"
DEFAULT_RELEASE_ROOT = pathlib.Path("/opt/cloudx/releases")
DEFAULT_ENVIRONMENT = pathlib.Path("/etc/cloudx/legacy-health-bridge.env")
DEFAULT_SERVICE = pathlib.Path("/etc/systemd/system/cloudx-legacy-health-bridge.service")
DEFAULT_TIMER = pathlib.Path("/etc/systemd/system/cloudx-legacy-health-bridge.timer")
DEFAULT_BACKUP_ROOT = pathlib.Path("/var/lib/cloudx/legacy-health-bridge-install-backups")
DEFAULT_LOCK = pathlib.Path("/run/lock/cloudx-legacy-health-bridge-install.lock")
TARGET_SERVICE = "cloudx-legacy-health-bridge.service"
TARGET_TIMER = "cloudx-legacy-health-bridge.timer"
LEGACY_SERVICE = "cloudx-health-contract.service"
LEGACY_TIMER = "cloudx-health-contract.timer"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TEMPLATE_BYTES = 64 * 1024
MAX_EXISTING_FILE_BYTES = 64 * 1024


def _safe_snapshot(
    path: pathlib.Path,
    label: str,
    *,
    required: bool,
    maximum: int,
) -> Snapshot:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if required:
            raise RuntimeError("%s is missing" % label)
        return Snapshot(False, b"", 0, 0, 0)
    except OSError as exc:
        raise RuntimeError("%s must be a readable non-symlink file" % label) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("%s must be a regular non-symlink file" % label)
        if metadata.st_size > maximum:
            raise RuntimeError("%s exceeds the size limit" % label)
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            raise RuntimeError("%s exceeds the size limit" % label)
        return Snapshot(
            True,
            data,
            stat.S_IMODE(metadata.st_mode),
            metadata.st_uid,
            metadata.st_gid,
        )
    finally:
        os.close(descriptor)


def _validate_root_directory(path: pathlib.Path, label: str, *, exact_mode: Optional[int] = None) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("%s must be a real directory" % label)
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid != 0 or mode & 0o022:
        raise RuntimeError("%s must be root-owned and not group/world writable" % label)
    if exact_mode is not None and mode != exact_mode:
        raise RuntimeError("%s must have mode %04o" % (label, exact_mode))


def _validate_runtime_directories() -> None:
    _validate_root_directory(DEFAULT_ENVIRONMENT.parent, "Cloudx configuration directory")
    _validate_root_directory(DEFAULT_SERVICE.parent, "systemd unit directory")
    if DEFAULT_TIMER.parent != DEFAULT_SERVICE.parent:
        _validate_root_directory(DEFAULT_TIMER.parent, "systemd timer directory")
    _validate_root_directory(DEFAULT_BACKUP_ROOT.parent, "Cloudx state directory")


def _validate_artifact(artifact: pathlib.Path) -> None:
    value = _safe_snapshot(
        artifact,
        "staged cloud artifact",
        required=True,
        maximum=MAX_ARTIFACT_BYTES,
    )
    if value.uid != 0 or value.mode & 0o022:
        raise RuntimeError("staged cloud artifact must be root-owned and immutable to non-root users")


@contextmanager
def _transaction_lock() -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("legacy bridge installation lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("legacy bridge installation lock is not root-owned")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("legacy bridge installation lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _artifact_template(artifact: pathlib.Path, name: str) -> bytes:
    try:
        completed = subprocess.run(
            [sys.executable, str(artifact), "systemd-template", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("staged cloud artifact template could not run") from exc
    if completed.returncode != 0 or len(completed.stdout) > MAX_TEMPLATE_BYTES:
        raise RuntimeError("staged cloud artifact template is unavailable or oversized")
    if not completed.stdout or b"\x00" in completed.stdout:
        raise RuntimeError("staged cloud artifact template is invalid")
    return completed.stdout


def _templates(artifact: pathlib.Path, release_version: str) -> Dict[str, bytes]:
    values = {
        "environment": _artifact_template(
            artifact,
            "cloudx-legacy-health-bridge.env.example",
        ),
        "service": _artifact_template(artifact, TARGET_SERVICE),
        "timer": _artifact_template(artifact, TARGET_TIMER),
    }
    expected_environment = (
        "CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT=%s\n" % artifact
    ).encode("utf-8")
    if values["environment"] != expected_environment:
        raise RuntimeError("legacy bridge environment does not select the exact artifact")
    try:
        service = values["service"].decode("utf-8")
        timer = values["timer"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("legacy bridge unit template is not UTF-8") from exc
    required_service = (
        "EnvironmentFile=/etc/cloudx/legacy-health-bridge.env",
        "${CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT} legacy-health-bridge",
        "--source /run/cloudx/health.json",
        "--publish-to /var/lib/cloudx/health/v1.json",
        "RestrictAddressFamilies=AF_UNIX",
    )
    if any(value not in service for value in required_service):
        raise RuntimeError("legacy bridge service template violates the fixed contract")
    if "/opt/cloudx/current" in service or "/home/" in service:
        raise RuntimeError("legacy bridge service template follows mutable code")
    if "Unit=%s" % TARGET_SERVICE not in timer or "WantedBy=timers.target" not in timer:
        raise RuntimeError("legacy bridge timer template targets the wrong unit")
    if release_version not in expected_environment.decode("utf-8"):
        raise RuntimeError("legacy bridge environment version is inconsistent")
    return values


def _unit_state(unit: str) -> Dict[str, str]:
    completed = subprocess.run(
        [
            "systemctl",
            "show",
            unit,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=UnitFileState",
            "--no-pager",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10.0,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise RuntimeError("systemd unit state is unavailable for %s" % unit)
    values: Dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if set(values) != {"LoadState", "ActiveState", "UnitFileState"}:
        raise RuntimeError("systemd unit state is incomplete for %s" % unit)
    return values


def _require_legacy_path(service: Mapping[str, str], timer: Mapping[str, str]) -> None:
    if service["LoadState"] != "loaded" or service["ActiveState"] == "failed":
        raise RuntimeError("legacy health service is not available for rollback")
    if (
        timer["LoadState"] != "loaded"
        or timer["ActiveState"] != "active"
        or timer["UnitFileState"] not in {"enabled", "enabled-runtime"}
    ):
        raise RuntimeError("legacy health timer must remain loaded, enabled, and active")


def _require_target_quiescent(service: Mapping[str, str], timer: Mapping[str, str]) -> None:
    if service["ActiveState"] != "inactive" or timer["ActiveState"] != "inactive":
        raise RuntimeError("legacy bridge target units must be inactive")
    if timer["UnitFileState"] not in {"", "disabled"}:
        raise RuntimeError("legacy bridge target timer must be disabled")
    if service["UnitFileState"] not in {"", "disabled", "static"}:
        raise RuntimeError("legacy bridge target service must not be enabled or linked")


def _verify_units() -> None:
    try:
        completed = subprocess.run(
            ["systemd-analyze", "verify", str(DEFAULT_SERVICE), str(DEFAULT_TIMER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("legacy bridge unit verification could not run") from exc
    if completed.returncode != 0:
        raise RuntimeError("legacy bridge unit verification failed")


def _daemon_reload() -> None:
    completed = subprocess.run(
        ["systemctl", "daemon-reload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20.0,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("systemd daemon-reload failed")


def _prepare_backup(snapshots: Mapping[str, Snapshot]) -> pathlib.Path:
    DEFAULT_BACKUP_ROOT.mkdir(mode=0o700, exist_ok=True)
    _validate_root_directory(DEFAULT_BACKUP_ROOT, "legacy bridge backup root", exact_mode=0o700)
    backup = DEFAULT_BACKUP_ROOT / str(time.time_ns())
    backup.mkdir(mode=0o700)
    manifest: Dict[str, Any] = {}
    for name, value in snapshots.items():
        manifest[name] = {
            "existed": value.existed,
            "mode": "%04o" % value.mode if value.existed else None,
            "uid": value.uid if value.existed else None,
            "gid": value.gid if value.existed else None,
        }
        if value.existed:
            atomic_write(backup / (name + ".before"), value.data, 0o600, 0, 0)
    atomic_write(
        backup / "manifest.json",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        0o600,
        0,
        0,
    )
    return backup


def _restore(path: pathlib.Path, value: Snapshot) -> None:
    if value.existed:
        atomic_write(path, value.data, value.mode, value.uid, value.gid)
    else:
        path.unlink(missing_ok=True)


def _matches(value: Snapshot, data: bytes) -> bool:
    return value == Snapshot(True, data, 0o644, 0, 0)


def plan(release_version: str, artifact: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-health-bridge-unit-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": str(artifact),
        "environmentPath": str(DEFAULT_ENVIRONMENT),
        "servicePath": str(DEFAULT_SERVICE),
        "timerPath": str(DEFAULT_TIMER),
        "legacyService": LEGACY_SERVICE,
        "legacyTimer": LEGACY_TIMER,
        "serviceStartRequired": False,
        "timerEnableRequired": False,
        "automaticAction": False,
        "preconditions": [
            "signed_cloud_artifact_staged",
            "legacy_timer_loaded_enabled_active",
            "target_units_disabled_inactive",
            "root_owned_install_directories",
        ],
        "authorization": {
            "unitWrite": False,
            "daemonReload": False,
            "serviceStart": False,
            "timerEnable": False,
            "legacyMutation": False,
            "releaseActivation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    root.add_argument("--artifact", type=pathlib.Path)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    expected_artifact = DEFAULT_RELEASE_ROOT / args.release_version / "cloudx-cloud.pyz"
    artifact = args.artifact or expected_artifact
    if artifact != expected_artifact:
        raise RuntimeError("legacy bridge unit installer is restricted to the staged artifact")
    if not args.apply:
        print(json.dumps(plan(args.release_version, artifact), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("legacy bridge unit confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("legacy bridge unit installer must run as root")

    with _transaction_lock():
        _validate_runtime_directories()
        _validate_artifact(artifact)
        verify_artifact(artifact, args.release_version)
        templates = _templates(artifact, args.release_version)
        legacy_service_before = _unit_state(LEGACY_SERVICE)
        legacy_timer_before = _unit_state(LEGACY_TIMER)
        target_service_before = _unit_state(TARGET_SERVICE)
        target_timer_before = _unit_state(TARGET_TIMER)
        _require_legacy_path(legacy_service_before, legacy_timer_before)
        _require_target_quiescent(target_service_before, target_timer_before)

        paths = {
            "environment": DEFAULT_ENVIRONMENT,
            "service": DEFAULT_SERVICE,
            "timer": DEFAULT_TIMER,
        }
        snapshots = {
            name: _safe_snapshot(
                path,
                "existing legacy bridge %s" % name,
                required=False,
                maximum=MAX_EXISTING_FILE_BYTES,
            )
            for name, path in paths.items()
        }
        changed = [name for name in paths if not _matches(snapshots[name], templates[name])]
        backup: Optional[pathlib.Path] = None
        daemon_reloaded = False

        if changed:
            backup = _prepare_backup(snapshots)
            try:
                for name in changed:
                    atomic_write(paths[name], templates[name], 0o644, 0, 0)
                _verify_units()
                _daemon_reload()
                daemon_reloaded = True
                _require_target_quiescent(
                    _unit_state(TARGET_SERVICE),
                    _unit_state(TARGET_TIMER),
                )
                _require_legacy_path(
                    _unit_state(LEGACY_SERVICE),
                    _unit_state(LEGACY_TIMER),
                )
            except Exception as exc:
                rollback_errors = []
                for name, path in paths.items():
                    try:
                        _restore(path, snapshots[name])
                    except Exception:  # pragma: no cover - hard failure path
                        rollback_errors.append("%s restore failed" % name)
                try:
                    _daemon_reload()
                except Exception:  # pragma: no cover - hard failure path
                    rollback_errors.append("daemon reload failed")
                try:
                    _require_target_quiescent(
                        _unit_state(TARGET_SERVICE),
                        _unit_state(TARGET_TIMER),
                    )
                    _require_legacy_path(
                        _unit_state(LEGACY_SERVICE),
                        _unit_state(LEGACY_TIMER),
                    )
                except Exception:  # pragma: no cover - concurrent external mutation
                    rollback_errors.append("unit state recovery failed")
                if not rollback_errors and backup is not None:
                    shutil.rmtree(backup)
                    raise RuntimeError("legacy bridge unit installation failed and was rolled back") from exc
                raise RuntimeError(
                    "legacy bridge unit installation failed; rollback incomplete: %s"
                    % "; ".join(rollback_errors)
                ) from exc
        else:
            _verify_units()
            _require_target_quiescent(
                _unit_state(TARGET_SERVICE),
                _unit_state(TARGET_TIMER),
            )
            _require_legacy_path(
                _unit_state(LEGACY_SERVICE),
                _unit_state(LEGACY_TIMER),
            )

    print(json.dumps({
        "schema": "cloudx.legacy-health-bridge-unit-install.v1",
        "status": "installed" if changed else "already-installed",
        "releaseVersion": args.release_version,
        "releaseArtifact": str(artifact),
        "filesChanged": len(changed),
        "environmentMode": "0644",
        "serviceMode": "0644",
        "timerMode": "0644",
        "systemdVerified": True,
        "daemonReloaded": daemon_reloaded,
        "serviceStarted": False,
        "timerEnabled": False,
        "legacyServiceStopped": False,
        "legacyTimerDisabled": False,
        "releaseActivated": False,
        "legacyTimerActive": True,
        "legacyTimerEnabled": True,
        "backup": str(backup) if backup is not None else None,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("install_legacy_health_bridge_units.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
