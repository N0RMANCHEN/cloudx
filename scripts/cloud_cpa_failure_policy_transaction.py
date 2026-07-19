#!/usr/bin/env python3
"""Accept the cloud CPA failure policy with a rollback-bounded live transaction."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import http.client
import json
import os
import pathlib
import pwd
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

ACTIVE_VERSION = "0.1.18"
CONFIRMATION = "ACCEPT CLOUD CPA FAILURE POLICY 0.1.18"
PLAN_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance-plan.v1"
RESULT_SCHEMA = "cloudx.cloud-cpa-failure-policy-acceptance.v1"
ACTIVE_ARTIFACT = pathlib.Path("/opt/cloudx/current/cloudx-cloud.pyz")
AUTH_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth")
ARCHIVE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-archive")
FAILURE_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-failures")
SWEEP_DIR = pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-sweeps")
STATE_DIR = pathlib.Path("/var/lib/cloudx/cpa-health")
TRANSACTION_ROOT = pathlib.Path("/var/lib/codex-gateway/cpa-policy-acceptance")
CLIENT_CREDENTIAL = pathlib.Path("/etc/cloudx/client-credential")
CPA_SERVICE = "cliproxy.service"
HEALTH_SERVICE = "cloudx-cpa-health.service"
FAILURE_PATH = "cloudx-cpa-failure.path"
SWEEP_PATH = "cloudx-cpa-sweep.path"
PROXY_URL = "http://127.0.0.1:7890"
GATEWAY_HOST = "100.90.97.113"
GATEWAY_PORT = 8317
EXPECTED_TEXT = "CLOUDX_CPA_POLICY_RECOVERY_OK"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
CANARY_PREFIX = "cloudx-m4b-limited-"

class AcceptanceRejected(RuntimeError):
    def __init__(self, code: str, message: str, *, transaction_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.transaction_id = transaction_id
def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
def _safe_bytes(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise AcceptanceRejected("unsafe_file", "required private file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise AcceptanceRejected("unsafe_file", "required private file is unsafe")
        chunks: List[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw or len(raw) > maximum:
            raise AcceptanceRejected("unsafe_file", "required private file is empty or oversized")
        return raw
    finally:
        os.close(descriptor)
def _sha256(path: pathlib.Path) -> str:
    return _sha256_bytes(_safe_bytes(path))
def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
def _atomic_bytes(
    path: pathlib.Path,
    raw: bytes,
    *,
    mode: int = 0o600,
    uid: Optional[int] = None,
    gid: Optional[int] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        if uid is not None and gid is not None:
            os.chown(temporary, uid, gid)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
def _atomic_json(path: pathlib.Path, document: Mapping[str, Any]) -> None:
    raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_bytes(path, raw)
def _json_file(path: pathlib.Path, maximum: int = MAX_FILE_BYTES) -> Dict[str, Any]:
    try:
        value = json.loads(_safe_bytes(path, maximum).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("invalid_json", "private state contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise AcceptanceRejected("invalid_json", "private state is not a JSON object")
    return value
def _run(
    argv: Sequence[str],
    *,
    input_bytes: Optional[bytes] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = 180.0,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(argv),
            input=input_bytes,
            stdin=None if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env) if env is not None else None,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceRejected("command_failed", "acceptance command failed") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise AcceptanceRejected("output_oversized", "acceptance command output exceeded the limit")
    if check and completed.returncode != 0:
        raise AcceptanceRejected("command_failed", "acceptance command returned nonzero")
    return completed
def _output_json(raw: bytes, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("invalid_output", "%s returned invalid JSON" % label) from exc
    if not isinstance(value, dict):
        raise AcceptanceRejected("invalid_output", "%s returned an invalid document" % label)
    return value
def _regular_files(root: pathlib.Path, suffix: str = "") -> List[pathlib.Path]:
    try:
        info = root.lstat()
    except OSError as exc:
        raise AcceptanceRejected("unsafe_directory", "required private directory is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise AcceptanceRejected("unsafe_directory", "required private directory is unsafe")
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink() and (not suffix or path.name.endswith(suffix))
    )
def _service_state(name: str) -> Dict[str, Any]:
    fields = ("MainPID", "NRestarts", "ActiveState", "SubState")
    values: Dict[str, Any] = {}
    for field in fields:
        raw = _run(["systemctl", "show", name, "-p", field, "--value"], timeout=30).stdout
        text = raw.decode("utf-8", errors="replace").strip()
        values[field] = int(text or "0") if field in {"MainPID", "NRestarts"} else text
    return values
def _unit_ready(name: str) -> bool:
    enabled = _run(["systemctl", "is-enabled", name], timeout=30, check=False).returncode == 0
    active = _run(["systemctl", "is-active", name], timeout=30, check=False).returncode == 0
    return enabled and active
def _active_version() -> str:
    current = pathlib.Path("/opt/cloudx/current")
    if not current.is_symlink():
        return ""
    try:
        return current.resolve(strict=True).name
    except OSError:
        return ""
def _archive_count(root: Optional[pathlib.Path] = None) -> int:
    manifest = _json_file((root or ARCHIVE_DIR) / "manifest.json")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise AcceptanceRejected("archive_invalid", "CPA archive manifest is invalid")
    return len(entries)
def _client_credential() -> str:
    value = _safe_bytes(CLIENT_CREDENTIAL, 4096).decode("utf-8", errors="strict").strip()
    if not value:
        raise AcceptanceRejected("gateway_credential", "gateway client credential is unavailable")
    return value
def _request(method: str, path: str, body: Optional[Dict[str, Any]], *, timeout: float = 180) -> Tuple[int, Dict[str, str], bytes]:
    connection = http.client.HTTPConnection(GATEWAY_HOST, GATEWAY_PORT, timeout=timeout)
    headers = {"Authorization": "Bearer %s" % _client_credential()}
    raw = None
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_OUTPUT_BYTES + 1)
        if len(data) > MAX_OUTPUT_BYTES:
            raise AcceptanceRejected("gateway_output", "gateway response exceeded the limit")
        return response.status, {key.lower(): value for key, value in response.getheaders()}, data
    except (OSError, http.client.HTTPException) as exc:
        raise AcceptanceRejected("gateway_unavailable", "gateway request failed") from exc
    finally:
        connection.close()
def _models() -> List[str]:
    status, unused_headers, raw = _request("GET", "/v1/models", None, timeout=15)
    if status != 200:
        raise AcceptanceRejected("models_unavailable", "gateway model list is unavailable")
    document = _output_json(raw, "gateway model list")
    data = document.get("data")
    models = [
        str(item.get("id"))
        for item in data
        if isinstance(data, list) and isinstance(item, dict) and isinstance(item.get("id"), str)
    ] if isinstance(data, list) else []
    priority = ("codex-auto-review", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.1-codex")
    ordered = [item for item in priority if item in models]
    ordered.extend(item for item in models if "codex" in item.lower() and item not in ordered)
    return ordered or models[:8]
def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
def _live_canary() -> Dict[str, Any]:
    attempts = 0
    for model in _models()[:8]:
        for retry in range(3):
            attempts += 1
            status, headers, raw = _request(
                "POST",
                "/v1/responses",
                {
                    "model": model,
                    "input": "Reply with exactly %s" % EXPECTED_TEXT,
                    "max_output_tokens": 64,
                    "stream": False,
                },
            )
            accepted = False
            if status == 200:
                try:
                    accepted = EXPECTED_TEXT in "\n".join(_strings(json.loads(raw.decode("utf-8"))))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    accepted = False
            policy = headers.get("x-cpa-max-concurrent-api-requests", "")
            if accepted and policy == "2":
                return {"status": 200, "policy": 2, "attempts": attempts, "model": model}
            if status in {400, 409, 429, 500, 502, 503, 504} and retry < 2:
                time.sleep(2)
                continue
            break
    raise AcceptanceRejected("live_canary_failed", "real gateway recovery canary failed")
def _signed_health(arguments: Sequence[str]) -> Dict[str, Any]:
    env = dict(os.environ)
    env["CLOUDX_CPA_PROXY_URL"] = PROXY_URL
    env["CLOUDX_CPA_SWEEP_CONCURRENCY"] = "32"
    completed = _run([sys.executable, str(ACTIVE_ARTIFACT), *arguments], env=env, timeout=180)
    return _output_json(completed.stdout, "signed Cloudx CPA command")
def _self_check() -> None:
    document = _signed_health(["self-check"])
    if document.get("status") != "ok" or document.get("version") != ACTIVE_VERSION:
        raise AcceptanceRejected("release_mismatch", "active signed Cloudx release self-check failed")

@contextmanager
def _transaction_lock() -> Iterator[None]:
    TRANSACTION_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(TRANSACTION_ROOT, 0, 0)
    TRANSACTION_ROOT.chmod(0o700)
    descriptors = []
    try:
        for lock_path in (TRANSACTION_ROOT / ".acceptance.lock", AUTH_DIR / ".cloudx-import.lock"):
            descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            descriptors.append(descriptor)
        yield
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
def _quota_samples(raw: bytes) -> List[bytes]:
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise AcceptanceRejected("quota_samples", "quota sample input is empty or oversized")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRejected("quota_samples", "quota sample input is invalid") from exc
    if not isinstance(document, dict) or set(document) != {"schema", "samples"} or document.get("schema") != "cloudx.cpa-quota-samples.v1":
        raise AcceptanceRejected("quota_samples", "quota sample contract is invalid")
    encoded = document.get("samples")
    if not isinstance(encoded, list) or len(encoded) != 3 or any(not isinstance(item, str) for item in encoded):
        raise AcceptanceRejected("quota_samples", "exactly three quota samples are required")
    samples: List[bytes] = []
    for item in encoded:
        try:
            value = base64.b64decode(item.encode("ascii"), validate=True)
            payload = json.loads(value.decode("utf-8"))
        except (ValueError, UnicodeEncodeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceRejected("quota_samples", "quota sample is invalid") from exc
        if not value or len(value) > MAX_FILE_BYTES or not isinstance(payload, dict):
            raise AcceptanceRejected("quota_samples", "quota sample is empty, oversized, or not an object")
        samples.append(value)
    if len({_sha256_bytes(item) for item in samples}) != 3:
        raise AcceptanceRejected("quota_samples", "quota samples must be distinct")
    return samples
def _preflight() -> Dict[str, Any]:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise AcceptanceRejected("wrong_host", "cloud CPA acceptance requires root on Linux")
    if _active_version() != ACTIVE_VERSION:
        raise AcceptanceRejected("release_mismatch", "signed Cloudx 0.1.18 is not active")
    _self_check()
    if not _unit_ready(FAILURE_PATH) or not _unit_ready(SWEEP_PATH):
        raise AcceptanceRejected("watcher_unavailable", "cloud CPA failure and sweep watchers must be active")
    service = _service_state(CPA_SERVICE)
    if service["ActiveState"] != "active" or service["SubState"] != "running" or service["MainPID"] <= 0:
        raise AcceptanceRejected("cpa_unavailable", "cloud CPA baseline is not healthy")
    active = _regular_files(AUTH_DIR, ".json")
    if len(active) != 1:
        raise AcceptanceRejected("active_pool", "cloud CPA acceptance requires exactly one active baseline credential")
    if _regular_files(FAILURE_DIR, ".json"):
        raise AcceptanceRejected("watcher_input", "failure receipt input must be empty before acceptance")
    if any(path.name == "trigger.json" for path in _regular_files(SWEEP_DIR)):
        raise AcceptanceRejected("watcher_input", "sweep trigger must be absent before acceptance")
    if _archive_count() != 45:
        raise AcceptanceRejected("archive_baseline", "expected 45 retained deactivated archive entries")
    cliproxy = pwd.getpwnam("cliproxy")
    info = active[0].stat()
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != cliproxy.pw_uid or info.st_gid != cliproxy.pw_gid:
        raise AcceptanceRejected("active_pool", "active baseline credential ownership or mode is unsafe")
    before_canary = _live_canary()
    if _regular_files(FAILURE_DIR, ".json"):
        raise AcceptanceRejected("watcher_input", "baseline canary emitted a failure receipt")
    sweep = _regular_files(SWEEP_DIR)
    if any(path.name == "trigger.json" for path in sweep):
        raise AcceptanceRejected("watcher_input", "baseline canary emitted an unavailable trigger")
    state_path = STATE_DIR / "state.json"
    return {
        "service": service,
        "activeName": active[0].name,
        "activeDigest": _sha256(active[0]),
        "sweep": {path.name: _sha256(path) for path in sweep},
        "stateDigest": _sha256(state_path) if state_path.is_file() else "",
        "archiveCount": 45,
        "beforeCanary": before_canary,
    }
def _prepare_transaction(baseline: Dict[str, Any], quota_samples: Sequence[bytes]) -> pathlib.Path:
    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    transaction = TRANSACTION_ROOT / transaction_id
    transaction.mkdir(mode=0o700)
    os.chown(transaction, 0, 0)
    for name in ("hold/active", "hold/sweep", "staged", "evidence"):
        path = transaction / name
        path.mkdir(parents=True, mode=0o700)
        os.chown(path, 0, 0)
    try:
        recovery = transaction / "recover.py"
        _atomic_bytes(recovery, _safe_bytes(pathlib.Path(__file__), 1024 * 1024), mode=0o700)
        cliproxy = pwd.getpwnam("cliproxy")
        canaries: Dict[str, str] = {}
        for index, raw in enumerate(quota_samples, start=1):
            name = "%s%d.json" % (CANARY_PREFIX, index)
            _atomic_bytes(transaction / "staged" / name, raw)
            canaries[name] = _sha256_bytes(raw)
        manifest = {
        "schema": RESULT_SCHEMA,
        "transactionId": transaction_id,
        "phase": "prepared",
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "activeName": baseline["activeName"],
        "activeDigest": baseline["activeDigest"],
        "sweep": baseline["sweep"],
        "stateDigest": baseline["stateDigest"],
        "canaries": canaries,
        "archiveCount": baseline["archiveCount"],
        "service": baseline["service"],
        "cliproxyUid": cliproxy.pw_uid,
        "cliproxyGid": cliproxy.pw_gid,
        "recoveryToolSha256": _sha256(recovery),
        "rawCredentialTemporarilyStored": True,
        }
        _atomic_json(transaction / "manifest.json", manifest)
        recovery_confirmation = "RECOVER CLOUD CPA FAILURE POLICY %s" % transaction_id
        manual = (
        "Cloud CPA failure-policy acceptance recovery\n\n"
        "Run exactly:\n"
        "sudo /usr/bin/python3 %s --recover --transaction %s --confirm %s\n"
        "The command restores the held active credential, removes only transaction canaries, "
        "restores watcher input, and performs a real gateway canary.\n"
        ) % (recovery, transaction, json.dumps(recovery_confirmation))
        _atomic_bytes(transaction / "RECOVERY.md", manual.encode("utf-8"))
        rehearsal = _run([sys.executable, str(recovery), "--self-test"], timeout=30)
        rehearsal_document = _output_json(rehearsal.stdout, "recovery self-test")
        if rehearsal_document.get("status") != "passed":
            raise AcceptanceRejected("recovery_rehearsal", "independent recovery tool rehearsal failed", transaction_id=transaction_id)
        _atomic_json(transaction / "evidence/recovery-rehearsal.json", rehearsal_document)
        return transaction
    except Exception:
        shutil.rmtree(transaction, ignore_errors=True)
        raise
def _synthetic_token() -> str:
    def encoded(value: Mapping[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return "%s.%s.%s" % (
        encoded({"alg": "none", "typ": "JWT"}),
        encoded({"exp": int(time.time()) + 3600, "nonce": secrets.token_hex(8)}),
        secrets.token_urlsafe(8),
    )
def _write_trigger(path: pathlib.Path) -> None:
    _atomic_json(path, {
        "schema": "cloudx.cpa-sweep-trigger.v1",
        "reason": "auth_unavailable",
        "observedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
def _isolated_sweep(transaction: pathlib.Path, kind: str, source: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    classification = "quota" if kind.startswith("quota-") else kind
    root = transaction / "isolated" / kind
    auth = root / "auth"
    archive = root / "archive"
    failure = root / "failure"
    sweep = root / "sweep"
    state = root / "state"
    for path in (auth, archive, failure, sweep, state):
        path.mkdir(parents=True, mode=0o700)
    name = "%s-canary.json" % kind
    if source is not None:
        raw = _safe_bytes(source)
    else:
        payload: Dict[str, Any] = {"type": "codex", "access_token": _synthetic_token(), "disabled": False}
        if classification == "provisional":
            payload["refresh_token"] = "cloudx-refreshable-401-canary"
        raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    _atomic_bytes(auth / name, raw)
    original_digest = _sha256(auth / name)
    _write_trigger(sweep / "trigger.json")
    document = _signed_health([
        "cpa-health", "--sweep-if-triggered",
        "--auth-dir", str(auth), "--archive-dir", str(archive),
        "--failure-dir", str(failure), "--sweep-dir", str(sweep),
        "--state-dir", str(state), "--proxy-url", PROXY_URL,
        "--probe-concurrency", "8", "--failure-confirmations", "1",
    ])
    common = (
        document.get("probe_gate") == "reachable"
        and document.get("sweep_triggered") is True
        and document.get("sweep_trigger_status") == "consumed"
        and document.get("probe_concurrency") == 1
    )
    if not common:
        raise AcceptanceRejected("isolated_sweep", "%s isolated sweep did not run as required" % kind)
    result: Dict[str, Any] = {"kind": kind, "probeConcurrency": 1, "networkProbe": True}
    if classification == "quota":
        if document.get("limited") != 1 or document.get("archived_count") != 0 or not (auth / name).is_file():
            raise AcceptanceRejected("quota_archived", "real weekly quota evidence changed archive state")
        result.update({"limited": 1, "archived": 0})
    elif classification == "provisional":
        if document.get("archived_count") != 0 or not (auth / name).is_file() or _sha256(auth / name) != original_digest:
            raise AcceptanceRejected("provisional_archived", "refreshable 401 evidence changed archive state")
        result.update({"provisional401": True, "archived": 0})
    else:
        if document.get("invalid") != 1 or document.get("probe_failure_archived_count") != 1 or (auth / name).exists():
            raise AcceptanceRejected("permanent_not_archived", "permanent 401 did not archive exactly one credential")
        manifest = _json_file(archive / "manifest.json")
        entries = manifest.get("entries")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            raise AcceptanceRejected("permanent_manifest", "permanent archive manifest is invalid")
        selector = str(entries[0].get("quarantine_name") or "")
        restored = _signed_health([
            "cpa-health-restore", selector, "--confirm", selector,
            "--auth-dir", str(auth), "--archive-dir", str(archive),
        ])
        if restored.get("status") != "restored" or restored.get("restored_count") != 1:
            raise AcceptanceRejected("restore_failed", "exact permanent credential restore failed")
        if _sha256(auth / name) != original_digest or _archive_count(archive) != 0:
            raise AcceptanceRejected("restore_mismatch", "restored permanent credential did not match its digest")
        result.update({"permanentArchived": 1, "digestMatched": True, "restored": 1})
    _atomic_json(transaction / "evidence" / (kind + ".json"), result)
    shutil.rmtree(root)
    return result
def _activate_limited(transaction: pathlib.Path) -> None:
    manifest = _json_file(transaction / "manifest.json")
    active_name = str(manifest["activeName"])
    active = AUTH_DIR / active_name
    if _sha256(active) != manifest["activeDigest"]:
        raise AcceptanceRejected("baseline_changed", "active credential changed before the transaction", transaction_id=transaction.name)
    current_sweep = {path.name: _sha256(path) for path in _regular_files(SWEEP_DIR)}
    if current_sweep != manifest["sweep"]:
        raise AcceptanceRejected("baseline_changed", "watcher input changed before the transaction", transaction_id=transaction.name)
    os.replace(active, transaction / "hold/active" / active_name)
    for name in manifest["sweep"]:
        os.replace(SWEEP_DIR / name, transaction / "hold/sweep" / name)
    cliproxy_uid = int(manifest["cliproxyUid"])
    cliproxy_gid = int(manifest["cliproxyGid"])
    for name, digest in manifest["canaries"].items():
        staged = transaction / "staged" / name
        if _sha256(staged) != digest:
            raise AcceptanceRejected("staged_changed", "staged quota credential changed", transaction_id=transaction.name)
        _atomic_bytes(AUTH_DIR / name, _safe_bytes(staged), uid=cliproxy_uid, gid=cliproxy_gid)
    _fsync_directory(AUTH_DIR)
    manifest["phase"] = "limited-active"
    _atomic_json(transaction / "manifest.json", manifest)
    time.sleep(4)
def _natural_aggregate(transaction: pathlib.Path) -> Dict[str, Any]:
    manifest = _json_file(transaction / "manifest.json")
    models = _models()
    if not models:
        raise AcceptanceRejected("models_unavailable", "gateway exposed no model for aggregate acceptance")
    started = time.monotonic()
    aggregate_signal = False
    attempts = 0
    statuses: List[int] = []
    for _unused in range(16):
        attempts += 1
        status, headers, raw = _request(
            "POST", "/v1/responses",
            {"model": models[0], "input": "Return one word.", "max_output_tokens": 16, "stream": False},
            timeout=60,
        )
        statuses.append(status)
        if headers.get("x-cpa-max-concurrent-api-requests") != "2":
            raise AcceptanceRejected("policy_mismatch", "business policy header changed", transaction_id=transaction.name)
        lowered = raw[:65536].lower()
        aggregate_signal = aggregate_signal or b"auth_unavailable" in lowered or b"no auth available" in lowered
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state_path = STATE_DIR / "state.json"
            if state_path.is_file():
                state = _json_file(state_path)
                if (
                    _sha256(state_path) != str(manifest.get("stateDigest") or "")
                    and
                    state.get("sweep_triggered") is True
                    and state.get("sweep_trigger_status") == "consumed"
                    and state.get("probe_gate") == "reachable"
                    and isinstance(state.get("probe_concurrency"), int)
                    and int(state["probe_concurrency"]) >= 3
                    and int(state.get("limited") or 0) >= 3
                    and int(state.get("archived_count") or 0) == 0
                    and int(state.get("probe_failure_archived_count") or 0) == 0
                    and int(state.get("runtime_failure_archived_count") or 0) == 0
                ):
                    if _archive_count() != 45 or _regular_files(FAILURE_DIR, ".json"):
                        raise AcceptanceRejected("archive_changed", "quota sweep changed permanent archive state", transaction_id=transaction.name)
                    result = {
                        "aggregateSignalObserved": aggregate_signal,
                        "businessPolicy": 2,
                        "businessAttempts": attempts,
                        "httpStatuses": sorted(set(statuses)),
                        "sweepProbeConcurrency": int(state["probe_concurrency"]),
                        "limited": int(state.get("limited") or 0),
                        "archived": 0,
                        "triggerStatus": "consumed",
                        "elapsedSeconds": round(time.monotonic() - started, 3),
                    }
                    _atomic_json(transaction / "evidence/natural-aggregate.json", result)
                    return result
            time.sleep(0.2)
        time.sleep(0.5)
    raise AcceptanceRejected("aggregate_not_triggered", "natural aggregate unavailable trigger was not accepted", transaction_id=transaction.name)
def _restore_archived_canaries(transaction: pathlib.Path, names: Sequence[str]) -> None:
    manifest = _json_file(ARCHIVE_DIR / "manifest.json")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise AcceptanceRejected("archive_invalid", "production archive manifest is invalid", transaction_id=transaction.name)
    selectors = [
        str(entry.get("quarantine_name") or "")
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("source_relative") or "") in names
    ]
    for selector in selectors:
        restored = _signed_health([
            "cpa-health-restore", selector, "--confirm", selector,
            "--auth-dir", str(AUTH_DIR), "--archive-dir", str(ARCHIVE_DIR),
        ])
        if restored.get("status") != "restored":
            raise AcceptanceRejected("canary_restore_failed", "archived quota canary could not be restored", transaction_id=transaction.name)
def _recover(transaction: pathlib.Path, *, verify: bool = True) -> Dict[str, Any]:
    manifest = _json_file(transaction / "manifest.json")
    if manifest.get("phase") == "recovered":
        active = _regular_files(AUTH_DIR, ".json")
        service = _service_state(CPA_SERVICE)
        if (
            len(active) != 1
            or active[0].name != str(manifest["activeName"])
            or service != manifest["service"]
            or _archive_count() != int(manifest["archiveCount"])
        ):
            raise AcceptanceRejected("recovery_incomplete", "previous recovery no longer matches baseline", transaction_id=transaction.name)
        return {"activeRestored": True, "serviceUnchanged": True, "archiveRestored": True, "alreadyRecovered": True}
    names = sorted(str(name) for name in manifest.get("canaries", {}))
    _restore_archived_canaries(transaction, names)
    for name in names:
        path = AUTH_DIR / name
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise AcceptanceRejected("recovery_unsafe", "quota canary path is unsafe", transaction_id=transaction.name)
            path.unlink()
    for receipt in _regular_files(FAILURE_DIR, ".json"):
        try:
            document = _json_file(receipt, 16 * 1024)
        except AcceptanceRejected:
            continue
        if str(document.get("authFile") or "") in names:
            os.replace(receipt, transaction / "evidence" / ("failure-" + receipt.name))
    sweep_baseline = manifest.get("sweep") if isinstance(manifest.get("sweep"), dict) else {}
    for path in _regular_files(SWEEP_DIR):
        expected = str(sweep_baseline.get(path.name) or "")
        if not expected or _sha256(path) != expected:
            target = transaction / "evidence" / ("post-sweep-" + path.name)
            target.unlink(missing_ok=True)
            os.replace(path, target)
    for name, digest in sweep_baseline.items():
        target = SWEEP_DIR / name
        held = transaction / "hold/sweep" / name
        if target.exists() and _sha256(target) == digest:
            held.unlink(missing_ok=True)
        elif held.exists() and _sha256(held) == digest:
            os.replace(held, target)
        else:
            raise AcceptanceRejected("recovery_incomplete", "watcher baseline could not be restored", transaction_id=transaction.name)
    active_name = str(manifest["activeName"])
    active_digest = str(manifest["activeDigest"])
    target = AUTH_DIR / active_name
    held = transaction / "hold/active" / active_name
    if target.exists() and _sha256(target) == active_digest:
        held.unlink(missing_ok=True)
    elif held.exists() and _sha256(held) == active_digest and not target.exists():
        os.replace(held, target)
        os.chmod(target, 0o600)
        os.chown(target, int(manifest["cliproxyUid"]), int(manifest["cliproxyGid"]))
    else:
        raise AcceptanceRejected("recovery_incomplete", "active baseline credential could not be restored", transaction_id=transaction.name)
    _fsync_directory(AUTH_DIR)
    _fsync_directory(SWEEP_DIR)
    shutil.rmtree(transaction / "staged", ignore_errors=True)
    shutil.rmtree(transaction / "isolated", ignore_errors=True)
    time.sleep(4)
    canary = _live_canary() if verify else {"status": "skipped"}
    service = _service_state(CPA_SERVICE)
    active = _regular_files(AUTH_DIR, ".json")
    if service != manifest["service"] or len(active) != 1 or active[0].name != active_name:
        raise AcceptanceRejected("recovery_incomplete", "CPA service or active pool did not return to baseline", transaction_id=transaction.name)
    if _archive_count() != int(manifest["archiveCount"]):
        raise AcceptanceRejected("recovery_incomplete", "production archive did not return to baseline", transaction_id=transaction.name)
    if _regular_files(FAILURE_DIR, ".json"):
        raise AcceptanceRejected("recovery_incomplete", "transaction failure receipts remain active", transaction_id=transaction.name)
    manifest["phase"] = "recovered"
    manifest["rawCredentialTemporarilyStored"] = False
    manifest["recoveredAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _atomic_json(transaction / "manifest.json", manifest)
    result = {"activeRestored": True, "serviceUnchanged": True, "archiveRestored": True, "liveCanary": canary}
    _atomic_json(transaction / "evidence/recovery.json", result)
    return result
def _idle_acceptance(transaction: pathlib.Path) -> Dict[str, Any]:
    before = _service_state(CPA_SERVICE)
    _run(["systemctl", "start", HEALTH_SERVICE], timeout=90)
    state = _json_file(STATE_DIR / "state.json")
    if (
        state.get("probe_gate") != "not_triggered"
        or state.get("probe_concurrency") != 0
        or state.get("sweep_triggered") is not False
        or state.get("sweep_trigger_status") != "absent"
        or _service_state(CPA_SERVICE) != before
    ):
        raise AcceptanceRejected("idle_probe", "idle maintenance performed an unsolicited probe", transaction_id=transaction.name)
    result = {"probeGate": "not_triggered", "probeConcurrency": 0, "trigger": "absent", "cpaServiceUnchanged": True}
    _atomic_json(transaction / "evidence/idle.json", result)
    return result
def _remote_apply(quota_samples: Sequence[bytes]) -> Dict[str, Any]:
    with _transaction_lock():
        baseline = _preflight()
        transaction = _prepare_transaction(baseline, quota_samples)
        recovered: Optional[Dict[str, Any]] = None
        try:
            quota_checks = [
                _isolated_sweep(transaction, "quota-%d" % index, transaction / "staged" / (CANARY_PREFIX + "%d.json" % index))
                for index in range(1, 4)
            ]
            quota = {"sampleCount": 3, "limited": sum(int(item["limited"]) for item in quota_checks), "archived": 0}
            provisional = _isolated_sweep(transaction, "provisional")
            permanent = _isolated_sweep(transaction, "permanent")
            _activate_limited(transaction)
            aggregate = _natural_aggregate(transaction)
            recovered = _recover(transaction)
            idle = _idle_acceptance(transaction)
            receipt = {
                "schema": RESULT_SCHEMA,
                "status": "accepted",
                "transactionId": transaction.name,
                "businessPolicy": 2,
                "quotaSampleCount": 3,
                "realQuota": quota,
                "provisional": provisional,
                "permanent": permanent,
                "aggregate": aggregate,
                "recovery": recovered,
                "idle": idle,
                "cpaPid": baseline["service"]["MainPID"],
                "cpaRestarts": baseline["service"]["NRestarts"],
                "serviceRestarted": False,
                "rawCredentialStored": False,
            }
            _atomic_json(transaction / "receipt.json", receipt)
            return receipt
        except Exception as exc:
            if recovered is None:
                try:
                    recovered = _recover(transaction)
                except Exception as recovery_exc:
                    raise AcceptanceRejected(
                        "recovery_incomplete",
                        "cloud CPA acceptance failed and manual recovery is required",
                        transaction_id=transaction.name,
                    ) from recovery_exc
            code = exc.code if isinstance(exc, AcceptanceRejected) else "acceptance_failed"
            _atomic_json(transaction / "receipt.json", {
                "schema": RESULT_SCHEMA,
                "status": "failed-recovered",
                "transactionId": transaction.name,
                "failureCode": code,
                "recovery": recovered,
                "serviceRestarted": False,
                "rawCredentialStored": False,
            })
            raise AcceptanceRejected(
                code,
                "cloud CPA acceptance failed and the active baseline was restored",
                transaction_id=transaction.name,
            ) from exc
def _remote_self_test() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as value:
        root = pathlib.Path(value)
        source = root / "held"
        target = root / "active"
        source.write_bytes(b"baseline")
        digest = _sha256(source)
        os.replace(source, target)
        if _sha256(target) != digest or source.exists():
            raise AcceptanceRejected("recovery_rehearsal", "recovery file-move rehearsal failed")
    return {"schema": "cloudx.cloud-cpa-recovery-self-test.v1", "status": "passed"}
def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--self-test", action="store_true")
    root.add_argument("--recover", action="store_true")
    root.add_argument("--transaction", type=pathlib.Path)
    return root
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        print(json.dumps(_remote_self_test(), sort_keys=True))
        return 0
    if args.recover:
        if args.transaction is None or args.confirm != "RECOVER CLOUD CPA FAILURE POLICY %s" % args.transaction.name:
            raise AcceptanceRejected("confirmation_mismatch", "manual recovery confirmation does not match")
        print(json.dumps(_recover(args.transaction), sort_keys=True))
        return 0
    if not args.apply or args.confirm != CONFIRMATION:
        raise AcceptanceRejected("confirmation_mismatch", "cloud CPA acceptance confirmation does not match")
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    print(json.dumps(_remote_apply(_quota_samples(raw)), sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceRejected as exc:
        print(json.dumps({
            "schema": RESULT_SCHEMA,
            "status": "rejected",
            "failureCode": exc.code,
            "transactionId": exc.transaction_id,
            "recoveryRequired": exc.code == "recovery_incomplete",
        }, sort_keys=True))
        raise SystemExit(2)
