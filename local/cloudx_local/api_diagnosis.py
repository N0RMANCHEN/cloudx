from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import accounts
from .api_failure import (
    CAUSE_ACCESS_DENIED,
    CAUSE_ACCOUNT_DEACTIVATED,
    CAUSE_GATEWAY_AUTHENTICATION,
    CAUSE_GATEWAY_FAILURE,
    CAUSE_GATEWAY_UNREACHABLE,
    CAUSE_LOGIN_REQUIRED,
    CAUSE_NO_USABLE_ACCOUNTS,
    CAUSE_QUOTA_EXHAUSTED,
    CAUSE_RATE_LIMITED,
    CAUSE_UNKNOWN,
    CAUSE_UPSTREAM_FAILURE,
    DEFINITIVE_ACCOUNT_CAUSES,
    ROOT_CAUSE_WINDOW_SECONDS,
    classify_http_failure,
    iso_utc,
    parse_timestamp,
    utc_now,
)
from .broker import BrokerClient
from .cloud_cli import probe_endpoint
from .config import LocalConfig
from .remote import RemoteClient


SCHEMA = "cloudx.api-diagnosis.v1"
MAX_PROFILE_BYTES = 256 * 1024
MAX_LOG_TAIL_BYTES = 512 * 1024
MAX_LOG_FILE_BYTES = 32 * 1024 * 1024
MAX_LOG_FILES = 100
LOG_LOOKBACK_SECONDS = 6 * 60 * 60

_BASE_URL = re.compile(r'^\s*openai_base_url\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
_TIMESTAMP = re.compile(r"^Timestamp:\s*(\S+)\s*$", re.MULTILINE)
_STATUS = re.compile(r"^Status:\s*([1-5][0-9]{2})\s*$", re.MULTILINE)


CAUSE_LABELS = {
    CAUSE_ACCOUNT_DEACTIVATED: "account deactivated",
    CAUSE_QUOTA_EXHAUSTED: "quota exhausted",
    CAUSE_RATE_LIMITED: "temporarily rate limited",
    CAUSE_LOGIN_REQUIRED: "login required",
    CAUSE_ACCESS_DENIED: "access or model permission denied",
    CAUSE_NO_USABLE_ACCOUNTS: "no usable accounts",
    CAUSE_GATEWAY_AUTHENTICATION: "gateway authentication failed",
    CAUSE_GATEWAY_UNREACHABLE: "gateway unreachable",
    CAUSE_GATEWAY_FAILURE: "gateway failure",
    CAUSE_UPSTREAM_FAILURE: "upstream provider failure",
    CAUSE_UNKNOWN: "undetermined",
    "none": "none",
}

MEANINGS = {
    CAUSE_ACCOUNT_DEACTIVATED: (
        "The upstream response explicitly says the account is deactivated or suspended; "
        "this is not a quota or token-expiry diagnosis."
    ),
    CAUSE_QUOTA_EXHAUSTED: (
        "The account usage allowance or credit window is exhausted; the evidence does not "
        "indicate account deactivation or an invalid login token."
    ),
    CAUSE_RATE_LIMITED: (
        "The provider is temporarily limiting request or token rate; this is distinct from "
        "a depleted usage allowance."
    ),
    CAUSE_LOGIN_REQUIRED: (
        "The access or refresh credential is invalid, expired, revoked, or already used; "
        "this is not evidence that quota is exhausted."
    ),
    CAUSE_ACCESS_DENIED: (
        "The credential lacks permission for the requested model, project, or organization; "
        "a generic 403 is not treated as account deactivation."
    ),
    CAUSE_NO_USABLE_ACCOUNTS: (
        "The gateway has no currently selectable account, but it did not preserve a more "
        "specific upstream reason."
    ),
    CAUSE_GATEWAY_AUTHENTICATION: "The client credential presented to the gateway was rejected.",
    CAUSE_GATEWAY_UNREACHABLE: "No HTTP response was received from the selected gateway.",
    CAUSE_GATEWAY_FAILURE: "The gateway returned a server-side failure before a usable upstream result.",
    CAUSE_UPSTREAM_FAILURE: "The upstream provider returned a server-side failure without an account-specific cause.",
    CAUSE_UNKNOWN: (
        "Available evidence cannot safely distinguish deactivation, quota, login, permission, "
        "or provider failure."
    ),
    "none": (
        "The gateway probe is reachable, but a model-list check alone does not prove that an "
        "upstream account has remaining quota."
    ),
}

NEXT_STEPS = {
    CAUSE_ACCOUNT_DEACTIVATED: "Replace the credential or use the provider appeal/support path; re-login or waiting for quota reset will not resolve an explicit deactivation.",
    CAUSE_QUOTA_EXHAUSTED: "Wait until the reported reset time or use an account with remaining allowance.",
    CAUSE_RATE_LIMITED: "Retry with bounded backoff or reduce request concurrency and token rate.",
    CAUSE_LOGIN_REQUIRED: "Re-authenticate the affected upstream account and replace the stale credential.",
    CAUSE_ACCESS_DENIED: "Check model entitlement, organization/project membership, and the requested model.",
    CAUSE_NO_USABLE_ACCOUNTS: "Inspect credential health; do not assume quota exhaustion or deactivation without a definitive upstream signal.",
    CAUSE_GATEWAY_AUTHENTICATION: "Verify the scoped local gateway key without exposing or rotating it as part of diagnosis.",
    CAUSE_GATEWAY_UNREACHABLE: "Check the local service or cloud tunnel/network path; diagnosis does not restart either one.",
    CAUSE_GATEWAY_FAILURE: "Inspect the external gateway health and retained error evidence; diagnosis does not restart the gateway.",
    CAUSE_UPSTREAM_FAILURE: "Retry with bounded backoff; if it persists, inspect provider and gateway health without changing credentials.",
    CAUSE_UNKNOWN: "Retry once, then run diagnosis immediately after the failure so the structured upstream evidence is still available.",
    "none": "Run this command immediately after a failed Codex turn to classify the retained response evidence.",
}


def _read_regular(path: pathlib.Path, limit: int) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
        raise OSError("unsafe or oversized file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
            raise OSError("unsafe or oversized file")
        raw = os.read(descriptor, limit + 1)
    finally:
        os.close(descriptor)
    if len(raw) > limit:
        raise OSError("oversized file")
    return raw


def _read_response_tail(path: pathlib.Path) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_LOG_FILE_BYTES:
        raise OSError("unsafe or oversized log")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_LOG_FILE_BYTES:
            raise OSError("unsafe or oversized log")
        marker = b"=== API RESPONSE ==="
        remaining = min(opened.st_size, MAX_LOG_TAIL_BYTES)
        position = opened.st_size
        buffered = b""
        while remaining > 0:
            amount = min(16 * 1024, remaining)
            position -= amount
            os.lseek(descriptor, position, os.SEEK_SET)
            buffered = os.read(descriptor, amount) + buffered
            found = buffered.find(marker)
            if found >= 0:
                return buffered[found:]
            remaining -= amount
        return b""
    finally:
        os.close(descriptor)


def _profile_key_and_port(config: LocalConfig, account: str) -> Tuple[str, int]:
    home = accounts.account_home(config, account)
    key = ""
    try:
        auth = json.loads(_read_regular(home / "auth.json", MAX_PROFILE_BYTES).decode("utf-8"))
        if isinstance(auth, dict):
            key = str(auth.get("OPENAI_API_KEY") or auth.get("api_key") or "").strip()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    port = 8317
    try:
        text = _read_regular(home / "config.toml", MAX_PROFILE_BYTES).decode("utf-8")
        match = _BASE_URL.search(text)
        parsed = urllib.parse.urlsplit(match.group(1)) if match else None
        if parsed and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
            port = parsed.port or 80
    except (OSError, UnicodeDecodeError, ValueError):
        pass
    return key, port


def _gateway(status: Optional[int]) -> Dict[str, Any]:
    if status is None:
        state = "unreachable"
    elif 200 <= status < 300:
        state = "reachable"
    elif status in (401, 403):
        state = "authentication_failed"
    elif status >= 500:
        state = "server_failure"
    else:
        state = "client_failure"
    return {"state": state, "httpStatus": status}


def _gateway_cause(gateway: Dict[str, Any]) -> str:
    return {
        "authentication_failed": CAUSE_GATEWAY_AUTHENTICATION,
        "unreachable": CAUSE_GATEWAY_UNREACHABLE,
        "server_failure": CAUSE_GATEWAY_FAILURE,
        "client_failure": CAUSE_GATEWAY_FAILURE,
    }.get(str(gateway.get("state") or ""), "none")


def _parse_log(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    try:
        text = _read_response_tail(path).decode("utf-8", errors="replace")
    except OSError:
        return None
    marker = "=== API RESPONSE ==="
    if marker not in text:
        return None
    api_response = text.split(marker, 1)[1]
    response_body = api_response.split("=== RESPONSE ===", 1)[0]
    response_section = api_response.split("=== RESPONSE ===", 1)[1] if "=== RESPONSE ===" in api_response else ""
    status_match = _STATUS.search(response_section)
    status = int(status_match.group(1)) if status_match else None
    timestamp_match = _TIMESTAMP.search(api_response)
    observed = parse_timestamp(timestamp_match.group(1)) if timestamp_match else None
    if observed is None:
        try:
            observed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            observed = utc_now()
    failure = classify_http_failure(status, response_body.encode("utf-8"), observed_at=observed)
    return failure.as_observation("gateway_error_log")


def recent_local_observation(
    config: LocalConfig,
    *,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    current = now or utc_now()
    log_dir = pathlib.Path(
        os.environ.get("CLOUDX_LOCAL_CPA_LOG_DIR", str(config.home / ".cli-proxy-api/logs"))
    ).expanduser()
    try:
        metadata = log_dir.lstat()
        if log_dir.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            return None
        paths = sorted(
            (
                path
                for path in log_dir.glob("error-*.log")
                if path.is_file() and not path.is_symlink()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:MAX_LOG_FILES]
    except OSError:
        return None
    observations: List[Dict[str, Any]] = []
    cutoff = current - timedelta(seconds=LOG_LOOKBACK_SECONDS)
    for path in paths:
        observation = _parse_log(path)
        if observation is None:
            continue
        observed = parse_timestamp(observation.get("observedAt"))
        if observed is None or observed < cutoff or observed > current + timedelta(minutes=5):
            continue
        observations.append(observation)
    if not observations:
        return None
    observations.sort(
        key=lambda item: parse_timestamp(item.get("observedAt")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    latest = observations[0]
    if latest.get("cause") != CAUSE_NO_USABLE_ACCOUNTS:
        return latest
    latest_time = parse_timestamp(latest.get("observedAt")) or current
    for candidate in observations[1:]:
        candidate_time = parse_timestamp(candidate.get("observedAt"))
        if candidate_time is None or (latest_time - candidate_time).total_seconds() > ROOT_CAUSE_WINDOW_SECONDS:
            break
        if candidate.get("cause") in DEFINITIVE_ACCOUNT_CAUSES:
            result = dict(candidate)
            result["maskedBy"] = CAUSE_NO_USABLE_ACCOUNTS
            return result
    return latest


def _diagnosis(target: str, gateway: Dict[str, Any], observation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if observation is not None:
        cause = str(observation.get("cause") or CAUSE_UNKNOWN)
        status = "failure_classified"
        confidence = "inferred" if observation.get("maskedBy") else (
            "exact" if observation.get("definitive") else "unknown"
        )
        evidence = {
            "source": str(observation.get("source") or "none"),
            "httpStatus": observation.get("httpStatus") if isinstance(observation.get("httpStatus"), int) else None,
            "signal": str(observation.get("signal") or "none"),
            "observedAt": observation.get("observedAt") if isinstance(observation.get("observedAt"), str) else None,
            "retryAt": observation.get("retryAt") if isinstance(observation.get("retryAt"), str) else None,
            "maskedBy": observation.get("maskedBy") if observation.get("maskedBy") == CAUSE_NO_USABLE_ACCOUNTS else None,
        }
    else:
        cause = _gateway_cause(gateway)
        status = "no_recent_failure" if cause == "none" else "gateway_failure"
        confidence = "unknown" if cause == "none" else "exact"
        evidence = {
            "source": "gateway_probe",
            "httpStatus": gateway.get("httpStatus") if isinstance(gateway.get("httpStatus"), int) else None,
            "signal": "none",
            "observedAt": iso_utc(utc_now()),
            "retryAt": None,
            "maskedBy": None,
        }
    return {
        "schema": SCHEMA,
        "target": target,
        "status": status,
        "cause": cause,
        "confidence": confidence,
        "gateway": gateway,
        "evidence": evidence,
    }


def diagnose_local(config: LocalConfig, account: str) -> Dict[str, Any]:
    key, port = _profile_key_and_port(config, account)
    gateway = _gateway(probe_endpoint(config, port, key)) if key else {
        "state": "authentication_failed",
        "httpStatus": None,
    }
    return _diagnosis("local_api", gateway, recent_local_observation(config))


def diagnose_cloud(config: LocalConfig) -> Dict[str, Any]:
    broker = BrokerClient(config)
    status_document = broker.status()
    observation = status_document.get("lastApiFailure")
    if not isinstance(observation, dict):
        observation = None
    status: Optional[int] = None
    try:
        endpoint = RemoteClient(config).resolve_endpoint()
        with broker.acquire(config.ssh_host, endpoint.forward_host, endpoint.forward_port) as lease:
            status = probe_endpoint(config, lease.port, endpoint.api_key)
            refreshed = broker.status().get("lastApiFailure")
            if observation is None and isinstance(refreshed, dict):
                observation = refreshed
    except (OSError, RuntimeError, ValueError):
        status = None
    return _diagnosis("cloud_gateway", _gateway(status), observation)


def render(document: Dict[str, Any], stream: Any = None) -> None:
    target_stream = stream if stream is not None else sys.stdout
    cause = str(document.get("cause") or CAUSE_UNKNOWN)
    evidence = document.get("evidence") if isinstance(document.get("evidence"), dict) else {}
    gateway = document.get("gateway") if isinstance(document.get("gateway"), dict) else {}
    target = "local API" if document.get("target") == "local_api" else "cloud gateway"
    result = {
        "failure_classified": "failure classified",
        "gateway_failure": "gateway failure classified",
        "no_recent_failure": "no recent failure evidence",
    }.get(str(document.get("status") or ""), "unknown")
    print("API diagnosis", file=target_stream)
    print("  Target: %s" % target, file=target_stream)
    print("  Result: %s" % result, file=target_stream)
    print("  Cause: %s" % CAUSE_LABELS.get(cause, "undetermined"), file=target_stream)
    print("  Confidence: %s" % document.get("confidence", "unknown"), file=target_stream)
    gateway_status = str(gateway.get("state") or "unknown").replace("_", " ")
    if isinstance(gateway.get("httpStatus"), int):
        gateway_status += " (HTTP %d)" % gateway["httpStatus"]
    print("  Gateway: %s" % gateway_status, file=target_stream)
    if evidence.get("signal") not in (None, "none"):
        signal = str(evidence.get("signal"))
        if isinstance(evidence.get("httpStatus"), int) and evidence["httpStatus"] >= 400:
            signal += " (HTTP %d)" % evidence["httpStatus"]
        print("  Upstream signal: %s" % signal, file=target_stream)
    if evidence.get("maskedBy") == CAUSE_NO_USABLE_ACCOUNTS:
        print("  Later response: no usable accounts (the earlier definitive cause was retained)", file=target_stream)
    if evidence.get("observedAt"):
        print("  Observed: %s" % evidence["observedAt"], file=target_stream)
    if evidence.get("retryAt"):
        print("  Retry after: %s" % evidence["retryAt"], file=target_stream)
    print("  Meaning: %s" % MEANINGS.get(cause, MEANINGS[CAUSE_UNKNOWN]), file=target_stream)
    print("  Next step: %s" % NEXT_STEPS.get(cause, NEXT_STEPS[CAUSE_UNKNOWN]), file=target_stream)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="codexx diagnose")
    root.add_argument("target", nargs="?", choices=("api", "cpa", "cloud"))
    root.add_argument("--json", action="store_true", help="print cloudx.api-diagnosis.v1 JSON")
    return root


def run(
    config: LocalConfig,
    arguments: Sequence[str],
    *,
    forced_target: Optional[str] = None,
) -> int:
    args = parser().parse_args(list(arguments))
    if forced_target and args.target:
        raise RuntimeError("%s diagnose does not accept another target" % forced_target)
    target = forced_target or args.target
    if not target:
        mode = os.environ.get("CLOUDX_MODE", "").strip()
        active = os.environ.get("CODEXX_ACTIVE_ACCOUNT", "").strip()
        if mode == "cloud" or active == "cloud":
            target = "cloud"
        elif mode == "api" or active in {"api", "cpa"}:
            target = active if active in {"api", "cpa"} else "api"
        else:
            raise RuntimeError("diagnose requires an active api/cloud mode or an explicit api, cpa, or cloud target")
    document = diagnose_cloud(config) if target == "cloud" else diagnose_local(config, target)
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        render(document)
    return 0
