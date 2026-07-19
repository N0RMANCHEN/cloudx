#!/usr/bin/env python3
"""Cut over, roll back, and restore the legacy health bridge without a publisher gap."""

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
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence

import install_legacy_health_bridge_units as units
import run_legacy_health_bridge_canary as canary


CONFIRMATION = "CUT OVER AND REHEARSE cloudx-legacy-health-bridge WITH ROLLBACK"
DEFAULT_OUTPUT = pathlib.Path("/var/lib/cloudx/health/v1.json")
DEFAULT_BACKUP_ROOT = pathlib.Path("/var/lib/cloudx/legacy-health-bridge-cutover-backups")
DEFAULT_LOCK = pathlib.Path("/run/lock/cloudx-legacy-health-bridge-cutover.lock")
DEFAULT_CURRENT = pathlib.Path("/opt/cloudx/current")
DEFAULT_PREVIOUS = pathlib.Path("/opt/cloudx/previous")
GATEWAY_UNIT = "cliproxy.service"
IMPORT_UNIT = "codex-import.service"
IMPORT_PORT = 8780
MAX_OUTPUT_BYTES = 64 * 1024


@contextmanager
def _transaction_lock() -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("legacy bridge cutover lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("legacy bridge cutover lock is not root-owned")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("legacy bridge cutover lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _selector_version(path: pathlib.Path) -> str:
    try:
        metadata = path.lstat()
        raw_target = os.readlink(path)
    except OSError as exc:
        raise RuntimeError("Cloudx release selector is unavailable") from exc
    if not stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("Cloudx release selector must be a symlink")
    target = (path.parent / raw_target).resolve(strict=True)
    try:
        relative = target.relative_to(units.DEFAULT_RELEASE_ROOT.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Cloudx release selector escapes the release root") from exc
    if len(relative.parts) != 1 or not units.VERSION_RE.fullmatch(relative.parts[0]):
        raise RuntimeError("Cloudx release selector does not name an exact version")
    return relative.parts[0]


def _selector_state() -> Dict[str, str]:
    return {
        "current": _selector_version(DEFAULT_CURRENT),
        "previous": _selector_version(DEFAULT_PREVIOUS),
    }


def _importer_connections_present() -> bool:
    try:
        completed = subprocess.run(
            [
                "ss",
                "-H",
                "-tan",
                "( sport = :%d or dport = :%d )" % (IMPORT_PORT, IMPORT_PORT),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("legacy importer socket state is unavailable") from exc
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise RuntimeError("legacy importer socket state is unavailable")
    return bool(completed.stdout.strip())


def _process_state(unit: str) -> Dict[str, Any]:
    if unit not in {GATEWAY_UNIT, IMPORT_UNIT}:
        raise RuntimeError("continuity unit is unsupported")
    completed = subprocess.run(
        [
            "systemctl",
            "show",
            unit,
            "--property=ActiveState",
            "--property=MainPID",
            "--property=NRestarts",
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
        raise RuntimeError("continuity process state is unavailable")
    values: Dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if set(values) != {"ActiveState", "MainPID", "NRestarts", "UnitFileState"}:
        raise RuntimeError("continuity process state is incomplete")
    try:
        pid = int(values["MainPID"])
        restarts = int(values["NRestarts"])
    except ValueError as exc:
        raise RuntimeError("continuity process state is invalid") from exc
    if restarts < 0:
        raise RuntimeError("continuity process state is invalid")
    if values["ActiveState"] == "active" and pid > 0:
        return {"activeState": "active", "mainPid": pid, "restarts": restarts}
    if (
        unit == IMPORT_UNIT
        and values["ActiveState"] == "inactive"
        and pid == 0
        and values["UnitFileState"] == "disabled"
        and not _importer_connections_present()
    ):
        return {
            "activeState": "inactive",
            "mainPid": 0,
            "restarts": restarts,
            "unitFileState": "disabled",
            "listenerClosed": True,
        }
    if unit == IMPORT_UNIT:
        raise RuntimeError("legacy importer is neither active nor safely retired")
    raise RuntimeError("continuity process is not active")


def _require_timer(unit: str, *, active: bool) -> None:
    value = units._unit_state(unit)
    if value["LoadState"] != "loaded":
        raise RuntimeError("legacy bridge timer is not loaded")
    if active:
        if value["ActiveState"] != "active" or value["UnitFileState"] not in {"enabled", "enabled-runtime"}:
            raise RuntimeError("legacy bridge timer is not enabled and active")
    elif value["ActiveState"] != "inactive" or value["UnitFileState"] != "disabled":
        raise RuntimeError("legacy bridge timer is not disabled and inactive")


def _require_initial_units() -> None:
    _require_timer(units.LEGACY_TIMER, active=True)
    _require_timer(units.TARGET_TIMER, active=False)
    units._require_canary_quiescent(units._unit_state(units.CANARY_SERVICE))
    service = units._unit_state(units.TARGET_SERVICE)
    if service["LoadState"] != "loaded" or service["ActiveState"] != "inactive":
        raise RuntimeError("primary legacy bridge service is not loaded and inactive")


def _require_installed_files(artifact: pathlib.Path, release_version: str) -> None:
    templates = units._templates(artifact, release_version)
    expected = {
        "environment": (units.DEFAULT_ENVIRONMENT, templates["environment"]),
        "canary": (units.DEFAULT_CANARY, templates["canary"]),
        "service": (units.DEFAULT_SERVICE, templates["service"]),
        "timer": (units.DEFAULT_TIMER, templates["timer"]),
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


def _read_output() -> Dict[str, Any]:
    value = units._safe_snapshot(
        DEFAULT_OUTPUT,
        "legacy health output",
        required=True,
        maximum=MAX_OUTPUT_BYTES,
    )
    if value.mode != 0o644 or value.uid != 0 or value.gid != 0:
        raise RuntimeError("legacy health output ownership or mode is invalid")
    try:
        document = json.loads(value.data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("legacy health output is invalid JSON") from exc
    try:
        canary.validate_legacy_health(document)
    except canary.LegacyHealthRejected as exc:
        raise RuntimeError("legacy health output violates the strict contract") from exc
    return {
        "document": document,
        "sha256": hashlib.sha256(value.data).hexdigest(),
        "snapshot": value,
    }


def _validate_candidate_output() -> Dict[str, Any]:
    value = _read_output()
    document = value["document"]
    if (
        document["producer"]["revision"] != "unknown"
        or document["gateway"]["processState"] != "unknown"
        or document["imports"]["processState"] != "unknown"
        or document["imports"]["state"] != "unknown"
    ):
        raise RuntimeError("legacy health output was not produced by the conservative bridge")
    return value


def _validate_legacy_output(expected_producer: Mapping[str, Any]) -> Dict[str, Any]:
    value = _read_output()
    document = value["document"]
    if document["producer"] != expected_producer or document["producer"]["revision"] == "unknown":
        raise RuntimeError("legacy health output was not restored by the old exporter")
    return value


def _systemctl(action: str, unit: str) -> None:
    allowed = {
        ("enable", units.LEGACY_TIMER),
        ("enable", units.TARGET_TIMER),
        ("disable", units.LEGACY_TIMER),
        ("disable", units.TARGET_TIMER),
        ("start", units.LEGACY_SERVICE),
        ("start", units.TARGET_SERVICE),
    }
    if (action, unit) not in allowed:
        raise RuntimeError("legacy bridge cutover action is unsupported")
    command = ["systemctl", action]
    if action in {"enable", "disable"}:
        command.append("--now")
    command.append(unit)
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("legacy bridge cutover systemd action did not complete") from exc
    if completed.returncode != 0:
        raise RuntimeError("legacy bridge cutover systemd action failed")


def _start_and_validate_candidate() -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for _attempt in range(3):
        try:
            _systemctl("start", units.TARGET_SERVICE)
            return _validate_candidate_output()
        except RuntimeError as exc:
            last_error = exc
    raise RuntimeError("primary legacy bridge did not publish accepted output") from last_error


def _start_and_validate_legacy(expected_producer: Mapping[str, Any]) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for _attempt in range(3):
        try:
            _systemctl("start", units.LEGACY_SERVICE)
            return _validate_legacy_output(expected_producer)
        except RuntimeError as exc:
            last_error = exc
    raise RuntimeError("old legacy exporter did not restore accepted output") from last_error


def _prepare_backup(
    output: units.Snapshot,
    selectors: Mapping[str, str],
    gateway: Mapping[str, Any],
    importer: Mapping[str, Any],
) -> pathlib.Path:
    DEFAULT_BACKUP_ROOT.mkdir(mode=0o700, exist_ok=True)
    units._validate_root_directory(DEFAULT_BACKUP_ROOT, "legacy bridge cutover backup root", exact_mode=0o700)
    backup = DEFAULT_BACKUP_ROOT / str(time.time_ns())
    backup.mkdir(mode=0o700)
    units.atomic_write(backup / "legacy-health.before.json", output.data, 0o600, 0, 0)
    manifest = {
        "schema": "cloudx.legacy-health-bridge-cutover-backup.v1",
        "selectors": dict(selectors),
        "gateway": dict(gateway),
        "importer": dict(importer),
        "outputMode": "%04o" % output.mode,
        "outputUid": output.uid,
        "outputGid": output.gid,
    }
    units.atomic_write(
        backup / "manifest.json",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        0o600,
        0,
        0,
    )
    return backup


def _recover_old_path(initial: units.Snapshot, expected_producer: Mapping[str, Any]) -> Sequence[str]:
    errors = []
    old_ready = False
    old_output_ready = False
    try:
        _systemctl("enable", units.LEGACY_TIMER)
        _require_timer(units.LEGACY_TIMER, active=True)
        old_ready = True
    except Exception:  # pragma: no cover - hard failure path
        errors.append("old timer recovery failed")
    if old_ready:
        try:
            _start_and_validate_legacy(expected_producer)
            old_output_ready = True
        except Exception:  # pragma: no cover - hard failure path
            errors.append("old exporter recovery failed")
            try:
                units.atomic_write(DEFAULT_OUTPUT, initial.data, initial.mode, initial.uid, initial.gid)
                old_output_ready = True
            except Exception:
                errors.append("legacy output restore failed")
    if old_ready and old_output_ready:
        try:
            _systemctl("disable", units.TARGET_TIMER)
            _require_timer(units.TARGET_TIMER, active=False)
        except Exception:  # pragma: no cover - hard failure path
            errors.append("primary timer recovery failed")
    return errors


def plan(release_version: str, artifact: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-health-bridge-cutover-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": str(artifact),
        "legacyService": units.LEGACY_SERVICE,
        "legacyTimer": units.LEGACY_TIMER,
        "primaryService": units.TARGET_SERVICE,
        "primaryTimer": units.TARGET_TIMER,
        "communicationGapAllowed": False,
        "finalPublisher": "signed_primary_bridge",
        "phases": [
            "isolated_canary",
            "candidate_overlap",
            "candidate_cutover",
            "legacy_rollback",
            "candidate_restoration",
        ],
        "automaticAction": False,
        "preconditions": [
            "signed_cloud_artifact_staged",
            "signed_units_installed_inactive",
            "legacy_timer_loaded_enabled_active",
            "gateway_and_importer_continuity",
            "exact_release_selectors_recorded",
        ],
        "authorization": {
            "isolatedCanary": False,
            "backupWrite": False,
            "primaryServiceStart": False,
            "primaryTimerEnable": False,
            "primaryTimerDisable": False,
            "legacyServiceStart": False,
            "legacyTimerEnable": False,
            "legacyTimerDisable": False,
            "legacyOutputWrite": False,
            "releaseActivation": False,
            "phiServiceMutation": False,
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
    if not units.VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    expected_artifact = units.DEFAULT_RELEASE_ROOT / args.release_version / "cloudx-cloud.pyz"
    artifact = args.artifact or expected_artifact
    if artifact != expected_artifact:
        raise RuntimeError("legacy bridge cutover is restricted to the staged artifact")
    if not args.apply:
        print(json.dumps(plan(args.release_version, artifact), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("legacy bridge cutover confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("legacy bridge cutover must run as root")

    with _transaction_lock(), canary._transaction_lock():
        units._validate_runtime_directories()
        units._validate_artifact(artifact)
        units.verify_artifact(artifact, args.release_version)
        _require_installed_files(artifact, args.release_version)
        _require_initial_units()
        selectors_before = _selector_state()
        gateway_before = _process_state(GATEWAY_UNIT)
        importer_before = _process_state(IMPORT_UNIT)
        initial = _read_output()
        expected_producer = dict(initial["document"]["producer"])
        if expected_producer.get("revision") == "unknown":
            raise RuntimeError("old legacy exporter identity is not distinguishable")
        canary._require_installed_files(artifact, args.release_version)
        canary._require_runtime_boundaries()
        isolated = canary.run_once()
        backup = _prepare_backup(
            initial["snapshot"],
            selectors_before,
            gateway_before,
            importer_before,
        )
        phases = [{"name": "isolated_canary", "status": "accepted", "outputSha256": isolated["sha256"]}]
        try:
            _systemctl("enable", units.TARGET_TIMER)
            _require_timer(units.LEGACY_TIMER, active=True)
            _require_timer(units.TARGET_TIMER, active=True)
            overlap = _start_and_validate_candidate()
            phases.append({"name": "candidate_overlap", "status": "accepted", "outputSha256": overlap["sha256"]})

            _systemctl("disable", units.LEGACY_TIMER)
            _require_timer(units.TARGET_TIMER, active=True)
            _require_timer(units.LEGACY_TIMER, active=False)
            cutover = _start_and_validate_candidate()
            phases.append({"name": "candidate_cutover", "status": "accepted", "outputSha256": cutover["sha256"]})

            _systemctl("enable", units.LEGACY_TIMER)
            _require_timer(units.TARGET_TIMER, active=True)
            _require_timer(units.LEGACY_TIMER, active=True)
            _start_and_validate_legacy(expected_producer)
            _systemctl("disable", units.TARGET_TIMER)
            _require_timer(units.LEGACY_TIMER, active=True)
            _require_timer(units.TARGET_TIMER, active=False)
            rollback = _start_and_validate_legacy(expected_producer)
            phases.append({"name": "legacy_rollback", "status": "accepted", "outputSha256": rollback["sha256"]})

            _systemctl("enable", units.TARGET_TIMER)
            _require_timer(units.LEGACY_TIMER, active=True)
            _require_timer(units.TARGET_TIMER, active=True)
            _start_and_validate_candidate()
            _systemctl("disable", units.LEGACY_TIMER)
            _require_timer(units.TARGET_TIMER, active=True)
            _require_timer(units.LEGACY_TIMER, active=False)
            restored = _start_and_validate_candidate()
            phases.append({"name": "candidate_restoration", "status": "accepted", "outputSha256": restored["sha256"]})

            selectors_after = _selector_state()
            gateway_after = _process_state(GATEWAY_UNIT)
            importer_after = _process_state(IMPORT_UNIT)
            if selectors_after != selectors_before:
                raise RuntimeError("Cloudx release selectors changed during bridge cutover")
            if gateway_after != gateway_before or importer_after != importer_before:
                raise RuntimeError("gateway or importer continuity changed during bridge cutover")
        except Exception as exc:
            recovery_errors = list(_recover_old_path(initial["snapshot"], expected_producer))
            try:
                selector_continuity = _selector_state() == selectors_before
            except Exception:  # pragma: no cover - external continuity failure
                selector_continuity = False
            if not selector_continuity:
                recovery_errors.append("release selector continuity changed")
            try:
                process_continuity = (
                    _process_state(GATEWAY_UNIT) == gateway_before
                    and _process_state(IMPORT_UNIT) == importer_before
                )
            except Exception:  # pragma: no cover - external continuity failure
                process_continuity = False
            if not process_continuity:
                recovery_errors.append("process continuity changed")
            if recovery_errors:
                raise RuntimeError(
                    "legacy bridge cutover failed; recovery incomplete: %s"
                    % "; ".join(recovery_errors)
                ) from exc
            raise RuntimeError("legacy bridge cutover failed and the old path was restored") from exc

    print(json.dumps({
        "schema": "cloudx.legacy-health-bridge-cutover.v1",
        "status": "accepted",
        "releaseVersion": args.release_version,
        "releaseArtifact": str(artifact),
        "phases": phases,
        "communicationGapObserved": False,
        "rollbackRehearsed": True,
        "restorationAccepted": True,
        "finalPublisher": "signed_primary_bridge",
        "primaryTimerEnabled": True,
        "legacyTimerDisabled": True,
        "legacyServiceRetained": True,
        "selectorsUnchanged": True,
        "gatewayProcessUnchanged": True,
        "importerProcessUnchanged": True,
        "phiServiceRestarted": False,
        "releaseActivated": False,
        "backup": str(backup),
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("rehearse_legacy_health_bridge_cutover.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
