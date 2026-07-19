#!/usr/bin/env python3
"""Install and run the rollback-capable cloud CPA policy acceptance transaction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRANSACTION_TOOL = ROOT / "scripts/cloud_cpa_failure_policy_transaction.py"
ACTIVE_VERSION = "0.1.18"
CONFIRMATION = "ACCEPT CLOUD CPA FAILURE POLICY 0.1.18"
PLAN_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance-plan.v1"
RESULT_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance.v1"
DEFAULT_SSH_HOST = "cloud"
REMOTE_TOOL_ROOT = pathlib.PurePosixPath("/var/lib/cloudx/operator-tools")
MAX_TOOL_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


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


def _ssh(
    host: str,
    arguments: Sequence[str],
    *,
    input_bytes: Optional[bytes] = None,
    timeout: float = 1200,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, *arguments],
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
        "naturalBusinessTraffic": True,
        "businessConcurrencyMaximum": 2,
        "incidentProbeConcurrencyMinimum": 3,
        "realQuotaSampleCount": 3,
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
    remote_tool = _install_remote_tool(args.ssh_host)
    completed = _ssh(args.ssh_host, [
        "sudo", "-n", "/usr/bin/python3", str(remote_tool), "--apply", "--confirm", CONFIRMATION,
    ])
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
