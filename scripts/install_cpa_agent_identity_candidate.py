#!/usr/bin/env python3
"""Stage or explicitly activate the local Agent Identity CPA candidate."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import pathlib
import plistlib
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "third_party/cliproxyapi/agent-identity-deployment-contract.json"
CAPABILITY_SCHEMA = "cloudx.local-cpa-capabilities.v1"
CAPABILITY_HEADER = "X-Cloudx-CPA-Capabilities"
RESULT_SCHEMA = "cloudx.cliproxy-agent-identity-install.v1"
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_AUTH_FILES = 4096


class AgentIdentityInstallRejected(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_file(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> Tuple[bytes, int]:
    if not path.is_absolute() or path.is_symlink():
        raise AgentIdentityInstallRejected("required file is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise AgentIdentityInstallRejected("required file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise AgentIdentityInstallRejected("required file is unsafe")
        chunks = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise AgentIdentityInstallRejected("required file could not be read safely") from exc
    finally:
        os.close(descriptor)
    if len(raw) > maximum or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise AgentIdentityInstallRejected("required file changed while it was read")
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise AgentIdentityInstallRejected("required file is unavailable") from exc
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise AgentIdentityInstallRejected("required file changed while it was read")
    return raw, stat.S_IMODE(after.st_mode)


def safe_bytes(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    return safe_file(path, maximum)[0]


def atomic_write(path: pathlib.Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_contract(path: pathlib.Path = DEFAULT_CONTRACT) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentIdentityInstallRejected("deployment contract is unavailable") from exc
    required = {
        "version",
        "candidateSha256",
        "candidateSize",
        "requiredActiveCloudxVersion",
        "baselineBinary",
        "baselineSha256",
        "baselineMetadata",
        "baselineMetadataSha256",
        "stageRoot",
        "backupRoot",
        "capabilityManifest",
        "authDirectory",
        "config",
        "launcher",
        "serviceLabel",
        "listenHost",
        "listenPort",
        "capabilities",
    }
    if document.get("schema") != "cloudx.cliproxy-agent-identity-deployment.v1" or not required.issubset(document):
        raise AgentIdentityInstallRejected("deployment contract is invalid")
    if document["capabilities"] != ["codex-agent-identity-v1"]:
        raise AgentIdentityInstallRejected("deployment capability is invalid")
    return document


def expanded_contract(document: Dict[str, Any], home: pathlib.Path) -> Dict[str, Any]:
    if not home.is_absolute() or home.is_symlink():
        raise AgentIdentityInstallRejected("local home is unsafe")
    result = dict(document)
    for key in (
        "baselineBinary",
        "baselineMetadata",
        "stageRoot",
        "backupRoot",
        "capabilityManifest",
        "authDirectory",
        "config",
        "launcher",
    ):
        relative = pathlib.PurePosixPath(str(document[key]))
        if relative.is_absolute() or ".." in relative.parts:
            raise AgentIdentityInstallRejected("deployment path is unsafe")
        result[key] = home.joinpath(*relative.parts)
    result["stagedBinary"] = result["stageRoot"] / result["version"] / "cli-proxy-api"
    return result


def confirmations(value: Dict[str, Any]) -> Tuple[str, str]:
    return (
        "STAGE LOCAL CPA AGENT IDENTITY %s" % value["version"],
        "ACTIVATE LOCAL CPA AGENT IDENTITY %s" % value["version"],
    )


def plan_document(value: Dict[str, Any]) -> Dict[str, Any]:
    stage, activate = confirmations(value)
    return {
        "schema": RESULT_SCHEMA,
        "status": "confirmation-required",
        "version": value["version"],
        "stageConfirmation": stage,
        "activationConfirmation": activate,
        "stageChangesService": False,
        "activationRestartsExternalCPA": True,
        "activationRequiresZeroEstablishedConnections": True,
        "activationPreservesBaselineBinary": True,
        "activationWritesHashBoundCapabilityManifest": True,
        "cloudxManagesExternalServiceLifecycle": False,
        "automaticActivation": False,
    }


def verify_candidate(path: pathlib.Path, value: Dict[str, Any]) -> bytes:
    raw = safe_bytes(path)
    if len(raw) != value["candidateSize"] or sha256_bytes(raw) != value["candidateSha256"]:
        raise AgentIdentityInstallRejected("candidate identity does not match")
    return raw


def stage_candidate(path: pathlib.Path, value: Dict[str, Any]) -> Dict[str, Any]:
    raw = verify_candidate(path, value)
    target = value["stagedBinary"]
    release = target.parent
    release.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(release, 0o700)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or safe_bytes(target) != raw:
            raise AgentIdentityInstallRejected("staged candidate conflicts with existing bytes")
        status = "already-staged"
    else:
        atomic_write(target, raw, 0o700)
        status = "staged"
    metadata = {
        "schema": "cloudx.cliproxy-agent-identity-stage.v1",
        "version": value["version"],
        "binarySha256": value["candidateSha256"],
        "binarySize": value["candidateSize"],
        "capabilities": value["capabilities"],
    }
    atomic_write(
        release / "manifest.json",
        (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o600,
    )
    return {"schema": RESULT_SCHEMA, "status": status, "version": value["version"], "serviceChanged": False}


def run_command(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(arguments),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentIdentityInstallRejected("local service command failed") from exc


def require_active_cloudx(value: Dict[str, Any], home: pathlib.Path) -> None:
    artifact = home / ".local/lib/cloudx/current/cloudx-local.pyz"
    completed = run_command([str(artifact), "self-check", "--json"])
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AgentIdentityInstallRejected("active Cloudx self-check is unavailable") from exc
    if completed.returncode != 0 or document.get("status") != "ok" or document.get("version") != value["requiredActiveCloudxVersion"]:
        raise AgentIdentityInstallRejected("required signed Cloudx version is not active")


def auth_inventory(directory: pathlib.Path) -> Tuple[int, str]:
    if not directory.is_dir() or directory.is_symlink():
        raise AgentIdentityInstallRejected("CPA auth directory is unsafe")
    paths = sorted(directory.glob("*.json"))
    if len(paths) > MAX_AUTH_FILES:
        raise AgentIdentityInstallRejected("CPA auth inventory is too large")
    digest = hashlib.sha256()
    for path in paths:
        raw = safe_bytes(path, 16 * 1024 * 1024)
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
    return len(paths), digest.hexdigest()


def launcher_bytes(value: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
    raw = safe_bytes(value["launcher"], 1024 * 1024)
    try:
        document = plistlib.loads(raw)
    except Exception as exc:
        raise AgentIdentityInstallRejected("CPA launcher is invalid") from exc
    arguments = document.get("ProgramArguments")
    if document.get("Label") != value["serviceLabel"] or not isinstance(arguments, list) or not arguments:
        raise AgentIdentityInstallRejected("CPA launcher identity does not match")
    return raw, document


def updated_launcher(document: Dict[str, Any], value: Dict[str, Any]) -> bytes:
    updated = dict(document)
    arguments = list(updated["ProgramArguments"])
    arguments[0] = str(value["stagedBinary"])
    updated["ProgramArguments"] = arguments
    return plistlib.dumps(updated, fmt=plistlib.FMT_XML, sort_keys=True)


def zero_established_connections(value: Dict[str, Any]) -> None:
    command = [
        "lsof",
        "-nP",
        "-iTCP:%d" % value["listenPort"],
        "-sTCP:ESTABLISHED",
        "-t",
    ]
    consecutive = 0
    for unused in range(30):
        completed = run_command(command)
        if completed.returncode not in {0, 1}:
            raise AgentIdentityInstallRejected("CPA connection audit failed")
        if not completed.stdout.strip():
            consecutive += 1
            if consecutive >= 5:
                return
        else:
            consecutive = 0
        time.sleep(1)
    raise AgentIdentityInstallRejected("CPA has established connections")


def probe_health(value: Dict[str, Any], require_capability: bool) -> None:
    expected = value["capabilities"][0]
    for unused in range(40):
        connection = http.client.HTTPConnection(value["listenHost"], value["listenPort"], timeout=1)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            body = response.read(4097)
            capabilities = response.getheader(CAPABILITY_HEADER, "")
            if response.status == 200 and len(body) <= 4096 and (
                not require_capability or expected in [item.strip() for item in capabilities.split(",")]
            ):
                return
        except OSError:
            pass
        finally:
            connection.close()
        time.sleep(0.5)
    raise AgentIdentityInstallRejected("CPA health capability canary failed")


def launch_domain(value: Dict[str, Any]) -> Tuple[str, str]:
    domain = "gui/%d" % os.getuid()
    return domain, "%s/%s" % (domain, value["serviceLabel"])


def bootout(value: Dict[str, Any], allow_absent: bool = False) -> None:
    domain, service = launch_domain(value)
    completed = run_command(["launchctl", "bootout", service])
    if completed.returncode != 0 and not allow_absent:
        raise AgentIdentityInstallRejected("CPA launchd bootout failed")
    if completed.returncode != 0 and allow_absent:
        inspection = run_command(["launchctl", "print", service])
        if inspection.returncode == 0:
            raise AgentIdentityInstallRejected("CPA launchd bootout failed")


def bootstrap(value: Dict[str, Any]) -> None:
    domain, unused_service = launch_domain(value)
    completed = run_command(["launchctl", "bootstrap", domain, str(value["launcher"])])
    if completed.returncode != 0:
        raise AgentIdentityInstallRejected("CPA launchd bootstrap failed")


def capability_manifest(value: Dict[str, Any]) -> bytes:
    document = {
        "schema": CAPABILITY_SCHEMA,
        "binary": str(value["stagedBinary"]),
        "binarySha256": value["candidateSha256"],
        "runtimeVersion": value["version"],
        "capabilities": value["capabilities"],
    }
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")


def backup_state(value: Dict[str, Any], launcher: bytes) -> pathlib.Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = value["backupRoot"] / (timestamp + "-" + value["candidateSha256"][:8])
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup, 0o700)
    baseline_binary, baseline_binary_mode = safe_file(value["baselineBinary"])
    baseline_metadata, baseline_metadata_mode = safe_file(
        value["baselineMetadata"], 1024 * 1024
    )
    launcher_mode = stat.S_IMODE(os.stat(value["launcher"], follow_symlinks=False).st_mode)
    files = {
        "baseline-binary": baseline_binary,
        "baseline-metadata.json": baseline_metadata,
        "launcher.plist": launcher,
    }
    modes = {
        "baseline-binary": baseline_binary_mode,
        "baseline-metadata.json": baseline_metadata_mode,
        "launcher.plist": launcher_mode,
    }
    capability = value["capabilityManifest"]
    capability_present = capability.is_file() and not capability.is_symlink()
    if capability_present:
        capability_raw, capability_mode = safe_file(capability, 1024 * 1024)
        files["capability-manifest.json"] = capability_raw
        modes["capability-manifest.json"] = capability_mode
    for name, raw in files.items():
        atomic_write(backup / name, raw, 0o600)
    record = {
        "schema": "cloudx.cliproxy-agent-identity-backup.v1",
        "capabilityManifestPresent": capability_present,
        "files": {name: sha256_bytes(raw) for name, raw in files.items()},
        "modes": modes,
    }
    atomic_write(backup / "backup.json", (json.dumps(record, sort_keys=True, indent=2) + "\n").encode(), 0o600)
    return backup


def restore(
    value: Dict[str, Any],
    backup: pathlib.Path,
    *,
    restore_baseline: bool = True,
) -> None:
    record_raw = safe_bytes(backup / "backup.json", 1024 * 1024)
    try:
        record = json.loads(record_raw)
    except json.JSONDecodeError as exc:
        raise AgentIdentityInstallRejected("rollback record is invalid") from exc
    files = record.get("files")
    modes = record.get("modes")
    if (
        record.get("schema") != "cloudx.cliproxy-agent-identity-backup.v1"
        or not isinstance(files, dict)
        or not isinstance(modes, dict)
        or set(files) != set(modes)
    ):
        raise AgentIdentityInstallRejected("rollback record is invalid")
    restored: Dict[str, bytes] = {}
    for name, expected in files.items():
        raw = safe_bytes(backup / name)
        mode = modes.get(name)
        if (
            sha256_bytes(raw) != expected
            or not isinstance(mode, int)
            or isinstance(mode, bool)
            or mode < 0o600
            or mode > 0o755
        ):
            raise AgentIdentityInstallRejected("rollback file digest does not match")
        restored[name] = raw
    bootout(value, allow_absent=True)
    if restore_baseline:
        atomic_write(
            value["baselineBinary"],
            restored["baseline-binary"],
            modes["baseline-binary"],
        )
        atomic_write(
            value["baselineMetadata"],
            restored["baseline-metadata.json"],
            modes["baseline-metadata.json"],
        )
    atomic_write(value["launcher"], restored["launcher.plist"], modes["launcher.plist"])
    capability = value["capabilityManifest"]
    if record.get("capabilityManifestPresent"):
        atomic_write(
            capability,
            restored["capability-manifest.json"],
            modes["capability-manifest.json"],
        )
    elif capability.exists() and not capability.is_symlink():
        capability.unlink()
    bootstrap(value)
    probe_health(value, require_capability=False)


def activate(value: Dict[str, Any], home: pathlib.Path) -> Dict[str, Any]:
    require_active_cloudx(value, home)
    verify_candidate(value["stagedBinary"], value)
    if sha256_bytes(safe_bytes(value["baselineBinary"])) != value["baselineSha256"]:
        raise AgentIdentityInstallRejected("baseline CPA binary changed")
    if sha256_bytes(safe_bytes(value["baselineMetadata"], 1024 * 1024)) != value["baselineMetadataSha256"]:
        raise AgentIdentityInstallRejected("baseline CPA metadata changed")
    launcher, document = launcher_bytes(value)
    current_program = str(document["ProgramArguments"][0])
    if current_program not in {str(value["baselineBinary"]), str(value["stagedBinary"])}:
        raise AgentIdentityInstallRejected("CPA launcher selects an unknown binary")
    before_count, before_digest = auth_inventory(value["authDirectory"])
    zero_established_connections(value)
    backup = backup_state(value, launcher)
    try:
        if current_program != str(value["stagedBinary"]):
            bootout(value)
            atomic_write(value["launcher"], updated_launcher(document, value), 0o644)
            bootstrap(value)
        probe_health(value, require_capability=True)
        atomic_write(value["capabilityManifest"], capability_manifest(value), 0o600)
        after_count, after_digest = auth_inventory(value["authDirectory"])
        if (after_count, after_digest) != (before_count, before_digest):
            raise AgentIdentityInstallRejected("CPA auth inventory changed during activation")
    except Exception as exc:
        # Activation never mutates the baseline binary or its metadata. Automatic
        # rollback therefore restores only installer-owned state and never
        # overwrites an external CPA update that raced this transaction.
        restore(value, backup, restore_baseline=False)
        if isinstance(exc, AgentIdentityInstallRejected):
            raise
        raise AgentIdentityInstallRejected("CPA activation failed and was restored") from exc
    return {
        "schema": RESULT_SCHEMA,
        "status": "activated",
        "version": value["version"],
        "capabilityAttested": True,
        "authFilesPreserved": before_count,
        "externalCPARestarted": current_program != str(value["stagedBinary"]),
        "rollbackBackup": backup.name,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=pathlib.Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--candidate", type=pathlib.Path)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--restore", type=pathlib.Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.stage, args.activate, args.restore))
    if selected > 1:
        raise AgentIdentityInstallRejected("choose only one mutation")
    home = pathlib.Path(os.environ.get("CLOUDX_USER_HOME") or pathlib.Path.home()).expanduser().resolve()
    value = expanded_contract(load_contract(args.contract), home)
    if selected == 0:
        print(json.dumps(plan_document(value), sort_keys=True))
        return 0
    stage_confirmation, activation_confirmation = confirmations(value)
    if args.stage:
        if args.confirm != stage_confirmation or args.candidate is None:
            raise AgentIdentityInstallRejected("stage confirmation or candidate is missing")
        result = stage_candidate(args.candidate.expanduser(), value)
    elif args.activate:
        if args.confirm != activation_confirmation:
            raise AgentIdentityInstallRejected("activation confirmation does not match")
        result = activate(value, home)
    else:
        backup = args.restore.expanduser().resolve()
        expected = "RESTORE LOCAL CPA AGENT IDENTITY %s" % backup.name
        try:
            backup.relative_to(value["backupRoot"].resolve())
        except ValueError as exc:
            raise AgentIdentityInstallRejected("rollback path is outside the private root") from exc
        if args.confirm != expected:
            raise AgentIdentityInstallRejected("rollback confirmation does not match")
        restore(value, backup)
        result = {"schema": RESULT_SCHEMA, "status": "restored", "backup": backup.name}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AgentIdentityInstallRejected as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "status": "rejected", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(2)
