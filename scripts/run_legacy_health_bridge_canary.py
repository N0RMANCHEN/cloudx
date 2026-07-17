#!/usr/bin/env python3
"""Run the signed legacy health bridge canary without touching legacy output."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence

import install_legacy_health_bridge_units as units


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.legacy_health_bridge import (  # noqa: E402
    LegacyHealthRejected,
    validate_legacy_health,
)


CONFIRMATION = "RUN cloudx-legacy-health-bridge-canary WITHOUT LEGACY CUTOVER"
DEFAULT_OUTPUT = pathlib.Path("/run/cloudx-legacy-health-bridge-canary/v1.json")
DEFAULT_LOCK = pathlib.Path("/run/lock/cloudx-legacy-health-bridge-canary.lock")
MAX_OUTPUT_BYTES = 64 * 1024


@contextmanager
def _transaction_lock() -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("legacy bridge canary lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("legacy bridge canary lock is not root-owned")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("legacy bridge canary lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _canary_result() -> Dict[str, str]:
    completed = subprocess.run(
        [
            "systemctl",
            "show",
            units.CANARY_SERVICE,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=UnitFileState",
            "--property=Result",
            "--property=ExecMainStatus",
            "--no-pager",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10.0,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise RuntimeError("legacy bridge canary result is unavailable")
    values: Dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    expected = {"LoadState", "ActiveState", "UnitFileState", "Result", "ExecMainStatus"}
    if set(values) != expected:
        raise RuntimeError("legacy bridge canary result is incomplete")
    return values


def _systemctl(action: str) -> None:
    if action not in {"start", "stop"}:
        raise RuntimeError("legacy bridge canary action is unsupported")
    try:
        completed = subprocess.run(
            ["systemctl", action, units.CANARY_SERVICE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("legacy bridge canary %s did not complete" % action) from exc
    if completed.returncode != 0:
        raise RuntimeError("legacy bridge canary %s failed" % action)


def _require_output_directory(*, allow_missing: bool) -> bool:
    directory = DEFAULT_OUTPUT.parent
    try:
        directory_metadata = directory.lstat()
    except FileNotFoundError:
        if allow_missing:
            return False
        raise RuntimeError("legacy bridge canary directory is missing")
    except OSError as exc:
        raise RuntimeError("legacy bridge canary directory is unavailable") from exc
    if directory.is_symlink() or not stat.S_ISDIR(directory_metadata.st_mode):
        raise RuntimeError("legacy bridge canary directory must be a real directory")
    if (
        directory_metadata.st_uid != 0
        or directory_metadata.st_gid != 0
        or stat.S_IMODE(directory_metadata.st_mode) != 0o755
    ):
        raise RuntimeError("legacy bridge canary directory must be root:root mode 0755")
    return True


def _require_no_output() -> None:
    try:
        metadata = DEFAULT_OUTPUT.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise RuntimeError("legacy bridge canary output state is unavailable") from exc
    if metadata is not None:
        raise RuntimeError("legacy bridge canary output must be absent before the run")
    if not _require_output_directory(allow_missing=True):
        return
    directory = DEFAULT_OUTPUT.parent
    try:
        if any(directory.iterdir()):
            raise RuntimeError("legacy bridge canary directory must be empty")
    except OSError as exc:
        raise RuntimeError("legacy bridge canary directory cannot be inspected") from exc


def _cleanup_output() -> None:
    directory_exists = _require_output_directory(allow_missing=True)
    try:
        metadata = DEFAULT_OUTPUT.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise RuntimeError("legacy bridge canary output cleanup is unavailable") from exc
    if metadata is not None:
        if DEFAULT_OUTPUT.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("legacy bridge canary output cleanup rejected an unsafe file")
        DEFAULT_OUTPUT.unlink()
    if directory_exists:
        try:
            DEFAULT_OUTPUT.parent.rmdir()
        except OSError as exc:
            raise RuntimeError("legacy bridge canary directory cleanup failed") from exc


def _require_runtime_boundaries() -> None:
    units._require_legacy_path(
        units._unit_state(units.LEGACY_SERVICE),
        units._unit_state(units.LEGACY_TIMER),
    )
    units._require_target_quiescent(
        units._unit_state(units.TARGET_SERVICE),
        units._unit_state(units.TARGET_TIMER),
    )
    units._require_canary_quiescent(units._unit_state(units.CANARY_SERVICE))


def _require_installed_files(artifact: pathlib.Path, release_version: str) -> None:
    templates = units._templates(artifact, release_version)
    expected = {
        "environment": (units.DEFAULT_ENVIRONMENT, templates["environment"]),
        "canary": (units.DEFAULT_CANARY, templates["canary"]),
    }
    for name, (path, data) in expected.items():
        value = units._safe_snapshot(
            path,
            "installed legacy bridge %s" % name,
            required=True,
            maximum=units.MAX_EXISTING_FILE_BYTES,
        )
        if value != units.Snapshot(True, data, 0o644, 0, 0):
            raise RuntimeError("installed legacy bridge %s does not match the signed artifact" % name)


def _validate_output() -> Mapping[str, Any]:
    _require_output_directory(allow_missing=False)
    value = units._safe_snapshot(
        DEFAULT_OUTPUT,
        "legacy bridge canary output",
        required=True,
        maximum=MAX_OUTPUT_BYTES,
    )
    if value.mode != 0o644 or value.uid != 0 or value.gid != 0:
        raise RuntimeError("legacy bridge canary output ownership or mode is invalid")
    try:
        document = json.loads(value.data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("legacy bridge canary output is invalid JSON") from exc
    try:
        validate_legacy_health(document)
    except LegacyHealthRejected as exc:
        raise RuntimeError("legacy bridge canary output violates the legacy contract") from exc
    return {"document": document, "sha256": hashlib.sha256(value.data).hexdigest()}


def plan(release_version: str, artifact: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-health-bridge-canary-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": str(artifact),
        "unit": units.CANARY_SERVICE,
        "outputPath": str(DEFAULT_OUTPUT),
        "legacyOutputPath": "/var/lib/cloudx/health/v1.json",
        "automaticAction": False,
        "preconditions": [
            "signed_cloud_artifact_staged",
            "signed_canary_unit_installed",
            "legacy_timer_loaded_enabled_active",
            "primary_bridge_disabled_inactive",
            "canary_output_absent",
        ],
        "authorization": {
            "canaryStart": False,
            "canaryStopOnFailure": False,
            "temporaryOutputWrite": False,
            "temporaryOutputCleanup": False,
            "primaryServiceStart": False,
            "primaryTimerEnable": False,
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


def run_once() -> Mapping[str, Any]:
    _require_no_output()
    canary_attempted = False
    try:
        canary_attempted = True
        _systemctl("start")
        result = _canary_result()
        if (
            result["LoadState"] != "loaded"
            or result["ActiveState"] != "inactive"
            or result["UnitFileState"] != "static"
            or result["Result"] != "success"
            or result["ExecMainStatus"] != "0"
        ):
            raise RuntimeError("legacy bridge canary unit did not finish successfully")
        accepted = _validate_output()
        _cleanup_output()
        _require_runtime_boundaries()
        return accepted
    except Exception as exc:
        cleanup_errors = []
        if canary_attempted:
            try:
                _systemctl("stop")
            except Exception:  # pragma: no cover - hard failure path
                cleanup_errors.append("canary stop failed")
        try:
            _cleanup_output()
        except Exception:  # pragma: no cover - hard failure path
            cleanup_errors.append("temporary output cleanup failed")
        try:
            _require_runtime_boundaries()
        except Exception:  # pragma: no cover - concurrent external mutation
            cleanup_errors.append("runtime boundary recovery failed")
        if cleanup_errors:
            raise RuntimeError(
                "legacy bridge canary failed; cleanup incomplete: %s"
                % "; ".join(cleanup_errors)
            ) from exc
        raise RuntimeError("legacy bridge canary failed and temporary state was removed") from exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not units.VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    expected_artifact = units.DEFAULT_RELEASE_ROOT / args.release_version / "cloudx-cloud.pyz"
    artifact = args.artifact or expected_artifact
    if artifact != expected_artifact:
        raise RuntimeError("legacy bridge canary is restricted to the staged artifact")
    if not args.apply:
        print(json.dumps(plan(args.release_version, artifact), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("legacy bridge canary confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("legacy bridge canary must run as root")

    with _transaction_lock():
        units._validate_runtime_directories()
        units._validate_artifact(artifact)
        units.verify_artifact(artifact, args.release_version)
        _require_installed_files(artifact, args.release_version)
        _require_runtime_boundaries()
        accepted = run_once()

    print(json.dumps({
        "schema": "cloudx.legacy-health-bridge-canary.v1",
        "status": "accepted",
        "releaseVersion": args.release_version,
        "releaseArtifact": str(artifact),
        "unit": units.CANARY_SERVICE,
        "unitResult": "success",
        "execMainStatus": 0,
        "outputMode": "0644",
        "outputSha256": accepted["sha256"],
        "canaryStarted": True,
        "canaryStoppedOnFailure": False,
        "temporaryOutputRemoved": True,
        "primaryServiceStarted": False,
        "primaryTimerEnabled": False,
        "legacyServiceStopped": False,
        "legacyTimerDisabled": False,
        "legacyOutputMutated": False,
        "releaseActivated": False,
        "legacyTimerActive": True,
        "legacyTimerEnabled": True,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("run_legacy_health_bridge_canary.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
