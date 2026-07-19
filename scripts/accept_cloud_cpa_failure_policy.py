#!/usr/bin/env python3
"""Install and run the rollback-capable cloud CPA policy acceptance transaction."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import shlex
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRANSACTION_TOOL = ROOT / "scripts/cloud_cpa_failure_policy_transaction.py"
ACTIVE_VERSION = "0.1.20"
CONFIRMATION = "ACCEPT CLOUD CPA FAILURE POLICY 0.1.20"
PLAN_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance-plan.v1"
RESULT_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance.v1"
DEFAULT_SSH_HOST = "cloud"
REMOTE_TOOL_ROOT = pathlib.PurePosixPath("/var/lib/cloudx/operator-tools")
LOCAL_CPA_AUTH_DIR = pathlib.Path.home() / ".cli-proxy-api"
MAX_TOOL_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_CREDENTIAL_BYTES = 4 * 1024 * 1024


class AcceptanceRejected(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _tool_bytes() -> bytes:
    try:
        raw = TRANSACTION_TOOL.read_bytes()
    except OSError as exc:
        raise AcceptanceRejected("tool_unavailable", "cloud CPA transaction tool is unavailable") from exc
    if not raw or len(raw) > MAX_TOOL_BYTES:
        raise AcceptanceRejected("tool_unavailable", "cloud CPA transaction tool is empty or oversized")
    return raw


def _credential_bytes(path: pathlib.Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise AcceptanceRejected("quota_samples", "local CPA credential sample is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CREDENTIAL_BYTES:
            raise AcceptanceRejected("quota_samples", "local CPA credential sample is unsafe")
        raw = os.read(descriptor, MAX_CREDENTIAL_BYTES + 1)
        if not raw or len(raw) > MAX_CREDENTIAL_BYTES:
            raise AcceptanceRejected("quota_samples", "local CPA credential sample is empty or oversized")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise AcceptanceRejected("quota_samples", "local CPA credential sample is not an object")
        return raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("quota_samples", "local CPA credential sample is invalid") from exc
    finally:
        os.close(descriptor)


def _local_command(
    arguments: Sequence[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 180,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(arguments), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceRejected("quota_samples", "local signed quota probe failed") from exc
    if completed.returncode != 0 or len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise AcceptanceRejected("quota_samples", "local signed quota probe was rejected")
    return completed


def _probe_local_sample(artifact: pathlib.Path, root: pathlib.Path, source: pathlib.Path, index: int) -> Optional[bytes]:
    probe_root = root / ("probe-%d" % index)
    auth = probe_root / "auth"
    archive = probe_root / "archive"
    auth.mkdir(parents=True, mode=0o700)
    archive.mkdir(mode=0o700)
    raw = _credential_bytes(source)
    sample = auth / "sample.json"
    sample.write_bytes(raw)
    sample.chmod(0o600)
    env = dict(os.environ, CLOUDX_CPA_PROXY_URL="http://127.0.0.1:7890", CLOUDX_CPA_SWEEP_CONCURRENCY="1")
    completed = _local_command([
        sys.executable, str(artifact), "cpa-health", "--check",
        "--auth-dir", str(auth), "--archive-dir", str(archive),
        "--proxy-url", "http://127.0.0.1:7890", "--probe-concurrency", "1",
    ], env=env)
    try:
        document = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("quota_samples", "local signed quota probe returned invalid JSON") from exc
    if (
        isinstance(document, dict)
        and document.get("probe_gate") == "reachable"
        and document.get("total") == 1
        and document.get("limited") == 1
        and document.get("archived_count") == 0
    ):
        return raw
    return None


def _encode_quota_samples(samples: Sequence[bytes]) -> bytes:
    if len(samples) != 3 or len({hashlib.sha256(item).digest() for item in samples}) != 3:
        raise AcceptanceRejected("quota_samples", "exactly three distinct quota samples are required")
    return json.dumps({
        "schema": "cloudx.cpa-quota-samples.v1",
        "samples": [base64.b64encode(item).decode("ascii") for item in samples],
    }, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _quota_bundle() -> bytes:
    candidates = sorted(
        path for path in LOCAL_CPA_AUTH_DIR.glob("*.json")
        if path.is_file() and not path.is_symlink()
    )
    if len(candidates) < 3:
        raise AcceptanceRejected("quota_samples", "local CPA has fewer than three top-level samples")
    state_root = pathlib.Path.home() / ".local/state/cloudx"
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    info = state_root.lstat()
    if state_root.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise AcceptanceRejected("quota_samples", "local quota-probe state directory is unsafe")
    with tempfile.TemporaryDirectory(prefix="quota-samples.", dir=state_root) as value:
        root = pathlib.Path(value)
        root.chmod(0o700)
        artifact = root / "cloudx-cloud.pyz"
        _local_command(["scp", "-q", "cloud:/opt/cloudx/current/cloudx-cloud.pyz", str(artifact)], timeout=60)
        self_check = _local_command([sys.executable, str(artifact), "self-check"], timeout=30)
        try:
            identity = json.loads(self_check.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceRejected("quota_samples", "signed cloud artifact self-check is invalid") from exc
        if not isinstance(identity, dict) or identity.get("status") != "ok" or identity.get("version") != ACTIVE_VERSION:
            raise AcceptanceRejected("quota_samples", "signed cloud artifact version does not match")
        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
            results = list(executor.map(
                lambda item: _probe_local_sample(artifact, root, item[1], item[0]),
                enumerate(candidates, start=1),
            ))
        limited = [item for item in results if item is not None]
        if len(limited) < 3:
            raise AcceptanceRejected("quota_samples", "three current real quota-limited local samples are unavailable")
        return _encode_quota_samples(limited[:3])


def _ssh(
    host: str,
    arguments: Sequence[str],
    *,
    input_bytes: Optional[bytes] = None,
    timeout: float = 1200,
) -> subprocess.CompletedProcess[bytes]:
    try:
        remote_command = shlex.join(list(arguments))
        completed = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, remote_command],
            input=input_bytes,
            stdin=None if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceRejected("remote_command", "cloud CPA remote command failed") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise AcceptanceRejected("remote_output", "cloud CPA remote output exceeded the limit")
    if completed.returncode != 0:
        try:
            document = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = {}
        code = str(document.get("failureCode") or "remote_rejected") if isinstance(document, dict) else "remote_rejected"
        raise AcceptanceRejected(code, "cloud CPA remote acceptance was rejected")
    return completed


def _install_remote_tool(host: str) -> pathlib.PurePosixPath:
    raw = _tool_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    target = REMOTE_TOOL_ROOT / ("cloud-cpa-failure-policy-%s.py" % digest[:16])
    _ssh(host, [
        "sudo", "-n", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
        str(REMOTE_TOOL_ROOT),
    ], timeout=30)
    uploader = (
        "import hashlib,os,pathlib,sys,tempfile;"
        "p=pathlib.Path(sys.argv[1]);r=sys.stdin.buffer.read(1048577);"
        "assert 0<len(r)<=1048576;fd,n=tempfile.mkstemp(prefix='.'+p.name+'.',dir=str(p.parent));"
        "f=os.fdopen(fd,'wb');f.write(r);f.flush();os.fsync(f.fileno());f.close();"
        "os.chmod(n,0o700);os.replace(n,p);print(hashlib.sha256(r).hexdigest())"
    )
    completed = _ssh(
        host,
        ["sudo", "-n", "/usr/bin/python3", "-c", uploader, str(target)],
        input_bytes=raw,
        timeout=60,
    )
    if completed.stdout.decode("ascii", errors="replace").strip() != digest:
        raise AcceptanceRejected("tool_upload", "remote recovery-capable operator tool digest mismatch")
    return target


def plan() -> Dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "requiredActiveCloudxVersion": ACTIVE_VERSION,
        "requiredCloudCpaPolicyVersion": "7.2.71-cloudx-policy.4",
        "naturalBusinessTraffic": True,
        "businessConcurrencyMaximum": 2,
        "incidentProbeConcurrencyMinimum": 3,
        "realQuotaSampleCount": 3,
        "localQuotaProbeReadOnly": True,
        "localCpaMutation": False,
        "provisionalRefreshable401Archived": False,
        "permanentUnauthorizedArchived": 1,
        "exactRestoreRequired": True,
        "prebuiltRecoveryTool": True,
        "cpaRestartAuthorized": False,
        "automaticAction": False,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.ssh_host != DEFAULT_SSH_HOST:
        raise AcceptanceRejected("host_mismatch", "cloud CPA acceptance host is fixed")
    if not args.apply:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    if args.confirm != CONFIRMATION:
        raise AcceptanceRejected("confirmation_mismatch", "cloud CPA acceptance confirmation does not match")
    quota_bundle = _quota_bundle()
    remote_tool = _install_remote_tool(args.ssh_host)
    completed = _ssh(args.ssh_host, [
        "sudo", "-n", "/usr/bin/python3", str(remote_tool), "--apply", "--confirm", CONFIRMATION,
    ], input_bytes=quota_bundle)
    try:
        document = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("invalid_output", "remote cloud CPA acceptance returned invalid JSON") from exc
    if not isinstance(document, dict) or document.get("status") != "accepted":
        raise AcceptanceRejected("invalid_output", "remote cloud CPA acceptance result was not accepted")
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceRejected as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "status": "rejected", "failureCode": exc.code}, sort_keys=True))
        raise SystemExit(2)
