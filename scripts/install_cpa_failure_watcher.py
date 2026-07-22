#!/usr/bin/env python3
"""Explicitly activate event-driven CPA failure-receipt maintenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import plistlib
import pwd
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "third_party/cliproxyapi/deployment-contract.json"
REQUIRED_CLOUDX_VERSIONS = {"local": "0.1.21", "cloud": "0.1.24"}
PLAN_SCHEMA = "cloudx.cpa-failure-watcher-plan.v1"
RESULT_SCHEMA = "cloudx.cpa-failure-watcher.v1"
MAX_FILE_BYTES = 2 * 1024 * 1024
LOCAL_FALLBACK_SECONDS = 120
LOCAL_THROTTLE_SECONDS = 5
CLOUD_FAILURE_SERVICE_UNIT = "cloudx-cpa-failure.service"
CLOUD_FAILURE_PATH_UNIT = "cloudx-cpa-failure.path"
CLOUD_SWEEP_SERVICE_UNIT = "cloudx-cpa-sweep.service"
CLOUD_SWEEP_PATH_UNIT = "cloudx-cpa-sweep.path"
CLOUD_HEALTH_SERVICE_UNIT = "cloudx-cpa-health.service"
CLOUD_HEALTH_TIMER_UNIT = "cloudx-cpa-health.timer"


class FailureWatcherRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    existed: bool
    data: bytes
    mode: int
    uid: int
    gid: int


def safe_snapshot(path: pathlib.Path, *, required: bool) -> Snapshot:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        if required:
            raise FailureWatcherRejected("required failure-watcher file is missing")
        return Snapshot(False, b"", 0, 0, 0)
    except OSError as exc:
        raise FailureWatcherRejected("failure-watcher file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise FailureWatcherRejected("failure-watcher file is unsafe or oversized")
        chunks = []
        remaining = MAX_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_FILE_BYTES:
            raise FailureWatcherRejected("failure-watcher file is oversized")
        return Snapshot(True, raw, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)
    finally:
        os.close(descriptor)


def fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_directory(path: pathlib.Path, *, mode: int, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise FailureWatcherRejected("failure-watcher directory is unsafe")
    os.chown(path, uid, gid)
    path.chmod(mode)


def atomic_write(path: pathlib.Path, raw: bytes, *, mode: int, uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, uid, gid)
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def restore_snapshot(path: pathlib.Path, value: Snapshot) -> None:
    if value.existed:
        atomic_write(path, value.data, mode=value.mode, uid=value.uid, gid=value.gid)
    else:
        path.unlink(missing_ok=True)
        if path.parent.is_dir():
            fsync_directory(path.parent)


def run_command(argv: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FailureWatcherRejected("failure-watcher service command failed") from exc
    if check and completed.returncode != 0:
        raise FailureWatcherRejected("failure-watcher service command was rejected")
    return completed


def target_value(target: str, contract_path: pathlib.Path) -> Dict[str, Any]:
    try:
        contract = json.loads(safe_snapshot(contract_path, required=True).data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailureWatcherRejected("CPA deployment contract is invalid") from exc
    if contract.get("schema") != "cloudx.cliproxy-policy-deployment.v1":
        raise FailureWatcherRejected("CPA deployment contract schema is invalid")
    raw = contract.get("targets", {}).get(target)
    if not isinstance(raw, dict) or raw.get("requiredActiveCloudxVersion") != REQUIRED_CLOUDX_VERSIONS[target]:
        raise FailureWatcherRejected("CPA failure-watcher target is invalid")
    value = dict(raw)
    if target == "local":
        home = pathlib.Path.home().resolve()
        keys = (
            "failureDirectory",
            "sweepDirectory",
            "launcher",
            "maintenanceLauncher",
            "stageRoot",
            "watcherBackupRoot",
        )
        for key in keys:
            value[key] = home / str(value.get(key) or "")
    else:
        keys = (
            "failureDirectory",
            "sweepDirectory",
            "gatewayDropIn",
            "healthServiceUnit",
            "healthTimerUnit",
            "failureServiceUnit",
            "failurePathUnit",
            "sweepServiceUnit",
            "sweepPathUnit",
            "stageRoot",
            "watcherBackupRoot",
        )
        for key in keys:
            value[key] = pathlib.Path(str(value.get(key) or ""))
            if not value[key].is_absolute():
                raise FailureWatcherRejected("cloud failure-watcher path is invalid")
    value["stagedBinary"] = value["stageRoot"] / value["version"] / "cli-proxy-api"
    return value


def active_artifact(target: str) -> pathlib.Path:
    if target == "local":
        return pathlib.Path.home().resolve() / ".local/lib/cloudx/current/cloudx-local.pyz"
    return pathlib.Path("/opt/cloudx/current/cloudx-cloud.pyz")


def require_active_cloudx(target: str, required_version: str) -> pathlib.Path:
    artifact = active_artifact(target)
    safe_snapshot(artifact, required=True)
    completed = run_command([sys.executable, str(artifact), "self-check"])
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FailureWatcherRejected("active Cloudx self-check is invalid") from exc
    if (
        document.get("schema") != "cloudx.self-check.v1"
        or document.get("status") != "ok"
        or document.get("version") != required_version
    ):
        raise FailureWatcherRejected("required signed Cloudx release is not active")
    return artifact


def require_receipt_producer(target: str, value: Dict[str, Any]) -> None:
    if target == "local":
        try:
            document = plistlib.loads(safe_snapshot(value["launcher"], required=True).data)
        except Exception as exc:
            raise FailureWatcherRejected("local CPA receipt-producer launcher is invalid") from exc
        arguments = document.get("ProgramArguments")
        environment = document.get("EnvironmentVariables")
        if (
            not isinstance(arguments, list)
            or not arguments
            or arguments[0] != str(value["stagedBinary"])
            or not isinstance(environment, dict)
            or environment.get("CLIPROXY_AUTH_FAILURE_DIR") != str(value["failureDirectory"])
            or environment.get("CLIPROXY_AUTH_SWEEP_DIR") != str(value["sweepDirectory"])
        ):
            raise FailureWatcherRejected("local CPA failure-receipt producer is not active")
        domain = "gui/%d" % os.geteuid()
        live = run_command(["launchctl", "print", "%s/%s" % (domain, value["serviceLabel"])])
        if str(value["stagedBinary"]) not in live.stdout:
            raise FailureWatcherRejected("local CPA live service does not select the receipt producer")
        return
    try:
        drop_in = safe_snapshot(value["gatewayDropIn"], required=True).data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FailureWatcherRejected("cloud CPA receipt-producer drop-in is invalid") from exc
    if (
        "CLIPROXY_AUTH_FAILURE_DIR=%s" % value["failureDirectory"] not in drop_in
        or "CLIPROXY_AUTH_SWEEP_DIR=%s" % value["sweepDirectory"] not in drop_in
        or str(value["stagedBinary"]) not in drop_in
    ):
        raise FailureWatcherRejected("cloud CPA failure-receipt producer is not active")
    live = run_command(["systemctl", "show", value["service"], "-p", "ExecStart", "--no-pager"])
    if str(value["stagedBinary"]) not in live.stdout:
        raise FailureWatcherRejected("cloud CPA live service does not select the receipt producer")


def local_launcher(raw: bytes, value: Dict[str, Any]) -> bytes:
    try:
        document = plistlib.loads(raw)
    except Exception as exc:
        raise FailureWatcherRejected("local CPA maintenance launcher is invalid") from exc
    arguments = document.get("ProgramArguments")
    expected_program = pathlib.Path.home().resolve() / ".local/bin/codexx"
    if (
        document.get("Label") != value["maintenanceLabel"]
        or not isinstance(arguments, list)
        or arguments != [str(expected_program), "api", "refresh", "--apply"]
    ):
        raise FailureWatcherRejected("local CPA maintenance launcher contract changed")
    document["RunAtLoad"] = True
    document["StartInterval"] = LOCAL_FALLBACK_SECONDS
    document["ThrottleInterval"] = LOCAL_THROTTLE_SECONDS
    document["WatchPaths"] = [
        str(value["failureDirectory"]),
        str(value["sweepDirectory"] / "trigger.json"),
    ]
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=False)


def signed_cloud_units(artifact: pathlib.Path, value: Dict[str, Any]) -> Dict[str, bytes]:
    health_service = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_HEALTH_SERVICE_UNIT]
    ).stdout
    health_timer = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_HEALTH_TIMER_UNIT]
    ).stdout
    failure_service = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_FAILURE_SERVICE_UNIT]
    ).stdout
    failure_path = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_FAILURE_PATH_UNIT]
    ).stdout
    sweep_service = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_SWEEP_SERVICE_UNIT]
    ).stdout
    sweep_path = run_command(
        [sys.executable, str(artifact), "systemd-template", CLOUD_SWEEP_PATH_UNIT]
    ).stdout
    if (
        "cpa-health --sweep-if-triggered" not in health_service
        or "CLOUDX_CPA_SWEEP_CONCURRENCY=32" not in health_service
        or str(value["sweepDirectory"]) not in health_service
        or "OnUnitActiveSec=5min" not in health_timer
        or "Unit=%s" % CLOUD_HEALTH_SERVICE_UNIT not in health_timer
        or "cpa-health --runtime-failures-only" not in failure_service
        or "PrivateNetwork=true" not in failure_service
        or "PathChanged=%s" % value["failureDirectory"] not in failure_path
        or "Unit=%s" % CLOUD_FAILURE_SERVICE_UNIT not in failure_path
        or "cpa-health --sweep-if-triggered" not in sweep_service
        or "CLOUDX_CPA_SWEEP_CONCURRENCY=32" not in sweep_service
        or "PathChanged=%s/trigger.json" % value["sweepDirectory"] not in sweep_path
        or "Unit=%s" % CLOUD_SWEEP_SERVICE_UNIT not in sweep_path
    ):
        raise FailureWatcherRejected("signed Cloudx failure-watcher templates are invalid")
    return {
        "health-service": health_service.encode("utf-8"),
        "health-timer": health_timer.encode("utf-8"),
        "failure-service": failure_service.encode("utf-8"),
        "failure-path": failure_path.encode("utf-8"),
        "sweep-service": sweep_service.encode("utf-8"),
        "sweep-path": sweep_path.encode("utf-8"),
    }


def backup(root: pathlib.Path, snapshots: Dict[str, Snapshot], *, uid: int, gid: int) -> pathlib.Path:
    ensure_directory(root, mode=0o700, uid=uid, gid=gid)
    destination = root / str(time.time_ns())
    ensure_directory(destination, mode=0o700, uid=uid, gid=gid)
    manifest: Dict[str, Any] = {"schema": "cloudx.cpa-failure-watcher-backup.v1", "files": {}}
    for name, snapshot in snapshots.items():
        manifest["files"][name] = {
            "existed": snapshot.existed,
            "mode": snapshot.mode,
            "uid": snapshot.uid,
            "gid": snapshot.gid,
            "sha256": hashlib.sha256(snapshot.data).hexdigest() if snapshot.existed else "",
        }
        if snapshot.existed:
            atomic_write(destination / (name + ".before"), snapshot.data, mode=0o600, uid=uid, gid=gid)
    atomic_write(
        destination / "manifest.json",
        (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o600,
        uid=uid,
        gid=gid,
    )
    return destination


def plan_document(target: str, value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "target": target,
        "confirmation": "ACTIVATE %s CPA FAILURE WATCHER %s" % (target.upper(), value["requiredActiveCloudxVersion"]),
        "requiredActiveCloudxVersion": value["requiredActiveCloudxVersion"],
        "requiredActivePolicyVersion": value["version"],
        "trigger": "permanent-receipt-or-pool-unavailable",
        "fallbackSeconds": LOCAL_FALLBACK_SECONDS if target == "local" else 300,
        "networkProbeOnPermanentReceipt": False,
        "networkProbeOnPoolUnavailable": True,
        "incidentProbeConcurrency": "adaptive-up-to-32",
        "periodicAccountProbe": False,
        "updatesTriggerAwareHealthFallback": target == "cloud",
        "restartsExternalCPA": False,
        "stopsCodexProcesses": False,
        "automaticAction": False,
    }


def activate_local(value: Dict[str, Any]) -> Dict[str, Any]:
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise FailureWatcherRejected("local failure-watcher activation requires the macOS login user")
    require_active_cloudx("local", value["requiredActiveCloudxVersion"])
    require_receipt_producer("local", value)
    before = safe_snapshot(value["maintenanceLauncher"], required=True)
    after = local_launcher(before.data, value)
    uid = os.geteuid()
    gid = os.getegid()
    ensure_directory(value["failureDirectory"], mode=0o700, uid=uid, gid=gid)
    ensure_directory(value["sweepDirectory"], mode=0o700, uid=uid, gid=gid)
    domain = "gui/%d" % uid
    service = "%s/%s" % (domain, value["maintenanceLabel"])
    was_loaded = run_command(["launchctl", "print", service], check=False).returncode == 0
    if before.data == after and was_loaded:
        return {"schema": RESULT_SCHEMA, "status": "already-active", "target": "local"}
    destination = backup(value["watcherBackupRoot"], {"maintenance-launcher": before}, uid=uid, gid=gid)
    try:
        atomic_write(
            value["maintenanceLauncher"],
            after,
            mode=before.mode,
            uid=before.uid,
            gid=before.gid,
        )
        run_command(["launchctl", "bootout", service], check=False)
        run_command(["launchctl", "bootstrap", domain, str(value["maintenanceLauncher"])])
        run_command(["launchctl", "print", service])
    except Exception as exc:
        try:
            restore_snapshot(value["maintenanceLauncher"], before)
            run_command(["launchctl", "bootout", service], check=False)
            if was_loaded:
                run_command(["launchctl", "bootstrap", domain, str(value["maintenanceLauncher"])])
                run_command(["launchctl", "print", service])
        except Exception as recovery_exc:
            raise FailureWatcherRejected(
                "local failure-watcher activation failed and rollback was incomplete"
            ) from recovery_exc
        raise FailureWatcherRejected("local failure-watcher activation failed and was rolled back") from exc
    return {"schema": RESULT_SCHEMA, "status": "active", "target": "local", "backupName": destination.name}


def unit_state(name: str) -> Tuple[bool, bool]:
    enabled = run_command(["systemctl", "is-enabled", name], check=False).returncode == 0
    active = run_command(["systemctl", "is-active", name], check=False).returncode == 0
    return enabled, active


def restore_cloud_state(name: str, enabled: bool, active: bool) -> None:
    run_command(["systemctl", "disable", "--now", name], check=False)
    if enabled:
        run_command(["systemctl", "enable", name])
    if active:
        run_command(["systemctl", "start", name])
    if unit_state(name) != (enabled, active):
        raise FailureWatcherRejected("cloud failure-watcher prior unit state was not restored")


def activate_cloud(value: Dict[str, Any]) -> Dict[str, Any]:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise FailureWatcherRejected("cloud failure-watcher activation requires root on Linux")
    artifact = require_active_cloudx("cloud", value["requiredActiveCloudxVersion"])
    require_receipt_producer("cloud", value)
    after = signed_cloud_units(artifact, value)
    paths = {
        "health-service": value["healthServiceUnit"],
        "health-timer": value["healthTimerUnit"],
        "failure-service": value["failureServiceUnit"],
        "failure-path": value["failurePathUnit"],
        "sweep-service": value["sweepServiceUnit"],
        "sweep-path": value["sweepPathUnit"],
    }
    before = {
        name: safe_snapshot(path, required=name.startswith("health-"))
        for name, path in paths.items()
    }
    failure_state = unit_state(CLOUD_FAILURE_PATH_UNIT)
    sweep_state = unit_state(CLOUD_SWEEP_PATH_UNIT)
    health_timer_state = unit_state(CLOUD_HEALTH_TIMER_UNIT)
    if (
        all(before[name].data == raw for name, raw in after.items())
        and failure_state == (True, True)
        and sweep_state == (True, True)
    ):
        return {"schema": RESULT_SCHEMA, "status": "already-active", "target": "cloud"}
    cliproxy = pwd.getpwnam("cliproxy")
    ensure_directory(value["failureDirectory"], mode=0o700, uid=cliproxy.pw_uid, gid=cliproxy.pw_gid)
    ensure_directory(value["sweepDirectory"], mode=0o700, uid=cliproxy.pw_uid, gid=cliproxy.pw_gid)
    destination = backup(
        value["watcherBackupRoot"],
        before,
        uid=0,
        gid=0,
    )
    try:
        for name, path in paths.items():
            atomic_write(path, after[name], mode=0o644, uid=0, gid=0)
        run_command(["systemctl", "daemon-reload"])
        run_command(["systemctl", "enable", "--now", CLOUD_FAILURE_PATH_UNIT, CLOUD_SWEEP_PATH_UNIT])
        if unit_state(CLOUD_FAILURE_PATH_UNIT) != (True, True) or unit_state(CLOUD_SWEEP_PATH_UNIT) != (True, True):
            raise FailureWatcherRejected("cloud failure-watcher path units did not become active")
        if unit_state(CLOUD_HEALTH_TIMER_UNIT) != health_timer_state:
            raise FailureWatcherRejected("cloud CPA health timer state changed")
    except Exception as exc:
        try:
            run_command(
                ["systemctl", "disable", "--now", CLOUD_FAILURE_PATH_UNIT, CLOUD_SWEEP_PATH_UNIT],
                check=False,
            )
            for name, path in paths.items():
                restore_snapshot(path, before[name])
            run_command(["systemctl", "daemon-reload"])
            restore_cloud_state(CLOUD_FAILURE_PATH_UNIT, *failure_state)
            restore_cloud_state(CLOUD_SWEEP_PATH_UNIT, *sweep_state)
            if unit_state(CLOUD_HEALTH_TIMER_UNIT) != health_timer_state:
                restore_cloud_state(CLOUD_HEALTH_TIMER_UNIT, *health_timer_state)
        except Exception as recovery_exc:
            raise FailureWatcherRejected(
                "cloud failure-watcher activation failed and rollback was incomplete"
            ) from recovery_exc
        raise FailureWatcherRejected("cloud failure-watcher activation failed and was rolled back") from exc
    return {"schema": RESULT_SCHEMA, "status": "active", "target": "cloud", "backupName": destination.name}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "cloud"), required=True)
    parser.add_argument("--contract", type=pathlib.Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    value = target_value(args.target, args.contract.expanduser().resolve())
    plan = plan_document(args.target, value)
    if not args.activate:
        print(json.dumps(plan, sort_keys=True))
        return 0
    if args.confirm != plan["confirmation"]:
        raise FailureWatcherRejected("failure-watcher activation confirmation does not match")
    result = activate_local(value) if args.target == "local" else activate_cloud(value)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FailureWatcherRejected as exc:
        print("install_cpa_failure_watcher.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
