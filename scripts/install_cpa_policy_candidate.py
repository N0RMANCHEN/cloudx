#!/usr/bin/env python3
"""Stage or explicitly activate the pinned external CPA policy candidate."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import pathlib
import plistlib
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "third_party/cliproxyapi/deployment-contract.json"
PLAN_SCHEMA = "cloudx.cliproxy-policy-deployment-plan.v1"
RESULT_SCHEMA = "cloudx.cliproxy-policy-deployment.v1"
MAX_CANDIDATE_BYTES = 100 * 1024 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_LAUNCHER_BYTES = 256 * 1024
MAX_DROP_IN_BYTES = 64 * 1024
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
COMMUNICATION_CANARY_TEXT = "LOCAL_CPA_POLICY_COMMUNICATION_OK"
COMMUNICATION_CANARY_TIMEOUT_SECONDS = 180.0
CPA_CANARY_READY_TIMEOUT_SECONDS = 20.0
CPA_CANARY_RETRY_INTERVAL_SECONDS = 0.25
CAPABILITY_HEADER = "X-Cloudx-CPA-Capabilities"
CAPABILITY_SCHEMAS = {"local": "cloudx.local-cpa-capabilities.v1", "cloud": "cloudx.cloud-cpa-capabilities.v1"}


class CpaPolicyInstallRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    existed: bool
    data: bytes
    mode: int
    uid: int
    gid: int


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_snapshot(path: pathlib.Path, *, maximum: int, required: bool) -> Snapshot:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        if required:
            raise CpaPolicyInstallRejected("required CPA policy file is missing")
        return Snapshot(False, b"", 0, 0, 0)
    except OSError as exc:
        raise CpaPolicyInstallRejected("CPA policy file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise CpaPolicyInstallRejected("CPA policy file is unsafe or oversized")
        chunks = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise CpaPolicyInstallRejected("CPA policy file is oversized")
        return Snapshot(True, raw, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)
    finally:
        os.close(descriptor)


def fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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


def ensure_directory(path: pathlib.Path, *, mode: int, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise CpaPolicyInstallRejected("CPA policy directory is unsafe")
    os.chown(path, uid, gid)
    path.chmod(mode)


def remove_created_empty_directories(paths: Sequence[pathlib.Path]) -> None:
    for path in paths:
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or any(path.iterdir()):
            raise CpaPolicyInstallRejected("CPA policy rollback directory is not empty or safe")
    for path in reversed(paths):
        try:
            path.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CpaPolicyInstallRejected("CPA policy rollback directory could not be removed") from exc
        if path.parent.is_dir():
            fsync_directory(path.parent)


def run_command(
    argv: Sequence[str],
    *,
    check: bool = True,
    timeout: float = 30.0,
    environment: Optional[Dict[str, str]] = None,
    cwd: Optional[pathlib.Path] = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CpaPolicyInstallRejected("CPA policy service command failed") from exc
    if check and completed.returncode != 0:
        raise CpaPolicyInstallRejected("CPA policy service command was rejected")
    return completed


def load_contract(path: pathlib.Path) -> Dict[str, Any]:
    value = safe_snapshot(path, maximum=MAX_CONFIG_BYTES, required=True)
    try:
        document = json.loads(value.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CpaPolicyInstallRejected("CPA deployment contract is invalid") from exc
    if document.get("schema") != "cloudx.cliproxy-policy-deployment.v1":
        raise CpaPolicyInstallRejected("CPA deployment contract schema is invalid")
    targets = document.get("targets")
    if not isinstance(targets, dict) or set(targets) != {"local", "cloud"}:
        raise CpaPolicyInstallRejected("CPA deployment targets are invalid")
    return document


def expanded_target(target: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    raw = contract["targets"].get(target)
    if not isinstance(raw, dict):
        raise CpaPolicyInstallRejected("CPA deployment target is unavailable")
    value = dict(raw)
    if not VERSION_RE.fullmatch(str(value.get("version") or "")):
        raise CpaPolicyInstallRejected("CPA deployment version is invalid")
    if not SHA256_RE.fullmatch(str(value.get("candidateSha256") or "")):
        raise CpaPolicyInstallRejected("CPA candidate digest is invalid")
    if not SHA256_RE.fullmatch(str(value.get("baselineSha256") or "")):
        raise CpaPolicyInstallRejected("CPA baseline digest is invalid")
    if not VERSION_RE.fullmatch(str(value.get("requiredActiveCloudxVersion") or "")):
        raise CpaPolicyInstallRejected("required active Cloudx version is invalid")
    if target == "local":
        home = pathlib.Path.home().resolve()
        for key in (
            "baselineBinary",
            "stageRoot",
            "backupRoot",
            "authDirectory",
            "failureDirectory",
            "sweepDirectory",
            "config",
            "launcher",
            "capabilityManifest",
        ):
            value[key] = home / str(value[key])
        codex_binary = pathlib.Path(str(value.get("codexBinary") or ""))
        if not codex_binary.is_absolute():
            raise CpaPolicyInstallRejected("local communication Codex binary path is invalid")
        codex_home_relative = pathlib.Path(str(value.get("communicationCodexHome") or ""))
        if codex_home_relative.is_absolute() or ".." in codex_home_relative.parts:
            raise CpaPolicyInstallRejected("local communication Codex home path is invalid")
        value["codexBinary"] = codex_binary
        value["communicationCodexHome"] = home / codex_home_relative
    else:
        for key in (
            "baselineBinary",
            "stageRoot",
            "backupRoot",
            "authDirectory",
            "failureDirectory",
            "sweepDirectory",
            "config",
            "capabilityManifest",
            "gatewayDropIn",
            "healthDropIn",
        ):
            path = pathlib.Path(str(value[key]))
            if not path.is_absolute():
                raise CpaPolicyInstallRejected("cloud CPA deployment path is not absolute")
            value[key] = path
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities or any(
        not isinstance(item, str) or not VERSION_RE.fullmatch(item) for item in capabilities
    ):
        raise CpaPolicyInstallRejected("CPA capabilities are invalid")
    value["stagedBinary"] = value["stageRoot"] / value["version"] / "cli-proxy-api"
    return value


def confirmations(target: str, value: Dict[str, Any]) -> Tuple[str, str]:
    label = target.upper()
    suffix = str(value["candidateSha256"])[:12]
    return (
        "STAGE %s CPA POLICY %s %s" % (label, value["version"], suffix),
        "ACTIVATE %s CPA POLICY %s %s" % (label, value["version"], suffix),
    )


def plan_document(target: str, value: Dict[str, Any]) -> Dict[str, Any]:
    stage_confirmation, activate_confirmation = confirmations(target, value)
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "target": target,
        "version": value["version"],
        "candidateSha256": value["candidateSha256"],
        "requiredActiveCloudxVersion": value["requiredActiveCloudxVersion"],
        "stageConfirmation": stage_confirmation,
        "activationConfirmation": activate_confirmation,
        "maxConcurrentAPIRequests": 2,
        "weeklyQuotaArchived": False,
        "periodicAccountProbe": False,
        "incidentSweepTrigger": True,
        "incidentProbeConcurrency": "adaptive-up-to-32",
        "requiredCapabilities": list(value.get("capabilities", [])),
        "stageChangesService": False,
        "activationRestartsExternalCPA": True,
        "activationStopsCodexProcesses": False,
        "gracefulCPAServiceRestart": True,
        "inFlightRequestContinuityGuaranteed": False,
        "localActivationRequiresRealCodexCanary": target == "local",
        "localActivationRollsBackOnCommunicationFailure": target == "local",
        "localActivationRequiresPreparedRecoveryTool": target == "local",
        "localActivationRequiresZeroEstablishedConnections": target == "local",
        "eventDrivenArchiveWatcherActivationSeparate": True,
        "automaticAction": False,
    }


def require_active_cloudx(target: str, value: Dict[str, Any]) -> None:
    artifact = (
        pathlib.Path.home() / ".local/lib/cloudx/current/cloudx-local.pyz"
        if target == "local"
        else pathlib.Path("/opt/cloudx/current/cloudx-cloud.pyz")
    )
    safe_snapshot(artifact, maximum=MAX_CANDIDATE_BYTES, required=True)
    completed = run_command([sys.executable, str(artifact), "self-check"], timeout=30.0)
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CpaPolicyInstallRejected("active Cloudx self-check is invalid") from exc
    if (
        document.get("schema") != "cloudx.self-check.v1"
        or document.get("status") != "ok"
        or document.get("version") != value["requiredActiveCloudxVersion"]
    ):
        raise CpaPolicyInstallRejected("required signed Cloudx receipt consumer is not active")


def verify_candidate(path: pathlib.Path, value: Dict[str, Any]) -> Snapshot:
    candidate = safe_snapshot(path, maximum=MAX_CANDIDATE_BYTES, required=True)
    if len(candidate.data) != int(value["candidateSize"]):
        raise CpaPolicyInstallRejected("CPA candidate size does not match")
    if sha256_bytes(candidate.data) != value["candidateSha256"]:
        raise CpaPolicyInstallRejected("CPA candidate digest does not match")
    completed = run_command([str(path), "-h"], check=False, timeout=10.0)
    output = (completed.stdout + completed.stderr).splitlines()
    expected = "CLIProxyAPI Version: %s," % value["version"]
    if completed.returncode != 0 or not output or not output[0].startswith(expected):
        raise CpaPolicyInstallRejected("CPA candidate runtime identity does not match")
    return candidate


def stage_candidate(target: str, candidate_path: pathlib.Path, value: Dict[str, Any]) -> Dict[str, Any]:
    if target == "cloud" and os.geteuid() != 0:
        raise CpaPolicyInstallRejected("cloud CPA staging must run as root")
    candidate = verify_candidate(candidate_path, value)
    uid = 0 if target == "cloud" else os.geteuid()
    gid = 0 if target == "cloud" else os.getegid()
    directory_mode = 0o755 if target == "cloud" else 0o700
    binary_mode = 0o755 if target == "cloud" else 0o700
    release_dir = value["stagedBinary"].parent
    ensure_directory(value["stageRoot"], mode=directory_mode, uid=uid, gid=gid)
    ensure_directory(release_dir, mode=directory_mode, uid=uid, gid=gid)
    final = value["stagedBinary"]
    status = "staged"
    if final.exists():
        existing = verify_candidate(final, value)
        if existing.data != candidate.data:
            raise CpaPolicyInstallRejected("existing staged CPA candidate differs")
        status = "already-staged"
    else:
        atomic_write(final, candidate.data, mode=binary_mode, uid=uid, gid=gid)
        verify_candidate(final, value)
    manifest = {
        "schema": "cloudx.cliproxy-policy-stage.v1",
        "target": target,
        "version": value["version"],
        "sha256": value["candidateSha256"],
        "size": value["candidateSize"],
        "capabilities": list(value.get("capabilities", [])),
    }
    atomic_write(
        release_dir / "manifest.json",
        (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o644 if target == "cloud" else 0o600,
        uid=uid,
        gid=gid,
    )
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "target": target,
        "version": value["version"],
        "sha256": value["candidateSha256"],
        "externalServiceManaged": False,
        "externalServiceRestarted": False,
    }


def top_level_config(path: pathlib.Path) -> Tuple[str, int]:
    raw = safe_snapshot(path, maximum=MAX_CONFIG_BYTES, required=True).data
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CpaPolicyInstallRejected("CPA config is not UTF-8") from exc
    values: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if key in {"host", "port"}:
            values[key] = raw_value.split("#", 1)[0].strip().strip("\"'")
    host = values.get("host", "")
    try:
        port = int(values.get("port", ""))
    except ValueError as exc:
        raise CpaPolicyInstallRejected("CPA config port is invalid") from exc
    if not host or not 1 <= port <= 65535:
        raise CpaPolicyInstallRejected("CPA config endpoint is invalid")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1" if host == "0.0.0.0" else "::1"
    return host, port


def probe_health(config: pathlib.Path, required_capability: str = "") -> None:
    host, port = top_level_config(config)
    deadline = time.monotonic() + CPA_CANARY_READY_TIMEOUT_SECONDS
    saw_response = False
    last_error: Optional[BaseException] = None
    while True:
        connection: Optional[http.client.HTTPConnection] = None
        try:
            connection = http.client.HTTPConnection(host, port, timeout=5.0)
            connection.request("GET", "/healthz")
            health = connection.getresponse()
            health_body = health.read(4096)
            live_capabilities = health.getheader(CAPABILITY_HEADER, "")
            saw_response = True
            if (
                health.status == 200
                and b'"status":"ok"' in health_body.replace(b" ", b"")
                and (
                    not required_capability
                    or required_capability in {item.strip() for item in live_capabilities.split(",")}
                )
            ):
                return
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if connection is not None:
                connection.close()
        if time.monotonic() >= deadline:
            break
        time.sleep(CPA_CANARY_RETRY_INTERVAL_SECONDS)
    if saw_response:
        raise CpaPolicyInstallRejected("CPA health canary failed")
    raise CpaPolicyInstallRejected("CPA health canary could not connect") from last_error


def probe_policy(config: pathlib.Path) -> Tuple[int, str]:
    probe_health(config)
    host, port = top_level_config(config)
    deadline = time.monotonic() + CPA_CANARY_READY_TIMEOUT_SECONDS
    last_error: Optional[BaseException] = None
    while True:
        connection: Optional[http.client.HTTPConnection] = None
        try:
            connection = http.client.HTTPConnection(host, port, timeout=5.0)
            connection.request(
                "POST",
                "/v1/responses",
                body=b"{}",
                headers={
                    "Authorization": "Bearer cloudx-policy-invalid-canary",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            response.read(4096)
            policy = response.getheader("X-CPA-Max-Concurrent-API-Requests", "")
            status = response.status
            if status not in {400, 401, 403} or policy != "2":
                raise CpaPolicyInstallRejected("CPA concurrency policy canary failed")
            return status, policy
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if connection is not None:
                connection.close()
        if time.monotonic() >= deadline:
            break
        time.sleep(CPA_CANARY_RETRY_INTERVAL_SECONDS)
    raise CpaPolicyInstallRejected("CPA policy canary could not connect") from last_error


def probe_local_communication(value: Dict[str, Any]) -> str:
    codex_binary = value["codexBinary"]
    codex_home = value["communicationCodexHome"]
    if not codex_binary.is_file() or not os.access(codex_binary, os.X_OK):
        raise CpaPolicyInstallRejected("official Codex communication canary binary is unavailable")
    if codex_home.is_symlink() or not codex_home.is_dir():
        raise CpaPolicyInstallRejected("local CPA communication account is unavailable")
    environment = dict(os.environ)
    environment["HOME"] = str(pathlib.Path.home().resolve())
    environment["CODEX_HOME"] = str(codex_home)
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "CLOUDX_MODE",
        "CLOUDX_MODE_LEASE_ID",
        "CLOUDX_MODE_BROKER_PORT",
        "CODEXX_ACTIVE_ACCOUNT",
        "CODEXX_ACTIVE_HOME",
        "CODEXX_ACTIVE_PINNED",
    ):
        environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-communication-canary-") as temporary:
        completed = run_command(
            [
                str(codex_binary),
                "exec",
                "--skip-git-repo-check",
                "Reply with exactly %s" % COMMUNICATION_CANARY_TEXT,
            ],
            check=False,
            timeout=COMMUNICATION_CANARY_TIMEOUT_SECONDS,
            environment=environment,
            cwd=pathlib.Path(temporary),
        )
    output = completed.stdout + "\n" + completed.stderr
    if completed.returncode != 0 or COMMUNICATION_CANARY_TEXT not in output:
        raise CpaPolicyInstallRejected("local CPA real Codex communication canary failed")
    return "passed"


def backup_snapshot(root: pathlib.Path, name: str, snapshots: Dict[str, Snapshot], *, uid: int, gid: int) -> pathlib.Path:
    ensure_directory(root, mode=0o700, uid=uid, gid=gid)
    backup = root / ("%d-%s" % (time.time_ns(), name))
    ensure_directory(backup, mode=0o700, uid=uid, gid=gid)
    manifest: Dict[str, Any] = {"schema": "cloudx.cliproxy-policy-backup.v1", "files": {}}
    for label, value in snapshots.items():
        manifest["files"][label] = {
            "existed": value.existed,
            "mode": value.mode,
            "uid": value.uid,
            "gid": value.gid,
            "sha256": sha256_bytes(value.data) if value.existed else "",
        }
        if value.existed:
            atomic_write(backup / (label + ".before"), value.data, mode=0o600, uid=uid, gid=gid)
    atomic_write(
        backup / "manifest.json",
        (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o600,
        uid=uid,
        gid=gid,
    )
    return backup


def wait_systemd_active(unit: str) -> int:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        completed = run_command(
            ["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "MainPID", "--no-pager"],
            check=False,
        )
        values = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
        if values.get("ActiveState") == "active" and values.get("SubState") == "running":
            pid = int(values.get("MainPID", "0") or "0")
            if pid > 0:
                return pid
        time.sleep(0.25)
    raise CpaPolicyInstallRejected("CPA systemd service did not become active")


def cloud_drop_ins(value: Dict[str, Any]) -> Tuple[bytes, bytes]:
    gateway = (
        "[Service]\n"
        "Environment=CLIPROXY_AUTH_DIR=%s\n"
        "Environment=CLIPROXY_AUTH_FAILURE_DIR=%s\n"
        "Environment=CLIPROXY_AUTH_SWEEP_DIR=%s\n"
        "ReadWritePaths=%s %s\n"
        "ExecStart=\n"
        "ExecStart=%s -config %s\n"
        % (
            value["authDirectory"], value["failureDirectory"], value["sweepDirectory"],
            value["failureDirectory"], value["sweepDirectory"], value["stagedBinary"], value["config"],
        )
    ).encode("utf-8")
    health = (
        "[Service]\nReadWritePaths=%s %s\n"
        % (value["failureDirectory"], value["sweepDirectory"])
    ).encode("utf-8")
    return gateway, health


def capability_manifest_bytes(target: str, value: Dict[str, Any]) -> bytes:
    return (json.dumps({
        "schema": CAPABILITY_SCHEMAS[target],
        "binary": str(value["stagedBinary"]),
        "binarySha256": value["candidateSha256"],
        "runtimeVersion": value["version"],
        "capabilities": list(value["capabilities"]),
    }, sort_keys=True) + "\n").encode("utf-8")


def activate_cloud(value: Dict[str, Any]) -> Dict[str, Any]:
    if os.geteuid() != 0 or sys.platform != "linux":
        raise CpaPolicyInstallRejected("cloud CPA activation requires root on Linux")
    require_active_cloudx("cloud", value)
    verify_candidate(value["stagedBinary"], value)
    baseline = safe_snapshot(value["baselineBinary"], maximum=MAX_CANDIDATE_BYTES, required=True)
    if sha256_bytes(baseline.data) != value["baselineSha256"]:
        raise CpaPolicyInstallRejected("cloud CPA baseline binary changed")
    gateway_before = safe_snapshot(value["gatewayDropIn"], maximum=MAX_DROP_IN_BYTES, required=False)
    health_before = safe_snapshot(value["healthDropIn"], maximum=MAX_DROP_IN_BYTES, required=False)
    capability_before = safe_snapshot(value["capabilityManifest"], maximum=MAX_DROP_IN_BYTES, required=False)
    gateway_after, health_after = cloud_drop_ins(value)
    capability_after = capability_manifest_bytes("cloud", value)
    if (
        gateway_before.existed
        and gateway_before.data == gateway_after
        and health_before.existed
        and health_before.data == health_after
        and capability_before.existed
        and capability_before.data == capability_after
    ):
        pid = wait_systemd_active(value["service"])
        status, policy = probe_policy(value["config"])
        probe_health(value["config"], value["capabilities"][0])
        return {"schema": RESULT_SCHEMA, "status": "already-active", "target": "cloud", "pid": pid, "httpStatus": status, "policy": policy}
    cliproxy = pwd.getpwnam("cliproxy")
    created_directories = [
        path for path in (value["failureDirectory"], value["sweepDirectory"]) if not path.exists()
    ]
    ensure_directory(value["failureDirectory"], mode=0o700, uid=cliproxy.pw_uid, gid=cliproxy.pw_gid)
    ensure_directory(value["sweepDirectory"], mode=0o700, uid=cliproxy.pw_uid, gid=cliproxy.pw_gid)
    backup = backup_snapshot(
        value["backupRoot"],
        "cloud",
        {
            "gateway-drop-in": gateway_before,
            "health-drop-in": health_before,
            "capability-manifest": capability_before,
        },
        uid=0,
        gid=0,
    )
    try:
        atomic_write(value["gatewayDropIn"], gateway_after, mode=0o644, uid=0, gid=0)
        atomic_write(value["healthDropIn"], health_after, mode=0o644, uid=0, gid=0)
        run_command(["systemctl", "daemon-reload"])
        run_command(["systemctl", "restart", value["service"]])
        pid = wait_systemd_active(value["service"])
        show = run_command(["systemctl", "show", value["service"], "-p", "ExecStart", "--no-pager"]).stdout
        if str(value["stagedBinary"]) not in show:
            raise CpaPolicyInstallRejected("cloud CPA service did not select the staged candidate")
        status, policy = probe_policy(value["config"])
        probe_health(value["config"], value["capabilities"][0])
        if sha256_bytes(safe_snapshot(value["baselineBinary"], maximum=MAX_CANDIDATE_BYTES, required=True).data) != value["baselineSha256"]:
            raise CpaPolicyInstallRejected("cloud CPA baseline changed during activation")
        atomic_write(value["capabilityManifest"], capability_after, mode=0o644, uid=0, gid=0)
    except Exception as exc:
        try:
            restore_snapshot(value["gatewayDropIn"], gateway_before)
            restore_snapshot(value["healthDropIn"], health_before)
            restore_snapshot(value["capabilityManifest"], capability_before)
            run_command(["systemctl", "daemon-reload"], check=False)
            run_command(["systemctl", "restart", value["service"]], check=False)
            wait_systemd_active(value["service"])
            probe_health(value["config"])
            remove_created_empty_directories(created_directories)
        except Exception as recovery_exc:
            raise CpaPolicyInstallRejected(
                "cloud CPA activation failed; baseline restoration verification failed"
            ) from recovery_exc
        raise CpaPolicyInstallRejected("cloud CPA activation failed and was rolled back") from exc
    return {
        "schema": RESULT_SCHEMA,
        "status": "active",
        "target": "cloud",
        "version": value["version"],
        "pid": pid,
        "httpStatus": status,
        "policy": policy,
        "capabilities": list(value["capabilities"]),
        "backupName": backup.name,
        "externalServiceManaged": False,
        "operatorApprovedRestart": True,
    }


def local_plist(raw: bytes, value: Dict[str, Any]) -> bytes:
    try:
        document = plistlib.loads(raw)
    except Exception as exc:
        raise CpaPolicyInstallRejected("local CPA launcher plist is invalid") from exc
    if document.get("Label") != value["serviceLabel"]:
        raise CpaPolicyInstallRejected("local CPA launcher label changed")
    arguments = document.get("ProgramArguments")
    if not isinstance(arguments, list) or not arguments:
        raise CpaPolicyInstallRejected("local CPA launcher arguments are invalid")
    document["ProgramArguments"] = [str(value["stagedBinary"]), *arguments[1:]]
    environment = document.get("EnvironmentVariables")
    if environment is None:
        environment = {}
    if not isinstance(environment, dict):
        raise CpaPolicyInstallRejected("local CPA launcher environment is invalid")
    environment.update({"CLIPROXY_AUTH_DIR": str(value["authDirectory"]), "CLIPROXY_AUTH_FAILURE_DIR": str(value["failureDirectory"]), "CLIPROXY_AUTH_SWEEP_DIR": str(value["sweepDirectory"])})
    document["EnvironmentVariables"] = environment
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=False)

def wait_launchd(domain: str, label: str, expected_binary: pathlib.Path) -> int:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        completed = run_command(["launchctl", "print", "%s/%s" % (domain, label)], check=False)
        match = re.search(r"\bpid = ([0-9]+)", completed.stdout)
        if completed.returncode == 0 and match and any(line.strip() == "program = %s" % expected_binary for line in completed.stdout.splitlines()):
            return int(match.group(1))
        time.sleep(0.25)
    raise CpaPolicyInstallRejected("local CPA launchd service did not become active")

def wait_launchd_unloaded(domain: str, label: str) -> None:
    deadline = time.monotonic() + 30.0
    absent_samples = 0
    while time.monotonic() < deadline:
        completed = run_command(["launchctl", "print", "%s/%s" % (domain, label)], check=False)
        absent_samples = absent_samples + 1 if completed.returncode != 0 else 0
        if absent_samples >= 3:
            return
        time.sleep(0.25)
    raise CpaPolicyInstallRejected("local CPA launchd service did not fully unload")


def run_local_recovery(tool: pathlib.Path, job: pathlib.Path, confirmation: str, *, quiescence: bool) -> Dict[str, Any]:
    if tool.is_symlink() or not tool.is_file() or job.is_symlink() or not job.is_dir():
        raise CpaPolicyInstallRejected("local CPA recovery bundle is unavailable")
    arguments = [sys.executable, str(tool), "--job", str(job)]
    arguments.extend(["--check-quiescent"] if quiescence else ["--apply", "--confirm", confirmation])
    completed = run_command(arguments, check=False, timeout=360.0)
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CpaPolicyInstallRejected("local CPA recovery tool returned invalid output") from exc
    accepted = {"quiescent"} if quiescence else {"recovered", "already-recovered"}
    if completed.returncode != 0 or document.get("status") not in accepted:
        message = "local CPA activation requires zero established connections" if quiescence else "local CPA baseline recovery tool failed"
        raise CpaPolicyInstallRejected(message)
    return document


def activate_local(value: Dict[str, Any], recovery_tool: pathlib.Path, recovery_job: pathlib.Path, recovery_confirm: str) -> Dict[str, Any]:
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise CpaPolicyInstallRejected("local CPA activation requires the macOS login user")
    require_active_cloudx("local", value)
    verify_candidate(value["stagedBinary"], value)
    baseline = safe_snapshot(value["baselineBinary"], maximum=MAX_CANDIDATE_BYTES, required=True)
    if sha256_bytes(baseline.data) != value["baselineSha256"]:
        raise CpaPolicyInstallRejected("local CPA baseline binary changed")
    launcher_before = safe_snapshot(value["launcher"], maximum=MAX_LAUNCHER_BYTES, required=True)
    launcher_after = local_plist(launcher_before.data, value)
    capability_before = safe_snapshot(value["capabilityManifest"], maximum=MAX_DROP_IN_BYTES, required=False)
    capability_after = capability_manifest_bytes("local", value)
    uid = os.geteuid()
    gid = os.getegid()
    domain = "gui/%d" % uid
    launch_before = run_command(["launchctl", "print", "%s/%s" % (domain, value["serviceLabel"])])
    if launcher_before.data != launcher_after and not any(line.strip() == "program = %s" % value["baselineBinary"] for line in launch_before.stdout.splitlines()):
        raise CpaPolicyInstallRejected("local CPA service does not select the pinned baseline")
    probe_local_communication(value)
    if launcher_before.data == launcher_after:
        pid = wait_launchd(domain, value["serviceLabel"], value["stagedBinary"])
        status, policy = probe_policy(value["config"])
        probe_health(value["config"], value["capabilities"][0])
        communication = probe_local_communication(value)
        if not capability_before.existed or capability_before.data != capability_after:
            atomic_write(value["capabilityManifest"], capability_after, mode=0o600, uid=uid, gid=gid)
        return {"schema": RESULT_SCHEMA, "status": "already-active", "target": "local", "pid": pid, "httpStatus": status, "policy": policy, "capabilities": list(value["capabilities"]), "communicationCanary": communication}
    run_local_recovery(recovery_tool, recovery_job, recovery_confirm, quiescence=True)
    created_directories = [
        path for path in (value["failureDirectory"], value["sweepDirectory"]) if not path.exists()
    ]
    ensure_directory(value["failureDirectory"], mode=0o700, uid=uid, gid=gid)
    ensure_directory(value["sweepDirectory"], mode=0o700, uid=uid, gid=gid)
    backup = backup_snapshot(
        value["backupRoot"],
        "local",
        {"launcher": launcher_before, "capability-manifest": capability_before},
        uid=uid,
        gid=gid,
    )
    service = "%s/%s" % (domain, value["serviceLabel"])
    try:
        atomic_write(
            value["launcher"],
            launcher_after,
            mode=launcher_before.mode,
            uid=launcher_before.uid,
            gid=launcher_before.gid,
        )
        run_command(["launchctl", "bootout", service], check=False, timeout=45.0)
        wait_launchd_unloaded(domain, value["serviceLabel"])
        run_command(["launchctl", "bootstrap", domain, str(value["launcher"])])
        pid = wait_launchd(domain, value["serviceLabel"], value["stagedBinary"])
        status, policy = probe_policy(value["config"])
        probe_health(value["config"], value["capabilities"][0])
        if sha256_bytes(safe_snapshot(value["baselineBinary"], maximum=MAX_CANDIDATE_BYTES, required=True).data) != value["baselineSha256"]:
            raise CpaPolicyInstallRejected("local CPA baseline changed during activation")
        communication = probe_local_communication(value)
        atomic_write(value["capabilityManifest"], capability_after, mode=0o600, uid=uid, gid=gid)
    except Exception as exc:
        try:
            run_local_recovery(recovery_tool, recovery_job, recovery_confirm, quiescence=False)
            restore_snapshot(value["capabilityManifest"], capability_before)
            remove_created_empty_directories(created_directories)
        except Exception as recovery_exc:
            raise CpaPolicyInstallRejected(
                "local CPA activation failed; baseline restoration verification failed"
            ) from recovery_exc
        raise CpaPolicyInstallRejected("local CPA activation failed and was rolled back") from exc
    return {"schema": RESULT_SCHEMA, "status": "active", "target": "local", "version": value["version"], "pid": pid, "httpStatus": status, "policy": policy, "capabilities": list(value["capabilities"]), "communicationCanary": communication, "backupName": backup.name, "externalServiceManaged": False, "operatorApprovedRestart": True}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "cloud"), required=True)
    parser.add_argument("--contract", type=pathlib.Path, default=DEFAULT_CONTRACT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--stage", action="store_true")
    action.add_argument("--activate", action="store_true")
    parser.add_argument("--candidate", type=pathlib.Path)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--recovery-tool", type=pathlib.Path)
    parser.add_argument("--recovery-job", type=pathlib.Path)
    parser.add_argument("--recovery-confirm", default="")
    args = parser.parse_args(argv)

    contract = load_contract(args.contract.expanduser().resolve())
    value = expanded_target(args.target, contract)
    stage_confirmation, activate_confirmation = confirmations(args.target, value)
    if not args.stage and not args.activate:
        print(json.dumps(plan_document(args.target, value), sort_keys=True))
        return 0
    if args.stage:
        if args.confirm != stage_confirmation or args.candidate is None:
            raise CpaPolicyInstallRejected("CPA stage confirmation or candidate does not match")
        document = stage_candidate(args.target, args.candidate.expanduser().resolve(), value)
    else:
        if args.confirm != activate_confirmation or args.candidate is not None:
            raise CpaPolicyInstallRejected("CPA activation confirmation does not match")
        if args.target == "local":
            if args.recovery_tool is None or args.recovery_job is None or not args.recovery_confirm:
                raise CpaPolicyInstallRejected("local CPA activation requires a prepared recovery bundle")
            document = activate_local(value, args.recovery_tool.expanduser().resolve(), args.recovery_job.expanduser().resolve(), args.recovery_confirm)
        else:
            if args.recovery_tool is not None or args.recovery_job is not None or args.recovery_confirm:
                raise CpaPolicyInstallRejected("cloud CPA activation rejects local recovery arguments")
            document = activate_cloud(value)
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CpaPolicyInstallRejected as exc:
        print("install_cpa_policy_candidate.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
