#!/usr/bin/env python3
"""Unload and quarantine the independently idle legacy local control LaunchAgent."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import json
import os
import pathlib
import plistlib
import re
import stat
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple

import migrate_legacy_local_control as migration


CONFIRMATION = "RETIRE IDLE LOCAL CODEXX CONTROL LAUNCHAGENT WITH AUTOMATIC RESTORE"
RECOVERY_CONFIRMATION = "RESTORE RETIRED LOCAL CODEXX CONTROL LAUNCHAGENT"
BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_BACKUPS = 64


def user_home() -> pathlib.Path:
    return pathlib.Path.home().resolve()


def _safe_file(path: pathlib.Path, label: str, maximum: int) -> Tuple[bytes, os.stat_result]:
    return migration.legacy_removal._safe_file(path, label, maximum)


def _retained_bundle(home: pathlib.Path, plist: Mapping[str, Any], command: Sequence[str]) -> Tuple[pathlib.Path, pathlib.Path]:
    arguments = plist["ProgramArguments"]
    launcher = pathlib.Path(arguments[0])
    backup_root = home / ".local/state/cloudx/legacy-backups"
    try:
        root_metadata = backup_root.lstat()
        resolved_root = backup_root.resolve(strict=True)
        resolved_launcher = launcher.resolve(strict=True)
        relative = resolved_launcher.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise RuntimeError("retained control runtime is unavailable or unsafe") from exc
    if backup_root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("retained control backup root is unsafe")
    if root_metadata.st_uid != os.geteuid() or stat.S_IMODE(root_metadata.st_mode) & 0o022:
        raise RuntimeError("retained control backup root permissions are unsafe")
    if (
        len(relative.parts) != 5
        or not BACKUP_ID_RE.fullmatch(relative.parts[0])
        or relative.parts[1:] != ("home", ".local", "bin", "codexx")
    ):
        raise RuntimeError("retained control launcher has an unexpected shape")
    bundle = resolved_root / relative.parts[0]
    bundle_metadata = bundle.lstat()
    if bundle.is_symlink() or stat.S_IMODE(bundle_metadata.st_mode) != 0o700:
        raise RuntimeError("retained control bundle is unsafe")
    python_launcher = bundle / "home/.local/bin/codexx.py"
    for path, label in ((resolved_launcher, "retained control launcher"), (python_launcher, "retained control Python launcher")):
        raw, metadata = _safe_file(path, label, migration.legacy_removal.MAX_FILE_BYTES)
        del raw
        if not stat.S_IMODE(metadata.st_mode) & stat.S_IXUSR:
            raise RuntimeError("retained control launcher is not executable")
    if not migration._control_command(command, python_launcher):
        raise RuntimeError("control process is not using the retained runtime")
    return bundle, python_launcher


def _migration_backup(home: pathlib.Path, plist_sha256: str) -> pathlib.Path:
    root = home / ".local/state/cloudx/legacy-control-migration-backups"
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise RuntimeError("legacy control migration backup root is unavailable") from exc
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("legacy control migration backup root is unsafe")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("legacy control migration backup root permissions are unsafe")
    matches = []
    candidates = sorted(root.iterdir(), key=lambda path: path.name, reverse=True)
    if len(candidates) > MAX_BACKUPS:
        raise RuntimeError("legacy control migration backup count exceeds the limit")
    for candidate in candidates:
        if not BACKUP_ID_RE.fullmatch(candidate.name) or candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            raw, manifest_metadata = _safe_file(
                candidate / "manifest.json",
                "legacy control migration manifest",
                MAX_MANIFEST_BYTES,
            )
            document = json.loads(raw)
        except (RuntimeError, json.JSONDecodeError):
            continue
        if stat.S_IMODE(manifest_metadata.st_mode) & 0o077:
            continue
        expected = document.get("files", {}).get("target.plist")
        target_raw, unused = _safe_file(candidate / "target.plist", "legacy target plist", migration.MAX_PLIST_BYTES)
        recovery_raw, unused = _safe_file(candidate / "recover.py", "legacy control recovery", migration.MAX_PLIST_BYTES)
        if (
            document.get("schema") == "cloudx.legacy-local-control-migration-backup.v1"
            and expected == hashlib.sha256(target_raw).hexdigest()
            and hashlib.sha256(target_raw).hexdigest() == plist_sha256
            and document.get("files", {}).get("recover.py") == hashlib.sha256(recovery_raw).hexdigest()
        ):
            try:
                compile(recovery_raw.decode("utf-8"), str(candidate / "recover.py"), "exec")
            except (UnicodeDecodeError, SyntaxError):
                continue
            matches.append(candidate)
    if len(matches) != 1:
        raise RuntimeError("exact legacy control migration backup is ambiguous")
    return matches[0]


def _continuity(home: pathlib.Path, release_version: str) -> Mapping[str, Any]:
    return migration._continuity(home, release_version)


def _contract(release_version: str, home: Optional[pathlib.Path] = None) -> Mapping[str, Any]:
    selected_home = home or user_home()
    plist_raw, plist = migration._plist(selected_home)
    service = migration._service()
    command = migration._process_command(service["pid"])
    bundle, unused_python_launcher = _retained_bundle(selected_home, plist, command)
    migration._idle_listener(service["pid"])
    if migration._http_canary() != 401:
        raise RuntimeError("legacy control authentication canary changed")
    idle_seconds = migration._idle_state(selected_home)
    plist_sha256 = hashlib.sha256(plist_raw).hexdigest()
    migration_backup = _migration_backup(selected_home, plist_sha256)
    continuity = _continuity(selected_home, release_version)
    return {
        "releaseVersion": release_version,
        "plistSha256": plist_sha256,
        "servicePid": service["pid"],
        "retainedBundleId": bundle.name,
        "migrationBackupId": migration_backup.name,
        "minimumIdleSeconds": idle_seconds,
        "selectors": continuity["selectors"],
        "localCpaPid": continuity["cpa"]["pid"],
    }


def _digest(contract: Mapping[str, Any]) -> str:
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def decision(release_version: str) -> Mapping[str, Any]:
    contract = _contract(release_version)
    return {
        "schema": "cloudx.legacy-local-control-retirement-decision.v1",
        "status": "retirement-ready",
        "decisionDigest": _digest(contract),
        "releaseVersion": release_version,
        "controlPid": contract["servicePid"],
        "port": migration.PORT,
        "activeConnections": 0,
        "minimumIdleSeconds": contract["minimumIdleSeconds"],
        "retainedBundleId": contract["retainedBundleId"],
        "migrationBackupId": contract["migrationBackupId"],
        "localCpaPid": contract["localCpaPid"],
        "localCpaChanged": False,
        "serviceStopRequired": True,
        "contract": contract,
    }


@contextmanager
def _lock(home: pathlib.Path) -> Iterator[None]:
    state = home / ".local/state/cloudx"
    path = state / "legacy-control-retirement.lock"
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise RuntimeError("legacy control retirement lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _recover_script() -> bytes:
    source = r'''#!/usr/bin/env python3
import argparse, hashlib, http.client, json, os, pathlib, plistlib, socket, subprocess, tempfile, time
CONFIRMATION="RESTORE RETIRED LOCAL CODEXX CONTROL LAUNCHAGENT"
ROOT=pathlib.Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def run(argv): return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
def port_open():
    s=socket.socket(); s.settimeout(.25)
    try: return s.connect_ex(("127.0.0.1",8765))==0
    finally: s.close()
def canary():
    c=http.client.HTTPConnection("127.0.0.1",8765,timeout=3)
    try: c.request("GET","/api/status"); r=c.getresponse(); r.read(4096); return r.status
    finally: c.close()
def atomic(path,raw):
    fd,name=tempfile.mkstemp(prefix=".control.",dir=str(path.parent)); os.fchmod(fd,0o644)
    with os.fdopen(fd,"wb") as h: h.write(raw); h.flush(); os.fsync(h.fileno())
    os.replace(name,path)
def state():
    manifest=json.loads((ROOT/"manifest.json").read_text()); held=ROOT/"live/com.codexx.control.plist"; live=pathlib.Path(manifest["livePlist"])
    if os.path.lexists(live): raise SystemExit("live legacy control LaunchAgent already exists")
    if held.is_symlink() or not held.is_file() or sha(held)!=manifest["plistSha256"]: raise SystemExit("retired legacy control plist is unavailable")
    plist=plistlib.loads(held.read_bytes()); executable=pathlib.Path(plist["ProgramArguments"][0])
    if not executable.is_file(): raise SystemExit("retained control runtime is unavailable")
    return manifest,held,live
def main():
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--confirm",default=""); a=p.parse_args(); manifest,held,live=state()
    if a.check: print(json.dumps({"status":"ready","backupId":manifest["backupId"],"portOpen":port_open()},sort_keys=True)); return
    if a.confirm!=CONFIRMATION: raise SystemExit("legacy control retirement recovery confirmation does not match")
    atomic(live,held.read_bytes()); domain=f"gui/{os.getuid()}"; result=run(["launchctl","bootstrap",domain,str(live)])
    if result.returncode: live.unlink(missing_ok=True); raise SystemExit("legacy control bootstrap failed")
    deadline=time.monotonic()+20
    while not port_open() and time.monotonic()<deadline: time.sleep(.2)
    if not port_open() or canary()!=401:
        run(["launchctl","bootout",f"{domain}/com.codexx.control"]); deadline=time.monotonic()+10
        while port_open() and time.monotonic()<deadline: time.sleep(.2)
        if not port_open(): os.replace(live,held)
        raise SystemExit("restored legacy control listener is unavailable")
    held.unlink(); print(json.dumps({"status":"restored","backupId":manifest["backupId"],"serviceStarted":True},sort_keys=True))
if __name__=="__main__": main()
'''
    return source.encode("utf-8")


def _prepare_backup(home: pathlib.Path, plist_raw: bytes, contract: Mapping[str, Any]) -> pathlib.Path:
    parent = home / ".local/state/cloudx/legacy-control-retirement-backups"
    parent.mkdir(mode=0o700, exist_ok=True)
    parent.chmod(0o700)
    metadata = parent.lstat()
    if parent.is_symlink() or metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise RuntimeError("legacy control retirement backup root is unsafe")
    backup_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise RuntimeError("legacy control retirement backup identity is invalid")
    root = parent / backup_id
    root.mkdir(mode=0o700)
    (root / "live").mkdir(mode=0o700)
    recovery = _recover_script()
    migration._atomic_bytes(root / "recover.py", recovery, 0o700)
    manifest = {
        "schema": "cloudx.legacy-local-control-retirement-backup.v1",
        "backupId": backup_id,
        "livePlist": str(migration._plist_path(home)),
        "plistSha256": hashlib.sha256(plist_raw).hexdigest(),
        "decisionDigest": _digest(contract),
        "retainedBundleId": contract["retainedBundleId"],
        "migrationBackupId": contract["migrationBackupId"],
        "recoverySha256": hashlib.sha256(recovery).hexdigest(),
        "recoveryConfirmation": RECOVERY_CONFIRMATION,
    }
    migration._atomic_bytes(
        root / "manifest.json",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        0o600,
    )
    manual = (
        "# Restore retired legacy local control LaunchAgent\n\n"
        "This restores and starts only com.codexx.control from the retained runtime. "
        "It does not stop, restart, or reconfigure local CPA.\n\n"
        "    ./recover.py --check\n"
        "    ./recover.py --confirm \"%s\"\n"
    ) % RECOVERY_CONFIRMATION
    migration._atomic_bytes(root / "RECOVERY.md", manual.encode("utf-8"), 0o600)
    return root


def _service_absent() -> bool:
    completed = migration._run([
        "launchctl", "print", "%s/%s" % (migration._launch_domain(), migration.LABEL)
    ])
    return completed.returncode != 0


def plan(release_version: str) -> Mapping[str, Any]:
    return {
        "schema": "cloudx.legacy-local-control-retirement-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "automaticAction": False,
        "preconditions": [
            "retained_control_runtime_active",
            "zero_active_control_connections",
            "minimum_thirty_day_state_idle_window",
            "exact_migration_backup_verified",
            "retirement_recovery_prepared_before_stop",
            "decision_digest_match",
            "external_local_cpa_healthy",
        ],
        "authorization": {
            "controlServiceStop": False,
            "launchAgentQuarantine": False,
            "controlServiceStart": False,
            "localCpaMutation": False,
            "codexProcessTermination": False,
            "accountMutation": False,
            "cloudxMutation": False,
            "recoveryRemoval": False,
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
    if not migration.legacy_removal.VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if not args.check and not args.apply:
        print(json.dumps(plan(args.release_version), sort_keys=True, separators=(",", ":")))
        return 0
    if args.apply and args.confirm != CONFIRMATION:
        raise RuntimeError("legacy control retirement confirmation does not match")
    if args.apply and not DIGEST_RE.fullmatch(args.decision_digest):
        raise RuntimeError("legacy control retirement decision digest is invalid")
    current = dict(decision(args.release_version))
    if args.check:
        current.pop("contract", None)
        print(json.dumps(current, sort_keys=True, separators=(",", ":")))
        return 0
    if current["decisionDigest"] != args.decision_digest:
        raise RuntimeError("legacy control retirement decision changed before apply")
    home = user_home()
    with _lock(home):
        contract = _contract(args.release_version, home)
        if _digest(contract) != args.decision_digest:
            raise RuntimeError("legacy control retirement identity changed before stop")
        plist_raw, plist = migration._plist(home)
        command = migration._process_command(contract["servicePid"])
        bundle, python_launcher = _retained_bundle(home, plist, command)
        del bundle
        continuity_before = _continuity(home, args.release_version)
        backup = _prepare_backup(home, plist_raw, contract)
        live_plist = migration._plist_path(home)
        held_plist = backup / "live/com.codexx.control.plist"
        stopped = False
        moved = False
        try:
            migration._bootout()
            stopped = True
            if live_plist.lstat().st_dev != held_plist.parent.lstat().st_dev:
                raise RuntimeError("legacy control retirement is not on one filesystem")
            os.replace(live_plist, held_plist)
            moved = True
            if not _service_absent() or migration.legacy_removal._port_open(migration.PORT):
                raise RuntimeError("legacy control service remained after retirement")
            if _continuity(home, args.release_version) != continuity_before:
                raise RuntimeError("local Cloudx or CPA continuity changed during control retirement")
        except Exception as exc:
            recovery_errors = []
            try:
                if moved and not os.path.lexists(live_plist) and held_plist.exists():
                    os.replace(held_plist, live_plist)
                if stopped and not migration.legacy_removal._port_open(migration.PORT):
                    migration._bootstrap(plist_raw, python_launcher)
                if _continuity(home, args.release_version) != continuity_before:
                    recovery_errors.append("local continuity changed after control recovery")
            except Exception:
                recovery_errors.append("legacy control recovery failed")
            if recovery_errors:
                raise RuntimeError(
                    "legacy control retirement failed; recovery incomplete: %s"
                    % "; ".join(recovery_errors)
                ) from exc
            raise RuntimeError("legacy control retirement failed and was restored") from exc
    print(json.dumps({
        "schema": "cloudx.legacy-local-control-retirement.v1",
        "status": "retired",
        "decisionDigest": args.decision_digest,
        "releaseVersion": args.release_version,
        "previousPid": contract["servicePid"],
        "port": migration.PORT,
        "portClosed": True,
        "launchAgentLoaded": False,
        "launchAgentLive": False,
        "backupId": backup.name,
        "retainedBundleId": contract["retainedBundleId"],
        "migrationBackupId": contract["migrationBackupId"],
        "recoveryScriptPrepared": True,
        "controlServiceStopped": True,
        "controlServiceRestarted": False,
        "sigkillSent": False,
        "localCpaPid": continuity_before["cpa"]["pid"],
        "localCpaChanged": False,
        "codexProcessTerminated": False,
        "accountMutation": False,
        "cloudxSelectorsUnchanged": True,
        "quarantineRetained": True,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("retire_legacy_local_control.py: %s" % exc, file=os.sys.stderr)
        raise SystemExit(1)
