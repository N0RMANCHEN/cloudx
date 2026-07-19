#!/usr/bin/env python3
"""Move the idle legacy control service onto the retained private recovery runtime."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import http.client
import json
import os
import pathlib
import plistlib
import re
import shlex
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import remove_legacy_local_package as legacy_removal


CONFIRMATION = "MIGRATE IDLE LOCAL CODEXX CONTROL TO RETAINED RECOVERY RUNTIME"
RECOVERY_CONFIRMATION = "RECOVER LOCAL CODEXX CONTROL FROM RETAINED BACKUP"
LABEL = "com.codexx.control"
PORT = 8765
MIN_IDLE_SECONDS = 30 * 24 * 60 * 60
CONNECTION_SAMPLES = 5
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
MAX_PLIST_BYTES = 1024 * 1024


def user_home() -> pathlib.Path:
    return pathlib.Path.home().resolve()


def _run(command: Sequence[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_bytes(path: pathlib.Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


@contextmanager
def _lock(home: pathlib.Path) -> Iterator[None]:
    state = home / ".local/state/cloudx"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = state.lstat()
    if state.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("Cloudx local state directory is unsafe")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("Cloudx local state directory permissions are too broad")
    path = state / "legacy-control-migration.lock"
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _plist_path(home: pathlib.Path) -> pathlib.Path:
    return home / "Library/LaunchAgents/com.codexx.control.plist"


def _plist(home: pathlib.Path) -> Tuple[bytes, Dict[str, Any]]:
    raw, metadata = legacy_removal._safe_file(
        _plist_path(home),
        "legacy control LaunchAgent",
        MAX_PLIST_BYTES,
    )
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RuntimeError("legacy control LaunchAgent ownership or mode is unsafe")
    try:
        document = plistlib.loads(raw)
    except Exception as exc:
        raise RuntimeError("legacy control LaunchAgent is invalid") from exc
    if not isinstance(document, dict) or document.get("Label") != LABEL:
        raise RuntimeError("legacy control LaunchAgent label is invalid")
    arguments = document.get("ProgramArguments")
    if not isinstance(arguments, list) or any(not isinstance(item, str) for item in arguments):
        raise RuntimeError("legacy control LaunchAgent arguments are invalid")
    if arguments[1:] != ["control", "serve", "--host", "127.0.0.1", "--port", str(PORT)]:
        raise RuntimeError("legacy control LaunchAgent command contract changed")
    if document.get("KeepAlive") is not True or document.get("RunAtLoad") is not True:
        raise RuntimeError("legacy control LaunchAgent lifecycle contract changed")
    return raw, document


def _launch_domain() -> str:
    return "gui/%d" % os.getuid()


def _service() -> Dict[str, Any]:
    completed = _run(["launchctl", "print", "%s/%s" % (_launch_domain(), LABEL)])
    if completed.returncode != 0:
        raise RuntimeError("legacy control LaunchAgent is not loaded")
    state = re.search(r"^\s*state = (\S+)\s*$", completed.stdout, re.MULTILINE)
    pid = re.search(r"^\s*pid = ([0-9]+)\s*$", completed.stdout, re.MULTILINE)
    program = re.search(r"^\s*program = (.+?)\s*$", completed.stdout, re.MULTILINE)
    if not state or state.group(1) != "running" or not pid or not program:
        raise RuntimeError("legacy control LaunchAgent is not running")
    return {"pid": int(pid.group(1)), "program": program.group(1)}


def _process_command(pid: int) -> List[str]:
    completed = _run(["ps", "-ww", "-p", str(pid), "-o", "command="])
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError("legacy control process command is unavailable")
    try:
        return shlex.split(completed.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("legacy control process command is invalid") from exc


def _control_command(tokens: Sequence[str], launcher: pathlib.Path) -> bool:
    value = str(launcher)
    return value in tokens and list(tokens[tokens.index(value) + 1:]) == [
        "control",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]


def _listener_rows() -> List[Tuple[int, str]]:
    completed = _run(["lsof", "-nP", "-iTCP:%d" % PORT])
    rows = []
    for line in completed.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 10:
            continue
        try:
            pid = int(fields[1])
        except ValueError:
            continue
        rows.append((pid, fields[-1]))
    return rows


def _idle_listener(pid: int) -> None:
    for index in range(CONNECTION_SAMPLES):
        rows = _listener_rows()
        if rows != [(pid, "(LISTEN)")]:
            raise RuntimeError("legacy control port has an active or unexpected connection")
        if index + 1 < CONNECTION_SAMPLES:
            time.sleep(0.2)


def _http_canary() -> int:
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3.0)
    try:
        connection.request("GET", "/api/status")
        response = connection.getresponse()
        response.read(4096)
        return response.status
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError("legacy control HTTP canary is unavailable") from exc
    finally:
        connection.close()


def _idle_state(home: pathlib.Path) -> int:
    paths = [
        home / ".config/codexx/control-plane.sqlite3",
        home / ".config/codexx/control-plane.json",
        home / ".config/codexx/control-plane-config.json",
        home / ".config/codexx/control-plane-logs/launchd.out.log",
        home / ".config/codexx/control-plane-logs/launchd.err.log",
    ]
    ages = []
    for path in paths:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise RuntimeError("legacy control state evidence is unavailable") from exc
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("legacy control state evidence is unsafe")
        ages.append(max(0, int(time.time() - metadata.st_mtime)))
    minimum = min(ages)
    if minimum < MIN_IDLE_SECONDS:
        raise RuntimeError("legacy control state is not idle for the required window")
    return minimum


def _recovery(home: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path, str]:
    runtime = legacy_removal._tree_records(home / ".local/bin/codexx_app")
    launcher_raw, unused_metadata = legacy_removal._safe_file(
        home / ".local/bin/codexx.py",
        "legacy launcher",
        legacy_removal.MAX_FILE_BYTES,
    )
    bundle, manifest = legacy_removal._recovery_bundle(home)
    legacy_removal._verify_recovery_copy(home, runtime, _sha256(launcher_raw), manifest)
    target = bundle / "home/.local/bin/codexx"
    target_raw, target_metadata = legacy_removal._safe_file(
        target,
        "retained legacy control launcher",
        legacy_removal.MAX_FILE_BYTES,
    )
    if not stat.S_IMODE(target_metadata.st_mode) & stat.S_IXUSR:
        raise RuntimeError("retained legacy control launcher is not executable")
    return bundle, target, _sha256(target_raw)


def _continuity(home: pathlib.Path, release_version: str) -> Dict[str, Any]:
    unused_artifact, selectors = legacy_removal._active_release(home, release_version)
    shell = legacy_removal._shell_snapshot(home)
    unused_legacy, cpa = legacy_removal._process_inventory(home)
    if not legacy_removal._port_open(8317):
        raise RuntimeError("external local CPA port is unavailable")
    return {"selectors": selectors, "shell": shell, "cpa": cpa}


def _target_plists(
    original: Mapping[str, Any],
    *,
    target_launcher: pathlib.Path,
    live_launcher: pathlib.Path,
    python_executable: pathlib.Path,
) -> Tuple[bytes, bytes]:
    target = copy.deepcopy(dict(original))
    target["ProgramArguments"] = [
        str(target_launcher),
        "control",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    fallback = copy.deepcopy(dict(original))
    fallback["ProgramArguments"] = [
        str(python_executable),
        str(live_launcher),
        "control",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    return plistlib.dumps(target, fmt=plistlib.FMT_XML, sort_keys=True), plistlib.dumps(
        fallback, fmt=plistlib.FMT_XML, sort_keys=True
    )


def _decision_contract(
    *,
    plist_sha256: str,
    service_pid: int,
    python_executable: str,
    bundle: pathlib.Path,
    target_sha256: str,
    continuity: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "plistSha256": plist_sha256,
        "servicePid": service_pid,
        "pythonExecutable": python_executable,
        "recoveryBundleId": bundle.name,
        "targetLauncherSha256": target_sha256,
        "selectors": continuity["selectors"],
        "localCpaPid": continuity["cpa"]["pid"],
    }


def _digest(contract: Mapping[str, Any]) -> str:
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def decision(release_version: str, home: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    selected_home = home or user_home()
    plist_raw, unused_plist = _plist(selected_home)
    service = _service()
    command = _process_command(service["pid"])
    live_launcher = selected_home / ".local/bin/codexx.py"
    if not _control_command(command, live_launcher):
        raise RuntimeError("legacy control service is not using the expected live launcher")
    python_executable = pathlib.Path(command[0])
    if not python_executable.is_absolute() or not python_executable.is_file():
        raise RuntimeError("legacy control Python executable is unavailable")
    _idle_listener(service["pid"])
    if _http_canary() != 401:
        raise RuntimeError("legacy control authentication canary changed")
    idle_seconds = _idle_state(selected_home)
    bundle, target, target_sha256 = _recovery(selected_home)
    continuity = _continuity(selected_home, release_version)
    contract = _decision_contract(
        plist_sha256=_sha256(plist_raw),
        service_pid=service["pid"],
        python_executable=str(python_executable),
        bundle=bundle,
        target_sha256=target_sha256,
        continuity=continuity,
    )
    return {
        "schema": "cloudx.legacy-local-control-migration-decision.v1",
        "status": "migration-ready",
        "decisionDigest": _digest(contract),
        "controlPid": service["pid"],
        "port": PORT,
        "activeConnections": 0,
        "minimumIdleSeconds": idle_seconds,
        "recoveryBundleId": bundle.name,
        "targetLauncherSha256": target_sha256,
        "localCpaPid": continuity["cpa"]["pid"],
        "localCpaChanged": False,
        "contract": contract,
    }


def _recover_script() -> bytes:
    source = r'''#!/usr/bin/env python3
import argparse, hashlib, http.client, json, os, pathlib, plistlib, socket, subprocess, tempfile, time
CONFIRMATION = "RECOVER LOCAL CODEXX CONTROL FROM RETAINED BACKUP"
ROOT = pathlib.Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def run(argv): return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
def port_open():
    s=socket.socket(); s.settimeout(.25)
    try: return s.connect_ex(("127.0.0.1",8765)) == 0
    finally: s.close()
def canary():
    c=http.client.HTTPConnection("127.0.0.1",8765,timeout=3)
    try:
        c.request("GET","/api/status"); r=c.getresponse(); r.read(4096); return r.status
    finally: c.close()
def atomic(path, raw):
    fd,name=tempfile.mkstemp(prefix=".control.",dir=str(path.parent))
    os.fchmod(fd,0o644)
    with os.fdopen(fd,"wb") as h: h.write(raw); h.flush(); os.fsync(h.fileno())
    os.replace(name,path)
def main():
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--mode",choices=("retained","live"),default="retained"); p.add_argument("--confirm",default=""); a=p.parse_args()
    m=json.loads((ROOT/"manifest.json").read_text()); selected=ROOT/("target.plist" if a.mode=="retained" else "fallback-live.plist")
    if sha(selected) != m["files"][selected.name]: raise SystemExit("recovery plist digest mismatch")
    plist=plistlib.loads(selected.read_bytes()); argv=plist.get("ProgramArguments",[])
    if plist.get("Label")!="com.codexx.control" or len(argv)<2: raise SystemExit("recovery plist contract is invalid")
    required=[pathlib.Path(argv[0])] if a.mode=="retained" else [pathlib.Path(argv[0]),pathlib.Path(argv[1])]
    if any(not item.is_absolute() or not item.is_file() for item in required): raise SystemExit("selected recovery runtime is unavailable")
    if a.check: print(json.dumps({"status":"ready","mode":a.mode,"portOpen":port_open()},sort_keys=True)); return
    if a.confirm != CONFIRMATION: raise SystemExit("recovery confirmation does not match")
    domain=f"gui/{os.getuid()}"; label="com.codexx.control"; live=pathlib.Path(m["livePlist"])
    run(["launchctl","bootout",f"{domain}/{label}"]); deadline=time.monotonic()+10
    while port_open() and time.monotonic()<deadline: time.sleep(.2)
    if port_open(): raise SystemExit("existing control listener did not stop")
    atomic(live,selected.read_bytes()); result=run(["launchctl","bootstrap",domain,str(live)])
    if result.returncode: raise SystemExit("launchctl bootstrap failed")
    deadline=time.monotonic()+20
    while not port_open() and time.monotonic()<deadline: time.sleep(.2)
    if not port_open() or canary()!=401: raise SystemExit("recovered control listener is unavailable")
    print(json.dumps({"status":"recovered","mode":a.mode,"port":8765},sort_keys=True))
if __name__ == "__main__": main()
'''
    return source.encode("utf-8")


def _prepare_backup(
    home: pathlib.Path,
    *,
    original: bytes,
    target: bytes,
    fallback: bytes,
    contract: Mapping[str, Any],
) -> pathlib.Path:
    backup_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise RuntimeError("legacy control backup identity is invalid")
    parent = home / ".local/state/cloudx/legacy-control-migration-backups"
    parent.mkdir(mode=0o700, exist_ok=True)
    parent.chmod(0o700)
    parent_metadata = parent.lstat()
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("legacy control backup directory is unsafe")
    root = parent / backup_id
    root.mkdir(mode=0o700)
    root_metadata = root.lstat()
    if (
        root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("legacy control backup is unsafe")
    files = {
        "original.plist": original,
        "target.plist": target,
        "fallback-live.plist": fallback,
        "recover.py": _recover_script(),
    }
    for name, raw in files.items():
        _atomic_bytes(root / name, raw, 0o700 if name.endswith(".py") else 0o600)
    manifest = {
        "schema": "cloudx.legacy-local-control-migration-backup.v1",
        "backupId": backup_id,
        "livePlist": str(_plist_path(home)),
        "decisionContract": dict(contract),
        "files": {name: _sha256(raw) for name, raw in files.items()},
        "recoveryConfirmation": RECOVERY_CONFIRMATION,
    }
    _atomic_bytes(
        root / "manifest.json",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        0o600,
    )
    manual = (
        "# Legacy control recovery\n\n"
        "Check retained recovery:\n\n"
        "    ./recover.py --check --mode retained\n\n"
        "Restore the retained runtime:\n\n"
        "    ./recover.py --mode retained --confirm \"%s\"\n\n"
        "Restore the live legacy runtime only while its launcher still exists:\n\n"
        "    ./recover.py --check --mode live\n"
        "    ./recover.py --mode live --confirm \"%s\"\n"
    ) % (RECOVERY_CONFIRMATION, RECOVERY_CONFIRMATION)
    _atomic_bytes(root / "RECOVERY.md", manual.encode("utf-8"), 0o600)
    return root


def _bootout() -> None:
    completed = _run(["launchctl", "bootout", "%s/%s" % (_launch_domain(), LABEL)])
    if completed.returncode != 0:
        raise RuntimeError("legacy control LaunchAgent bootout failed")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not legacy_removal._port_open(PORT):
            return
        time.sleep(0.2)
    raise RuntimeError("legacy control listener did not stop")


def _bootstrap(plist_raw: bytes, expected_launcher: pathlib.Path) -> int:
    _atomic_bytes(_plist_path(user_home()), plist_raw, 0o644)
    completed = _run(["launchctl", "bootstrap", _launch_domain(), str(_plist_path(user_home()))])
    if completed.returncode != 0:
        raise RuntimeError("legacy control LaunchAgent bootstrap failed")
    deadline = time.monotonic() + 20.0
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            service = _service()
            if _control_command(_process_command(service["pid"]), expected_launcher) and _http_canary() == 401:
                return service["pid"]
        except RuntimeError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError("legacy control LaunchAgent did not recover on the expected runtime") from last_error


def plan(release_version: str) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-local-control-migration-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "automaticAction": False,
        "preconditions": [
            "exact_idle_control_service",
            "zero_active_control_connections",
            "minimum_thirty_day_state_idle_window",
            "private_recovery_bundle_verified",
            "recovery_script_prepared_before_restart",
            "decision_digest_match",
            "external_local_cpa_healthy",
        ],
        "authorization": {
            "controlServiceRestart": False,
            "launchAgentWrite": False,
            "legacyPackageQuarantine": False,
            "processTermination": False,
            "localCpaMutation": False,
            "accountMutation": False,
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
    if not legacy_removal.VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if not args.check and not args.apply:
        print(json.dumps(plan(args.release_version), sort_keys=True, separators=(",", ":")))
        return 0
    if args.apply and args.confirm != CONFIRMATION:
        raise RuntimeError("legacy control migration confirmation does not match")
    if args.apply and not SHA256_RE.fullmatch(args.decision_digest):
        raise RuntimeError("legacy control migration decision digest is invalid")
    current = decision(args.release_version)
    if args.check:
        public = dict(current)
        public.pop("contract", None)
        print(json.dumps(public, sort_keys=True, separators=(",", ":")))
        return 0
    if current["decisionDigest"] != args.decision_digest:
        raise RuntimeError("legacy control migration decision changed before apply")
    home = user_home()
    with _lock(home):
        plist_raw, plist_document = _plist(home)
        service = _service()
        command = _process_command(service["pid"])
        python_executable = pathlib.Path(command[0])
        bundle, target_launcher, unused_target_sha = _recovery(home)
        continuity_before = _continuity(home, args.release_version)
        contract = _decision_contract(
            plist_sha256=_sha256(plist_raw),
            service_pid=service["pid"],
            python_executable=str(python_executable),
            bundle=bundle,
            target_sha256=current["targetLauncherSha256"],
            continuity=continuity_before,
        )
        if _digest(contract) != args.decision_digest:
            raise RuntimeError("legacy control migration identity changed before restart")
        target_plist, fallback_plist = _target_plists(
            plist_document,
            target_launcher=target_launcher,
            live_launcher=home / ".local/bin/codexx.py",
            python_executable=python_executable,
        )
        backup = _prepare_backup(
            home,
            original=plist_raw,
            target=target_plist,
            fallback=fallback_plist,
            contract=contract,
        )
        restarted = False
        try:
            _bootout()
            restarted = True
            new_pid = _bootstrap(target_plist, bundle / "home/.local/bin/codexx.py")
            if _continuity(home, args.release_version) != continuity_before:
                raise RuntimeError("local Cloudx or CPA continuity changed during control migration")
            _idle_listener(new_pid)
        except Exception as exc:
            recovery_errors = []
            try:
                if legacy_removal._port_open(PORT):
                    _bootout()
                _bootstrap(fallback_plist, home / ".local/bin/codexx.py")
                if _continuity(home, args.release_version) != continuity_before:
                    recovery_errors.append("local continuity changed after control recovery")
            except Exception:
                recovery_errors.append("live control recovery failed")
            if recovery_errors:
                raise RuntimeError(
                    "legacy control migration failed; recovery incomplete: %s"
                    % "; ".join(recovery_errors)
                ) from exc
            raise RuntimeError("legacy control migration failed and live control was restored") from exc
    print(json.dumps({
        "schema": "cloudx.legacy-local-control-migration.v1",
        "status": "migrated",
        "decisionDigest": args.decision_digest,
        "releaseVersion": args.release_version,
        "previousPid": service["pid"],
        "currentPid": new_pid,
        "port": PORT,
        "httpAuthenticationCanary": 401,
        "activeConnections": 0,
        "recoveryBundleId": bundle.name,
        "rollbackBackupId": backup.name,
        "recoveryScriptPrepared": True,
        "controlServiceRestarted": restarted,
        "legacyPackageQuarantined": False,
        "localCpaPid": continuity_before["cpa"]["pid"],
        "localCpaChanged": False,
        "accountMutation": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("migrate_legacy_local_control.py: %s" % exc, file=os.sys.stderr)
        raise SystemExit(1)
