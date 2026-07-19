#!/usr/bin/env python3
"""Retire only proven-unusable orphaned legacy codexx exec process groups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence


CONFIRMATION = "RETIRE STALE ORPHANED LOCAL CODEXX EXEC PROCESSES"
MIN_AGE_SECONDS = 30 * 24 * 60 * 60
MIN_CPU_PERCENT = 80.0
CPU_SAMPLES = 3
MAX_TARGET_GROUPS = 8
SYSTEM_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    pgid: int
    started_at: int
    tty: str
    state: str
    cpu: float
    command: str


@dataclass(frozen=True)
class Target:
    parent: Process
    child: Process


def user_home() -> pathlib.Path:
    return pathlib.Path.home().resolve()


def _run(command: Sequence[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def _processes() -> List[Process]:
    completed = _run([
        "ps",
        "-axo",
        "pid=,ppid=,pgid=,lstart=,tty=,stat=,%cpu=,command=",
    ])
    if completed.returncode != 0 or len(completed.stdout) > 8 * 1024 * 1024:
        raise RuntimeError("local process inventory is unavailable")
    processes = []
    for line in completed.stdout.splitlines():
        fields = line.strip().split(None, 11)
        if len(fields) != 12:
            continue
        try:
            started = datetime.strptime(" ".join(fields[3:8]), "%a %b %d %H:%M:%S %Y")
            processes.append(Process(
                pid=int(fields[0]),
                ppid=int(fields[1]),
                pgid=int(fields[2]),
                started_at=int(started.timestamp()),
                tty=fields[8],
                state=fields[9],
                cpu=float(fields[10]),
                command=fields[11],
            ))
        except (ValueError, OverflowError):
            continue
    return processes


def _tokens(command: str) -> List[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _age(process: Process) -> int:
    return max(0, int(time.time()) - process.started_at)


def _network_free(pid: int) -> bool:
    completed = _run(["lsof", "-nP", "-a", "-p", str(pid), "-i"])
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return not lines or (len(lines) == 1 and lines[0].startswith("COMMAND "))


def _stdio_revoked(pid: int) -> bool:
    completed = _run(["lsof", "-nP", "-a", "-p", str(pid), "-d", "0,1,2"])
    found = set()
    for line in completed.stdout.splitlines()[1:]:
        match = re.search(r"\s([012])[rwu]?\s+.*\(revoked\)\s*$", line)
        if match:
            found.add(int(match.group(1)))
    return found == {0, 1, 2}


def _sample_cpu(pids: Iterable[int]) -> Dict[int, List[float]]:
    selected = sorted(set(int(pid) for pid in pids))
    samples = {pid: [] for pid in selected}
    for index in range(CPU_SAMPLES):
        completed = _run([
            "ps",
            "-p",
            ",".join(str(pid) for pid in selected),
            "-o",
            "pid=,%cpu=",
        ])
        if completed.returncode != 0:
            raise RuntimeError("stale process CPU evidence is unavailable")
        current = {}
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2:
                try:
                    current[int(fields[0])] = float(fields[1])
                except ValueError:
                    pass
        if set(current) != set(selected):
            raise RuntimeError("stale process identity changed during CPU sampling")
        for pid, value in current.items():
            samples[pid].append(value)
        if index + 1 < CPU_SAMPLES:
            time.sleep(0.2)
    return samples


def _port_open(port: int) -> bool:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(0.25)
        return connection.connect_ex(("127.0.0.1", port)) == 0
    finally:
        connection.close()


def _targets(home: pathlib.Path, processes: Sequence[Process]) -> List[Target]:
    launcher = str(home / ".local/bin/codexx.py")
    official_codex = shutil.which("codex", path=SYSTEM_PATH)
    if not official_codex or official_codex.startswith(str(home)):
        raise RuntimeError("official Codex executable is unavailable")
    by_parent: Dict[int, List[Process]] = {}
    for process in processes:
        by_parent.setdefault(process.ppid, []).append(process)
    targets = []
    for parent in processes:
        tokens = _tokens(parent.command)
        if launcher not in tokens:
            continue
        index = tokens.index(launcher)
        if tokens[index + 1:] != ["exec"]:
            continue
        if (
            index < 1
            or parent.ppid != 1
            or parent.pgid != parent.pid
            or parent.tty not in {"?", "??"}
            or parent.state.startswith("Z")
            or _age(parent) < MIN_AGE_SECONDS
        ):
            raise RuntimeError("legacy codexx exec process is not a safe orphan target")
        children = by_parent.get(parent.pid, [])
        if len(children) != 1:
            raise RuntimeError("legacy codexx exec process has an unexpected child set")
        child = children[0]
        child_tokens = _tokens(child.command)
        if (
            not child_tokens
            or pathlib.Path(child_tokens[0]).resolve() != pathlib.Path(official_codex).resolve()
            or child.pgid != parent.pgid
            or child.tty not in {"?", "??"}
            or child.state.startswith("Z")
            or _age(child) < MIN_AGE_SECONDS
            or by_parent.get(child.pid)
        ):
            raise RuntimeError("legacy codexx child is not one stale official Codex process")
        for process in (parent, child):
            if not _network_free(process.pid) or not _stdio_revoked(process.pid):
                raise RuntimeError("legacy codexx orphan still has usable communication")
        targets.append(Target(parent=parent, child=child))
    if not targets:
        raise RuntimeError("no stale orphaned legacy codexx exec process is eligible")
    if len(targets) > MAX_TARGET_GROUPS:
        raise RuntimeError("stale legacy process target count exceeds the safety limit")
    cpu = _sample_cpu(target.child.pid for target in targets)
    if any(
        len(cpu[target.child.pid]) != CPU_SAMPLES
        or min(cpu[target.child.pid]) < MIN_CPU_PERCENT
        for target in targets
    ):
        raise RuntimeError("legacy Codex child is not consistently stale and CPU-bound")
    return sorted(targets, key=lambda target: target.parent.pid)


def _local_cpa(home: pathlib.Path, processes: Sequence[Process]) -> int:
    marker = str(home / ".local/bin/cli-proxy-api")
    matches = [process for process in processes if marker in process.command]
    if len(matches) != 1 or not _port_open(8317):
        raise RuntimeError("external local CPA continuity is unavailable")
    return matches[0].pid


def _stable_contract(targets: Sequence[Target], cpa_pid: int) -> Dict[str, Any]:
    return {
        "targets": [
            {
                "parentPid": target.parent.pid,
                "childPid": target.child.pid,
                "processGroup": target.parent.pgid,
                "startedAtEpoch": target.parent.started_at,
            }
            for target in targets
        ],
        "localCpaPid": cpa_pid,
    }


def _digest(contract: Dict[str, Any]) -> str:
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def decision(home: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    selected_home = home or user_home()
    processes = _processes()
    targets = _targets(selected_home, processes)
    cpa_pid = _local_cpa(selected_home, processes)
    contract = _stable_contract(targets, cpa_pid)
    return {
        "schema": "cloudx.stale-local-codexx-exec-decision.v1",
        "status": "retirement-ready",
        "decisionDigest": _digest(contract),
        "targetCount": len(targets),
        "targetPids": [target.parent.pid for target in targets],
        "childPids": [target.child.pid for target in targets],
        "minimumAgeSeconds": MIN_AGE_SECONDS,
        "stdioRevoked": True,
        "networkSockets": 0,
        "minimumObservedCpuPercent": MIN_CPU_PERCENT,
        "localCpaPid": cpa_pid,
        "localCpaChanged": False,
        "irreversibleProcessTerminationRequired": True,
        "contract": contract,
    }


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate(targets: Sequence[Target]) -> None:
    for target in targets:
        os.killpg(target.parent.pgid, signal.SIGTERM)
    deadline = time.monotonic() + 20.0
    pids = [process.pid for target in targets for process in (target.parent, target.child)]
    while time.monotonic() < deadline:
        if not any(_alive(pid) for pid in pids):
            return
        time.sleep(0.2)
    raise RuntimeError("stale process group did not exit after SIGTERM; no SIGKILL was sent")


def plan() -> Dict[str, Any]:
    return {
        "schema": "cloudx.stale-local-codexx-exec-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "automaticAction": False,
        "preconditions": [
            "orphan_parent_ppid_one",
            "one_official_codex_child",
            "minimum_thirty_day_age",
            "revoked_standard_io",
            "zero_network_sockets",
            "sustained_cpu_bound_state",
            "decision_digest_match",
            "external_local_cpa_healthy",
        ],
        "authorization": {
            "processInspection": False,
            "processTermination": False,
            "sigkill": False,
            "localCpaMutation": False,
            "serviceRestart": False,
            "fileMutation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    mode = root.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--decision-digest", default="")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not args.check and not args.apply:
        print(json.dumps(plan(), sort_keys=True, separators=(",", ":")))
        return 0
    if args.apply and args.confirm != CONFIRMATION:
        raise RuntimeError("stale legacy process retirement confirmation does not match")
    if args.apply and not SHA256_RE.fullmatch(args.decision_digest):
        raise RuntimeError("stale legacy process decision digest is invalid")
    current = decision()
    if args.check:
        public = dict(current)
        public.pop("contract", None)
        print(json.dumps(public, sort_keys=True, separators=(",", ":")))
        return 0
    if current["decisionDigest"] != args.decision_digest:
        raise RuntimeError("stale legacy process decision changed before apply")
    targets_by_parent = {target.parent.pid: target for target in _targets(user_home(), _processes())}
    targets = [targets_by_parent[pid] for pid in current["targetPids"]]
    if _digest(_stable_contract(targets, current["localCpaPid"])) != args.decision_digest:
        raise RuntimeError("stale legacy process identity changed before termination")
    _terminate(targets)
    after = _processes()
    if any(process.pid in set(current["targetPids"] + current["childPids"]) for process in after):
        raise RuntimeError("stale legacy process remained after SIGTERM")
    if _local_cpa(user_home(), after) != current["localCpaPid"]:
        raise RuntimeError("external local CPA continuity changed during stale process retirement")
    print(json.dumps({
        "schema": "cloudx.stale-local-codexx-exec-retirement.v1",
        "status": "retired",
        "decisionDigest": args.decision_digest,
        "processGroupsRetired": len(targets),
        "parentProcessesRetired": len(targets),
        "childProcessesRetired": len(targets),
        "signal": "SIGTERM",
        "sigkillSent": False,
        "fileMutation": False,
        "serviceRestarted": False,
        "localCpaPid": current["localCpaPid"],
        "localCpaChanged": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("retire_stale_local_codexx_exec.py: %s" % exc, file=os.sys.stderr)
        raise SystemExit(1)
