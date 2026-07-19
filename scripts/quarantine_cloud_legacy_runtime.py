#!/usr/bin/env python3
"""Quarantine the dormant cloud codexx_app runtime with root-only recovery."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

CONFIRMATION = "QUARANTINE DORMANT CLOUD CODEXX APP RUNTIME WITH AUTOMATIC RESTORE"
RECOVERY_CONFIRMATION = "RESTORE QUARANTINED CLOUD CODEXX APP RUNTIME"
TARGET = pathlib.Path("/opt/codex-gateway/codexx_app")
QUARANTINE_ROOT = pathlib.Path("/var/lib/cloudx/legacy-runtime-quarantine")
LOCK_PATH = pathlib.Path("/var/lib/cloudx/legacy-runtime-quarantine.lock")
ROLLBACK_SNAPSHOT = pathlib.Path(
    "/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z"
)
RELEASE_ROOT = pathlib.Path("/opt/cloudx/releases")
CURRENT_LINK = pathlib.Path("/opt/cloudx/current")
PREVIOUS_LINK = pathlib.Path("/opt/cloudx/previous")
CLOUDX_REMOTE = pathlib.Path("/usr/local/bin/cloudx-remote")
PROC_ROOT = pathlib.Path("/proc")
SYSTEMD_ROOTS = (
    pathlib.Path("/etc/systemd/system"),
    pathlib.Path("/usr/lib/systemd/system"),
)
CRON_ROOTS = (
    pathlib.Path("/etc/cron.d"),
    pathlib.Path("/etc/cron.daily"),
    pathlib.Path("/etc/cron.hourly"),
    pathlib.Path("/etc/cron.weekly"),
    pathlib.Path("/var/spool/cron"),
)
DEPENDENT_SOURCES = (
    pathlib.Path("/opt/codex-gateway/cloud_import_api.py"),
    pathlib.Path("/opt/codex-gateway/cloud_import_phi_repair.py"),
    pathlib.Path("/opt/codex-gateway/cloud_import_retry.py"),
    pathlib.Path("/opt/codex-gateway/deepseek_quota_monitor.py"),
    pathlib.Path("/opt/codex-gateway/import_api.py"),
)
DEPENDENT_UNITS = {
    "codex-import.service": ("inactive", "disabled", 0),
    "codex-import-phi-repair.service": ("inactive", "static", 0),
    "codex-import-phi-repair.timer": ("inactive", "disabled", 0),
    "pi-deepseek-quota-monitor.service": ("inactive", "static", 0),
    "pi-deepseek-quota-monitor.timer": ("inactive", "disabled", 0),
}
EXPECTED_REFERENCE_UNITS = {
    "codex-import.service",
    "codex-import-phi-repair.service",
    "pi-deepseek-quota-monitor.service",
}
CONTINUITY_UNITS = {
    "cloudx-legacy-health-bridge.timer": ("active", "enabled"),
    "cloudx-health-contract.timer": ("inactive", "disabled"),
    "phi-cloudx-health.timer": ("active", "enabled"),
}
GATEWAY_UNIT = "cliproxy.service"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
MAX_FILES = 2000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_FILES = 5000

@dataclass(frozen=True)
class TreeSnapshot:
    records: Tuple[Mapping[str, Any], ...]
    file_count: int
    total_bytes: int
    tree_sha256: str
    device: int
    inode: int

def _run(
    command: Sequence[str],
    *,
    timeout: float = 30.0,
    cwd: Optional[pathlib.Path] = None,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise RuntimeError("cloud legacy runtime command output exceeded the limit")
    return completed

def _safe_file(path: pathlib.Path, label: str, maximum: int) -> Tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("%s is unavailable or unsafe" % label) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise RuntimeError("%s is not one bounded regular file" % label)
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise RuntimeError("%s exceeds the size limit" % label)
        return raw, metadata
    finally:
        os.close(descriptor)

def _tree_snapshot(path: pathlib.Path) -> TreeSnapshot:
    try:
        root = path.lstat()
    except OSError as exc:
        raise RuntimeError("cloud legacy runtime is unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(root.st_mode):
        raise RuntimeError("cloud legacy runtime must be one real directory")
    if stat.S_IMODE(root.st_mode) & 0o022:
        raise RuntimeError("cloud legacy runtime root is writable by another identity")
    records: List[Mapping[str, Any]] = []
    file_count = 0
    total_bytes = 0
    pending = [path]
    while pending:
        current = pending.pop()
        for entry in sorted(os.scandir(current), key=lambda item: item.name):
            candidate = pathlib.Path(entry.path)
            metadata = candidate.lstat()
            relative = candidate.relative_to(path).as_posix()
            mode = stat.S_IMODE(metadata.st_mode)
            if candidate.is_symlink():
                raise RuntimeError("cloud legacy runtime contains a symlink")
            if mode & 0o022:
                raise RuntimeError("cloud legacy runtime contains a writable entry")
            common = {
                "relative": relative,
                "mode": mode,
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
            }
            if stat.S_ISDIR(metadata.st_mode):
                records.append({**common, "kind": "directory"})
                pending.append(candidate)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError("cloud legacy runtime contains a special file")
            raw, opened = _safe_file(candidate, "cloud legacy runtime file", MAX_FILE_BYTES)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                raise RuntimeError("cloud legacy runtime changed during inventory")
            file_count += 1
            total_bytes += len(raw)
            if file_count > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise RuntimeError("cloud legacy runtime exceeds the bounded inventory")
            records.append({
                **common,
                "kind": "file",
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
    if file_count == 0:
        raise RuntimeError("cloud legacy runtime is empty")
    ordered = tuple(sorted(records, key=lambda item: str(item["relative"])))
    digest = hashlib.sha256(
        json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TreeSnapshot(
        records=ordered,
        file_count=file_count,
        total_bytes=total_bytes,
        tree_sha256=digest,
        device=root.st_dev,
        inode=root.st_ino,
    )

def _inside(value: str, root: pathlib.Path) -> bool:
    clean = value.removesuffix(" (deleted)")
    prefix = str(root)
    return clean == prefix or clean.startswith(prefix + "/")

def _process_references() -> List[int]:
    references = []
    needles = [str(TARGET).encode("utf-8")]
    needles.extend(str(path).encode("utf-8") for path in DEPENDENT_SOURCES)
    for candidate in sorted(PROC_ROOT.glob("[0-9]*"), key=lambda item: item.name):
        try:
            pid = int(candidate.name)
        except ValueError:
            continue
        matched = False
        for name in ("exe", "cwd", "root"):
            try:
                if _inside(os.readlink(candidate / name), TARGET):
                    matched = True
                    break
            except OSError:
                pass
        for name, maximum in (("cmdline", 1024 * 1024), ("environ", 1024 * 1024), ("maps", 4 * 1024 * 1024)):
            if matched:
                break
            try:
                raw = (candidate / name).read_bytes()
            except OSError:
                continue
            if len(raw) > maximum:
                raise RuntimeError("cloud process reference evidence exceeded the limit")
            if any(needle in raw for needle in needles):
                matched = True
                break
        if not matched:
            try:
                descriptors = list((candidate / "fd").iterdir())
            except OSError:
                descriptors = []
            for descriptor in descriptors[:65536]:
                try:
                    if _inside(os.readlink(descriptor), TARGET):
                        matched = True
                        break
                except OSError:
                    pass
        if matched:
            references.append(pid)
    return references

def _dependency_sources() -> Mapping[str, str]:
    values = {}
    for path in DEPENDENT_SOURCES:
        raw, metadata = _safe_file(path, "legacy dependent source", MAX_FILE_BYTES)
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise RuntimeError("legacy dependent source ownership or mode is unsafe")
        if b"codexx_app" not in raw:
            raise RuntimeError("legacy dependent source no longer has the expected dependency")
        values[path.name] = hashlib.sha256(raw).hexdigest()
    return values

def _reference_units() -> List[str]:
    needles = [str(path).encode("utf-8") for path in DEPENDENT_SOURCES]
    needles.append(str(TARGET).encode("utf-8"))
    units = set()
    inspected = 0
    for root in SYSTEMD_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            inspected += 1
            if inspected > MAX_REFERENCE_FILES:
                raise RuntimeError("systemd reference inventory exceeded the limit")
            try:
                raw, unused = _safe_file(path, "systemd reference file", 1024 * 1024)
            except RuntimeError:
                continue
            if not any(needle in raw for needle in needles):
                continue
            if path.parent.name.endswith(".d"):
                units.add(path.parent.name[:-2])
            else:
                units.add(path.name)
    return sorted(units)

def _cron_references() -> int:
    needles = [str(path).encode("utf-8") for path in DEPENDENT_SOURCES]
    needles.append(str(TARGET).encode("utf-8"))
    matches = 0
    inspected = 0
    for root in CRON_ROOTS:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else list(root.rglob("*"))
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                continue
            inspected += 1
            if inspected > MAX_REFERENCE_FILES:
                raise RuntimeError("cron reference inventory exceeded the limit")
            try:
                raw, unused = _safe_file(path, "cron reference file", 1024 * 1024)
            except RuntimeError:
                continue
            if any(needle in raw for needle in needles):
                matches += 1
    return matches

def _unit_state(unit: str) -> Dict[str, Any]:
    completed = _run([
        "systemctl", "show", unit, "--no-pager",
        "-p", "LoadState", "-p", "ActiveState", "-p", "SubState",
        "-p", "UnitFileState", "-p", "MainPID", "-p", "NRestarts",
    ])
    if completed.returncode != 0:
        raise RuntimeError("cloud unit state is unavailable")
    values = {}
    for line in completed.stdout.decode("utf-8", errors="strict").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    required = {"LoadState", "ActiveState", "SubState", "UnitFileState"}
    if not required.issubset(values):
        raise RuntimeError("cloud unit state is incomplete")
    try:
        pid = int(values.get("MainPID", "0"))
        restarts = int(values.get("NRestarts", "0"))
    except ValueError as exc:
        raise RuntimeError("cloud unit state is invalid") from exc
    return {
        "loadState": values["LoadState"],
        "activeState": values["ActiveState"],
        "subState": values["SubState"],
        "unitFileState": values["UnitFileState"],
        "mainPid": pid,
        "restarts": restarts,
    }

def _dependency_units() -> Mapping[str, Mapping[str, Any]]:
    states = {unit: _unit_state(unit) for unit in DEPENDENT_UNITS}
    for unit, expected in DEPENDENT_UNITS.items():
        state = states[unit]
        if (
            state["loadState"] != "loaded"
            or state["activeState"] != expected[0]
            or state["unitFileState"] != expected[1]
            or state["mainPid"] != expected[2]
        ):
            raise RuntimeError("legacy dependency unit is not safely dormant")
    return states

def _selectors(release_version: str) -> Mapping[str, str]:
    values = {}
    for name, path in (("current", CURRENT_LINK), ("previous", PREVIOUS_LINK)):
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(RELEASE_ROOT)
        except (OSError, ValueError) as exc:
            raise RuntimeError("cloud release selector is unavailable or unsafe") from exc
        if not stat.S_ISLNK(metadata.st_mode) or len(relative.parts) != 1 or not VERSION_RE.fullmatch(relative.parts[0]):
            raise RuntimeError("cloud release selector is invalid")
        values[name] = relative.parts[0]
    if values["current"] != release_version:
        raise RuntimeError("the requested signed cloud release is not active")
    artifact = RELEASE_ROOT / release_version / "cloudx-cloud.pyz"
    completed = _run(["/usr/bin/python3", str(artifact), "self-check"])
    try:
        document = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("signed cloud self-check is invalid") from exc
    if (
        completed.returncode != 0
        or document.get("schema") != "cloudx.self-check.v1"
        or document.get("component") != "cloud"
        or document.get("version") != release_version
        or document.get("status") != "ok"
    ):
        raise RuntimeError("signed cloud self-check did not match")
    return values

def _public_canaries(release_version: str) -> Mapping[str, Any]:
    if CLOUDX_REMOTE.is_symlink() or not CLOUDX_REMOTE.is_file():
        raise RuntimeError("cloudx-remote canary entrypoint is unsafe")
    documents = {}
    for name, arguments in (
        ("health", ("health", "--json")),
        ("handshake", ("handshake", "--json")),
    ):
        completed = _run([str(CLOUDX_REMOTE), *arguments], timeout=60.0)
        try:
            document = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("cloud public canary returned invalid JSON") from exc
        if completed.returncode != 0 or not isinstance(document, dict):
            raise RuntimeError("cloud public canary failed")
        documents[name] = document
    health = documents["health"]
    handshake = documents["handshake"]
    if (
        health.get("schema") != "cloudx.health.v1"
        or health.get("cloudxVersion") != release_version
        or health.get("gatewayStatus") != "healthy"
        or health.get("importStatus") != "ready"
        or handshake.get("schema") != "cloudx.handshake.v1"
        or handshake.get("productVersion") != release_version
        or handshake.get("gateway", {}).get("status") != "healthy"
    ):
        raise RuntimeError("cloud public canaries were not accepted")
    return {
        "healthSchema": health["schema"],
        "gatewayStatus": health["gatewayStatus"],
        "importStatus": health["importStatus"],
        "handshakeSchema": handshake["schema"],
        "gatewayVersion": handshake["gateway"]["version"],
    }

def _rollback_snapshot(snapshot: TreeSnapshot) -> Mapping[str, Any]:
    metadata = ROLLBACK_SNAPSHOT.lstat()
    if (
        ROLLBACK_SNAPSHOT.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("HTTP importer rollback snapshot is unsafe")
    completed = _run(
        ["/usr/bin/sha256sum", "-c", "SHA256SUMS"],
        timeout=90.0,
        cwd=ROLLBACK_SNAPSHOT,
    )
    if completed.returncode != 0:
        raise RuntimeError("HTTP importer rollback snapshot digest verification failed")
    archive = ROLLBACK_SNAPSHOT / "importer-runtime.tar.gz"
    raw, archive_metadata = _safe_file(archive, "HTTP importer runtime archive", MAX_TOTAL_BYTES)
    if archive_metadata.st_uid != 0 or stat.S_IMODE(archive_metadata.st_mode) & 0o077:
        raise RuntimeError("HTTP importer runtime archive permissions are too broad")
    listed = _run(["/usr/bin/tar", "-tzf", str(archive)], timeout=90.0)
    if listed.returncode != 0:
        raise RuntimeError("HTTP importer runtime archive is unreadable")
    names = listed.stdout.decode("utf-8", errors="strict").splitlines()
    if any(name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts for name in names):
        raise RuntimeError("HTTP importer runtime archive contains an unsafe member")
    target_entries = sum(1 for name in names if "codexx_app/" in name)
    if target_entries < snapshot.file_count:
        raise RuntimeError("HTTP importer rollback archive lacks the legacy runtime")
    return {
        "archiveSha256": hashlib.sha256(raw).hexdigest(),
        "targetEntries": target_entries,
    }

def _continuity(release_version: str, snapshot: TreeSnapshot) -> Mapping[str, Any]:
    gateway = _unit_state(GATEWAY_UNIT)
    if gateway["activeState"] != "active" or gateway["mainPid"] <= 0:
        raise RuntimeError("cloud gateway is not active")
    continuity_units = {unit: _unit_state(unit) for unit in CONTINUITY_UNITS}
    for unit, expected in CONTINUITY_UNITS.items():
        state = continuity_units[unit]
        if state["activeState"] != expected[0] or state["unitFileState"] != expected[1]:
            raise RuntimeError("cloud compatibility consumer state changed")
    return {
        "gateway": gateway,
        "selectors": _selectors(release_version),
        "dependencyUnits": _dependency_units(),
        "continuityUnits": continuity_units,
        "publicCanaries": _public_canaries(release_version),
        "rollback": _rollback_snapshot(snapshot),
    }

def _contract(release_version: str) -> Tuple[Mapping[str, Any], TreeSnapshot]:
    if os.geteuid() != 0:
        raise RuntimeError("cloud legacy runtime inspection requires root")
    snapshot = _tree_snapshot(TARGET)
    processes = _process_references()
    if processes:
        raise RuntimeError("cloud legacy runtime still has a live process reference")
    dependencies = _dependency_sources()
    units = _reference_units()
    if set(units) != EXPECTED_REFERENCE_UNITS:
        raise RuntimeError("cloud legacy runtime unit references changed")
    cron = _cron_references()
    if cron:
        raise RuntimeError("cloud legacy runtime still has a scheduled reference")
    continuity = _continuity(release_version, snapshot)
    return {
        "releaseVersion": release_version,
        "targetDevice": snapshot.device,
        "targetInode": snapshot.inode,
        "targetFileCount": snapshot.file_count,
        "targetBytes": snapshot.total_bytes,
        "targetTreeSha256": snapshot.tree_sha256,
        "processReferences": processes,
        "dependencySources": dependencies,
        "referenceUnits": units,
        "cronReferences": cron,
        "continuity": continuity,
    }, snapshot

def _digest(contract: Mapping[str, Any]) -> str:
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def decision(release_version: str) -> Mapping[str, Any]:
    contract, unused_snapshot = _contract(release_version)
    continuity = contract["continuity"]
    return {
        "schema": "cloudx.cloud-legacy-runtime-quarantine-decision.v1",
        "status": "quarantine-ready",
        "decisionDigest": _digest(contract),
        "releaseVersion": release_version,
        "targetFileCount": contract["targetFileCount"],
        "targetBytes": contract["targetBytes"],
        "targetTreeSha256": contract["targetTreeSha256"],
        "liveProcessReferences": 0,
        "dependencySourceCount": len(contract["dependencySources"]),
        "referenceUnitCount": len(contract["referenceUnits"]),
        "scheduledReferences": 0,
        "rollbackSnapshotVerified": True,
        "rollbackArchiveContainsTarget": True,
        "gatewayPid": continuity["gateway"]["mainPid"],
        "gatewayRestarts": continuity["gateway"]["restarts"],
        "currentVersion": continuity["selectors"]["current"],
        "previousVersion": continuity["selectors"]["previous"],
        "serviceRestartRequired": False,
        "contract": contract,
    }

def _private_directory(path: pathlib.Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("cloud legacy runtime quarantine directory is unsafe")

@contextmanager
def _lock() -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(LOCK_PATH, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_gid != os.getegid()
        ):
            raise RuntimeError("cloud legacy runtime quarantine lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)

def _atomic_file(path: pathlib.Path, raw: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)

def _recover_script() -> bytes:
    source = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib, stat
CONFIRMATION="RESTORE QUARANTINED CLOUD CODEXX APP RUNTIME"
ROOT=pathlib.Path(__file__).resolve().parent
def tree(path):
    records=[]; files=0; total=0; pending=[path]
    while pending:
        current=pending.pop()
        for entry in sorted(os.scandir(current),key=lambda item:item.name):
            candidate=pathlib.Path(entry.path); metadata=candidate.lstat(); relative=candidate.relative_to(path).as_posix(); mode=stat.S_IMODE(metadata.st_mode)
            if candidate.is_symlink() or mode & 0o022: raise SystemExit("quarantined runtime is unsafe")
            common={"relative":relative,"mode":mode,"uid":metadata.st_uid,"gid":metadata.st_gid}
            if stat.S_ISDIR(metadata.st_mode): records.append({**common,"kind":"directory"}); pending.append(candidate); continue
            if not stat.S_ISREG(metadata.st_mode): raise SystemExit("quarantined runtime contains a special file")
            raw=candidate.read_bytes(); files+=1; total+=len(raw); records.append({**common,"kind":"file","size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
    ordered=tuple(sorted(records,key=lambda item:str(item["relative"])))
    digest=hashlib.sha256(json.dumps(ordered,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return files,total,digest
def state():
    manifest=json.loads((ROOT/"manifest.json").read_text()); live=pathlib.Path(manifest["liveTarget"]); held=ROOT/"live/codexx_app"
    if os.path.lexists(live): raise SystemExit("live cloud legacy runtime already exists")
    if held.is_symlink() or not held.is_dir(): raise SystemExit("quarantined cloud legacy runtime is unavailable")
    if live.parent.stat().st_dev != held.stat().st_dev: raise SystemExit("cloud legacy restore is not on one filesystem")
    observed=tree(held)
    if observed != (manifest["fileCount"],manifest["totalBytes"],manifest["treeSha256"]): raise SystemExit("quarantined cloud legacy runtime digest changed")
    return manifest,live,held
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); parser.add_argument("--confirm",default=""); args=parser.parse_args(); manifest,live,held=state()
    if args.check: print(json.dumps({"status":"ready","backupId":manifest["backupId"],"fileCount":manifest["fileCount"]},sort_keys=True)); return
    if args.confirm!=CONFIRMATION: raise SystemExit("cloud legacy runtime recovery confirmation does not match")
    os.replace(held,live)
    for parent in (held.parent,live.parent):
        descriptor=os.open(parent,os.O_RDONLY); os.fsync(descriptor); os.close(descriptor)
    print(json.dumps({"status":"restored","backupId":manifest["backupId"],"serviceRestarted":False},sort_keys=True))
if __name__=="__main__": main()
'''
    return source.encode("utf-8")

def _prepare_backup(contract: Mapping[str, Any], snapshot: TreeSnapshot) -> pathlib.Path:
    _private_directory(QUARANTINE_ROOT)
    backup_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise RuntimeError("cloud legacy runtime backup identity is invalid")
    root = QUARANTINE_ROOT / backup_id
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    (root / "live").mkdir(mode=0o700)
    manifest = {
        "schema": "cloudx.cloud-legacy-runtime-quarantine-backup.v1",
        "backupId": backup_id,
        "liveTarget": str(TARGET),
        "fileCount": snapshot.file_count,
        "totalBytes": snapshot.total_bytes,
        "treeSha256": snapshot.tree_sha256,
        "decisionDigest": _digest(contract),
        "rollbackSnapshotRetained": str(ROLLBACK_SNAPSHOT),
        "recoveryConfirmation": RECOVERY_CONFIRMATION,
    }
    _atomic_file(
        root / "manifest.json",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        0o600,
    )
    _atomic_file(root / "recover.py", _recover_script(), 0o700)
    manual = (
        "# Restore quarantined cloud codexx_app runtime\n\n"
        "This restores code only. It does not start, enable, stop, disable, or restart any "
        "service and does not change a credential, release selector, gateway, CPA, or Phi.\n\n"
        "    ./recover.py --check\n"
        "    ./recover.py --confirm \"%s\"\n"
    ) % RECOVERY_CONFIRMATION
    _atomic_file(root / "RECOVERY.md", manual.encode("utf-8"), 0o600)
    return root

def plan(release_version: str) -> Mapping[str, Any]:
    return {
        "schema": "cloudx.cloud-legacy-runtime-quarantine-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "target": str(TARGET),
        "automaticAction": False,
        "preconditions": [
            "exact_signed_cloud_release_active",
            "bounded_non_writable_runtime_inventory",
            "zero_live_process_references",
            "only_declared_dormant_unit_references",
            "zero_scheduled_references",
            "http_importer_rollback_archive_verified",
            "manual_recovery_prepared_before_move",
            "decision_digest_match",
            "gateway_and_compatibility_continuity",
        ],
        "authorization": {
            "runtimeQuarantine": False,
            "runtimeDeletion": False,
            "serviceStart": False,
            "serviceStop": False,
            "serviceRestart": False,
            "serviceEnable": False,
            "serviceDisable": False,
            "daemonReload": False,
            "gatewayMutation": False,
            "credentialMutation": False,
            "releaseMutation": False,
            "phiMutation": False,
            "rollbackRemoval": False,
        },
    }

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    mode = root.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--decision-digest", default="")
    root.add_argument("--release-version", required=True)
    return root

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if not args.check and not args.apply:
        print(json.dumps(plan(args.release_version), sort_keys=True, separators=(",", ":")))
        return 0
    if args.apply and args.confirm != CONFIRMATION:
        raise RuntimeError("cloud legacy runtime quarantine confirmation does not match")
    if args.apply and not DIGEST_RE.fullmatch(args.decision_digest):
        raise RuntimeError("cloud legacy runtime quarantine decision digest is invalid")
    current = dict(decision(args.release_version))
    if args.check:
        current.pop("contract", None)
        print(json.dumps(current, sort_keys=True, separators=(",", ":")))
        return 0
    if current["decisionDigest"] != args.decision_digest:
        raise RuntimeError("cloud legacy runtime quarantine decision changed before apply")
    with _lock():
        contract, snapshot = _contract(args.release_version)
        if _digest(contract) != args.decision_digest:
            raise RuntimeError("cloud legacy runtime quarantine identity changed before move")
        continuity_before = contract["continuity"]
        backup = _prepare_backup(contract, snapshot)
        held = backup / "live/codexx_app"
        moved = False
        try:
            if TARGET.lstat().st_dev != held.parent.lstat().st_dev:
                raise RuntimeError("cloud legacy runtime quarantine is not on one filesystem")
            os.replace(TARGET, held)
            moved = True
            if os.path.lexists(TARGET) or not held.is_dir() or held.is_symlink():
                raise RuntimeError("cloud legacy runtime did not enter quarantine")
            after_snapshot = _tree_snapshot(held)
            if (
                after_snapshot.file_count != snapshot.file_count
                or after_snapshot.total_bytes != snapshot.total_bytes
                or after_snapshot.tree_sha256 != snapshot.tree_sha256
            ):
                raise RuntimeError("cloud legacy runtime changed during quarantine")
            if _process_references():
                raise RuntimeError("cloud legacy runtime process reference appeared after move")
            if _continuity(args.release_version, after_snapshot) != continuity_before:
                raise RuntimeError("cloud gateway or compatibility continuity changed")
        except Exception as exc:
            recovery_errors = []
            if moved and not os.path.lexists(TARGET) and held.exists():
                try:
                    os.replace(held, TARGET)
                except OSError:
                    recovery_errors.append("legacy runtime restore failed")
            try:
                if _tree_snapshot(TARGET).tree_sha256 != snapshot.tree_sha256:
                    recovery_errors.append("legacy runtime digest changed after recovery")
                if _continuity(args.release_version, snapshot) != continuity_before:
                    recovery_errors.append("cloud continuity changed after recovery")
            except Exception:
                recovery_errors.append("cloud recovery audit failed")
            if not recovery_errors:
                shutil.rmtree(backup)
                raise RuntimeError("cloud legacy runtime quarantine failed and was restored") from exc
            raise RuntimeError(
                "cloud legacy runtime quarantine failed; recovery incomplete: %s"
                % "; ".join(recovery_errors)
            ) from exc
    print(json.dumps({
        "schema": "cloudx.cloud-legacy-runtime-quarantine.v1",
        "status": "quarantined",
        "releaseVersion": args.release_version,
        "decisionDigest": args.decision_digest,
        "backupId": backup.name,
        "targetFileCount": snapshot.file_count,
        "targetBytes": snapshot.total_bytes,
        "targetTreeSha256": snapshot.tree_sha256,
        "dependencySourceCount": len(contract["dependencySources"]),
        "referenceUnitCount": len(contract["referenceUnits"]),
        "liveProcessReferences": 0,
        "scheduledReferences": 0,
        "recoveryScriptPrepared": True,
        "httpImporterRollbackSnapshotRetained": True,
        "gatewayPid": continuity_before["gateway"]["mainPid"],
        "gatewayProcessUnchanged": True,
        "selectorsUnchanged": True,
        "runtimeLive": False,
        "runtimeDeleted": False,
        "serviceRestarted": False,
        "daemonReloaded": False,
        "credentialMutation": False,
        "phiServiceRestarted": False,
        "releaseActivated": False,
        "quarantineRetained": True,
    }, sort_keys=True, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("quarantine_cloud_legacy_runtime.py: %s" % exc, file=os.sys.stderr)
        raise SystemExit(1)
