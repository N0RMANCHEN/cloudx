#!/usr/bin/env python3
"""Stop the legacy HTTP importer after signed gate and SSH-path acceptance."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import shlex
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import http_importer_gate  # noqa: E402


CONFIRMATION = "STOP AND DISABLE codex-import.service WITH AUTOMATIC RESTORE"
DEFAULT_EVIDENCE = ROOT / "docs/archive/2026-07-17-http-importer-stop-gate-evidence.json"
DEFAULT_ROLLBACK_SNAPSHOT = pathlib.PurePosixPath(
    "/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z"
)
DEFAULT_SSH_HOST = "cloud"
DEFAULT_LOCK = pathlib.Path.home() / ".local/state/cloudx/http-importer-stop.lock"
SERVICE = "codex-import.service"
GATEWAY_UNIT = "cliproxy.service"
PHI_SERVICE = "phi-cloudx-health.service"
PHI_TIMER = "phi-cloudx-health.timer"
LISTENER_PORT = 8780
MAX_EVIDENCE_AGE_SECONDS = 300
SNAPSHOT_RE = re.compile(r"^/var/lib/cloudx/http-importer-stop-prep/[0-9]{8}T[0-9]{6}Z$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _safe_evidence(path: pathlib.Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("stop-gate evidence is unavailable or unsafe") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("stop-gate evidence must be a regular non-symlink file")
        if metadata.st_size > http_importer_gate.MAX_EVIDENCE_BYTES:
            raise RuntimeError("stop-gate evidence exceeds the size limit")
        chunks = []
        remaining = http_importer_gate.MAX_EVIDENCE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > http_importer_gate.MAX_EVIDENCE_BYTES:
            raise RuntimeError("stop-gate evidence exceeds the size limit")
        return raw
    finally:
        os.close(descriptor)


@contextmanager
def _transaction_lock() -> Iterator[None]:
    directory = DEFAULT_LOCK.parent
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = directory.lstat()
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("HTTP importer stop state directory is unsafe")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("HTTP importer stop state directory permissions are too broad")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("HTTP importer stop lock is unavailable") from exc
    try:
        lock_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(lock_metadata.st_mode) or lock_metadata.st_uid != os.geteuid():
            raise RuntimeError("HTTP importer stop lock ownership is invalid")
        if stat.S_IMODE(lock_metadata.st_mode) & 0o077:
            raise RuntimeError("HTTP importer stop lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _ssh(
    arguments: Sequence[str],
    *,
    input_bytes: Optional[bytes] = None,
    timeout: float = 30.0,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", DEFAULT_SSH_HOST, *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError("cloud maintenance command failed")
    if len(completed.stdout) > 1024 * 1024 or len(completed.stderr) > 1024 * 1024:
        raise RuntimeError("cloud maintenance command output exceeded the limit")
    return completed


def _ssh_shell(command: str, *, timeout: float = 30.0) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", DEFAULT_SSH_HOST, command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("cloud maintenance verification failed")
    if len(completed.stdout) > 1024 * 1024 or len(completed.stderr) > 1024 * 1024:
        raise RuntimeError("cloud maintenance verification output exceeded the limit")
    return completed


def _parse_json(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("%s returned invalid JSON" % label) from exc
    if not isinstance(value, dict):
        raise RuntimeError("%s returned an invalid document" % label)
    return value


def _fresh_gate(raw: bytes, expected_digest: str) -> Mapping[str, Any]:
    try:
        decision = http_importer_gate.evaluate(raw)
    except http_importer_gate.EvidenceRejected as exc:
        raise RuntimeError("stop-gate evidence was rejected") from exc
    if (
        decision.get("status") != "preconditions-satisfied"
        or decision.get("preconditionsSatisfied") is not True
        or decision.get("automaticAction") is not False
        or decision.get("authorization", {}).get("serviceStop") is not False
        or decision.get("blockers") != []
        or decision.get("evidenceDigest") != expected_digest
    ):
        raise RuntimeError("stop-gate preconditions are not satisfied for the expected evidence")
    captured = str(decision["capturedAt"])
    candidate = captured[:-1] + "+00:00" if captured.endswith("Z") else captured
    try:
        observed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise RuntimeError("stop-gate capture time is invalid") from exc
    now = dt.datetime.now(dt.timezone.utc)
    age = (now - observed.astimezone(dt.timezone.utc)).total_seconds()
    if age < -30 or age > MAX_EVIDENCE_AGE_SECONDS:
        raise RuntimeError("stop-gate evidence is not fresh enough for a service stop")
    return decision


def _remote_gate(
    raw: bytes,
    artifact: pathlib.PurePosixPath,
    release_version: str,
) -> Mapping[str, Any]:
    self_check = _parse_json(
        _ssh(
            [
                "sudo",
                "-n",
                "/usr/bin/python3",
                str(artifact),
                "self-check",
            ]
        ).stdout,
        "signed cloud artifact self-check",
    )
    if (
        self_check.get("schema") != "cloudx.self-check.v1"
        or self_check.get("component") != "cloud"
        or self_check.get("version") != release_version
        or self_check.get("status") != "ok"
    ):
        raise RuntimeError("signed cloud artifact self-check did not match the stop transaction")
    completed = _ssh(
        [
            "sudo",
            "-n",
            "/usr/bin/python3",
            str(artifact),
            "http-importer-stop-gate",
        ],
        input_bytes=raw,
    )
    return _parse_json(completed.stdout, "signed stop-gate evaluator")


def _verify_snapshot(path: pathlib.PurePosixPath) -> None:
    raw = str(path)
    if not SNAPSHOT_RE.fullmatch(raw):
        raise RuntimeError("rollback snapshot path is outside the declared contract")
    quoted = shlex.quote(raw)
    command = (
        "sudo -n /bin/sh -c "
        + shlex.quote("cd %s && /usr/bin/sha256sum -c SHA256SUMS" % quoted)
    )
    completed = _ssh_shell(command, timeout=60.0)
    lines = [line for line in completed.stdout.decode("utf-8", errors="strict").splitlines() if line]
    if not lines or any(not line.endswith(": OK") for line in lines):
        raise RuntimeError("rollback snapshot manifest verification failed")
    required = (
        "importer-runtime.tar.gz: OK",
        "importer-systemd.tar.gz: OK",
        "import-failures.tar.gz: OK",
        "restore-plan.txt: OK",
        "token-metadata.txt: OK",
        "snapshot.json: OK",
    )
    if any(not any(line.endswith(value) for line in lines) for value in required):
        raise RuntimeError("rollback snapshot is incomplete")


def _properties(unit: str, names: Sequence[str]) -> Dict[str, str]:
    arguments = ["systemctl", "show", unit]
    for name in names:
        arguments.extend(["-p", name])
    arguments.append("--no-pager")
    completed = _ssh(arguments)
    values: Dict[str, str] = {}
    for line in completed.stdout.decode("utf-8", errors="strict").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if set(values) != set(names):
        raise RuntimeError("cloud service state is incomplete")
    return values


def _service_state() -> Dict[str, Any]:
    values = _properties(
        SERVICE,
        ("LoadState", "ActiveState", "SubState", "UnitFileState", "MainPID", "NRestarts"),
    )
    try:
        pid = int(values["MainPID"])
        restarts = int(values["NRestarts"])
    except ValueError as exc:
        raise RuntimeError("HTTP importer service state is invalid") from exc
    return {
        "loadState": values["LoadState"],
        "activeState": values["ActiveState"],
        "subState": values["SubState"],
        "unitFileState": values["UnitFileState"],
        "mainPid": pid,
        "restarts": restarts,
    }


def _continuity_state() -> Dict[str, Any]:
    gateway = _properties(GATEWAY_UNIT, ("ActiveState", "MainPID", "NRestarts"))
    selectors = _ssh(["readlink", "/opt/cloudx/current", "/opt/cloudx/previous"])
    selector_lines = selectors.stdout.decode("utf-8", errors="strict").splitlines()
    if len(selector_lines) != 2:
        raise RuntimeError("Cloudx release selector state is incomplete")
    try:
        gateway_pid = int(gateway["MainPID"])
        gateway_restarts = int(gateway["NRestarts"])
    except ValueError as exc:
        raise RuntimeError("gateway continuity state is invalid") from exc
    if gateway["ActiveState"] != "active" or gateway_pid <= 0:
        raise RuntimeError("gateway is not active")
    return {
        "gatewayPid": gateway_pid,
        "gatewayRestarts": gateway_restarts,
        "currentSelector": selector_lines[0],
        "previousSelector": selector_lines[1],
    }


def _listener_counts() -> Tuple[int, int]:
    listening = _ssh(["ss", "-H", "-ltn"])
    established = _ssh(["ss", "-H", "-tn", "state", "established"])

    def matches(raw: bytes) -> int:
        total = 0
        for line in raw.decode("utf-8", errors="strict").splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            local = fields[3]
            try:
                port = int(local.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                continue
            if port == LISTENER_PORT:
                total += 1
        return total

    return matches(listening.stdout), matches(established.stdout)


def _require_active_baseline() -> Dict[str, Any]:
    state = _service_state()
    listeners, established = _listener_counts()
    if (
        state["loadState"] != "loaded"
        or state["activeState"] != "active"
        or state["subState"] != "running"
        or state["unitFileState"] not in {"enabled", "enabled-runtime"}
        or state["mainPid"] <= 0
        or listeners != 1
        or established != 0
    ):
        raise RuntimeError("HTTP importer baseline is not safe to stop")
    return state


def _disable_importer() -> None:
    _ssh(["sudo", "-n", "systemctl", "disable", "--now", SERVICE], timeout=60.0)


def _restore_importer() -> None:
    _ssh(["sudo", "-n", "systemctl", "enable", "--now", SERVICE], timeout=60.0)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        state = _service_state()
        listeners, _established = _listener_counts()
        if (
            state["activeState"] == "active"
            and state["subState"] == "running"
            and state["unitFileState"] in {"enabled", "enabled-runtime"}
            and state["mainPid"] > 0
            and listeners == 1
        ):
            return
        time.sleep(0.25)
    raise RuntimeError("HTTP importer restore did not become healthy")


def _require_stopped() -> Dict[str, Any]:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        state = _service_state()
        listeners, established = _listener_counts()
        if (
            state["loadState"] == "loaded"
            and state["activeState"] == "inactive"
            and state["unitFileState"] == "disabled"
            and state["mainPid"] == 0
            and listeners == 0
            and established == 0
        ):
            return state
        time.sleep(0.25)
    raise RuntimeError("HTTP importer did not stop cleanly")


def _ssh_import_canary() -> None:
    fixture = json.dumps(
        {
            "access_token": "fixture.stop.canary",
            "refresh_token": "fixture.stop.refresh",
            "account_id": "cloudx-stop-canary",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    completed = _ssh(["cloudx-remote", "import", "--dry-run"], input_bytes=fixture)
    document = _parse_json(completed.stdout, "SSH import canary")
    if (
        document.get("schema") != "cloudx.import.v1"
        or document.get("dryRun") is not True
        or document.get("status") != "accepted"
        or not isinstance(document.get("written"), int)
        or not isinstance(document.get("skipped"), int)
        or document["written"] + document["skipped"] < 1
        or document.get("errors") != []
    ):
        raise RuntimeError("SSH import canary was not accepted")


def _health_canaries() -> None:
    health = _parse_json(_ssh(["cloudx-remote", "health", "--json"]).stdout, "formal health canary")
    if (
        health.get("schema") != "cloudx.health.v1"
        or health.get("importStatus") != "ready"
        or health.get("gatewayStatus") != "healthy"
        or health.get("freshness", {}).get("state") != "fresh"
    ):
        raise RuntimeError("formal health canary was not accepted")
    handshake = _parse_json(_ssh(["cloudx-remote", "handshake", "--json"]).stdout, "gateway canary")
    if handshake.get("schema") != "cloudx.handshake.v1" or handshake.get("gateway", {}).get("status") != "healthy":
        raise RuntimeError("gateway model canary was not accepted")
    timer = _properties(PHI_TIMER, ("LoadState", "ActiveState", "UnitFileState"))
    service = _properties(PHI_SERVICE, ("LoadState", "Result", "ExecMainStatus"))
    if (
        timer["LoadState"] != "loaded"
        or timer["ActiveState"] != "active"
        or timer["UnitFileState"] not in {"enabled", "enabled-runtime"}
        or service["LoadState"] != "loaded"
        or service["Result"] != "success"
        or service["ExecMainStatus"] != "0"
    ):
        raise RuntimeError("Phi formal-health consumer canary was not accepted")


def plan(release_version: str, artifact: pathlib.PurePosixPath, snapshot: pathlib.PurePosixPath) -> Dict[str, Any]:
    return {
        "schema": "cloudx.http-importer-stop-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": str(artifact),
        "service": SERVICE,
        "listenerPort": LISTENER_PORT,
        "rollbackSnapshot": str(snapshot),
        "evidenceRequired": True,
        "maximumEvidenceAgeSeconds": MAX_EVIDENCE_AGE_SECONDS,
        "automaticAction": False,
        "canaries": [
            "signed_stop_gate",
            "rollback_manifest",
            "listener_closed",
            "ssh_import_dry_run",
            "formal_health",
            "phi_formal_health_consumer",
            "gateway_model",
            "selector_and_gateway_continuity",
        ],
        "authorization": {
            "serviceStop": False,
            "serviceDisable": False,
            "serviceRestoreOnFailure": False,
            "runtimeRemoval": False,
            "unitRemoval": False,
            "tokenRemoval": False,
            "failureReceiptRemoval": False,
            "rollbackSnapshotRemoval": False,
            "gatewayRestart": False,
            "phiServiceRestart": False,
            "releaseActivation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    root.add_argument("--evidence", type=pathlib.Path, default=DEFAULT_EVIDENCE)
    root.add_argument("--evidence-digest", default="")
    root.add_argument(
        "--rollback-snapshot",
        type=pathlib.PurePosixPath,
        default=DEFAULT_ROLLBACK_SNAPSHOT,
    )
    root.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if args.ssh_host != DEFAULT_SSH_HOST:
        raise RuntimeError("HTTP importer stop is restricted to the declared cloud host")
    artifact = pathlib.PurePosixPath(
        "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % args.release_version
    )
    if not SNAPSHOT_RE.fullmatch(str(args.rollback_snapshot)):
        raise RuntimeError("rollback snapshot path is outside the declared contract")
    if not args.apply:
        print(json.dumps(plan(args.release_version, artifact, args.rollback_snapshot), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("HTTP importer stop confirmation does not match")
    if not DIGEST_RE.fullmatch(args.evidence_digest):
        raise RuntimeError("HTTP importer stop requires the exact evidence digest")

    with _transaction_lock():
        raw = _safe_evidence(args.evidence)
        local_decision = _fresh_gate(raw, args.evidence_digest)
        remote_decision = _remote_gate(raw, artifact, args.release_version)
        if remote_decision != local_decision:
            raise RuntimeError("signed and local stop-gate decisions do not match")
        _verify_snapshot(args.rollback_snapshot)
        service_before = _require_active_baseline()
        continuity_before = _continuity_state()

        stop_attempted = False
        try:
            stop_attempted = True
            _disable_importer()
            _require_stopped()
            _ssh_import_canary()
            _health_canaries()
            continuity_after = _continuity_state()
            if continuity_after != continuity_before:
                raise RuntimeError("gateway or release selector continuity changed")
        except Exception as exc:
            recovery_errors = []
            if stop_attempted:
                try:
                    _restore_importer()
                except Exception:  # pragma: no cover - hard failure path
                    recovery_errors.append("importer restore failed")
            try:
                if _continuity_state() != continuity_before:
                    recovery_errors.append("gateway or selector continuity changed")
            except Exception:  # pragma: no cover - external continuity failure
                recovery_errors.append("gateway or selector continuity unavailable")
            if recovery_errors:
                raise RuntimeError(
                    "HTTP importer stop failed; recovery incomplete: %s"
                    % "; ".join(recovery_errors)
                ) from exc
            raise RuntimeError("HTTP importer stop failed and the service was restored") from exc

    print(json.dumps({
        "schema": "cloudx.http-importer-stop.v1",
        "status": "stopped",
        "releaseVersion": args.release_version,
        "releaseArtifact": str(artifact),
        "service": SERVICE,
        "previousPid": service_before["mainPid"],
        "listenerPort": LISTENER_PORT,
        "evidenceDigest": args.evidence_digest,
        "rollbackSnapshot": str(args.rollback_snapshot),
        "serviceActive": False,
        "serviceEnabled": False,
        "listenerClosed": True,
        "sshImportDryRunAccepted": True,
        "formalHealthAccepted": True,
        "phiConsumerAccepted": True,
        "gatewayModelAccepted": True,
        "gatewayProcessUnchanged": True,
        "selectorsUnchanged": True,
        "rollbackSnapshotRetained": True,
        "runtimeRemoved": False,
        "unitRemoved": False,
        "tokenRemoved": False,
        "failureReceiptsRemoved": False,
        "legacyExporterRetained": True,
        "gatewayRestarted": False,
        "phiServiceRestarted": False,
        "releaseActivated": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("stop_http_importer.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
