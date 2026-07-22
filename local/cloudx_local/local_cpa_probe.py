from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import agent_identity
from .local_cpa_import import _account_id, _auth_tokens, _expand_object


USAGE_ENDPOINT_CHATGPT = "https://chatgpt.com/backend-api/wham/usage"
USAGE_ENDPOINT_CODEXAPI = "https://api.openai.com/api/codex/usage"
MAX_AUTH_FILE_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CONTEXTS = 4096
MAX_CONCURRENCY = 64
DEFAULT_CONCURRENCY = 32
REFRESH_SKEW_SECONDS = 5 * 60
PERMANENT_MARKERS = (
    ("deactivated_workspace", "deactivated_workspace"),
    ("account_deactivated", "account_deactivated"),
    ("account has been deactivated", "account_deactivated"),
    ("account deactivated", "account_deactivated"),
    ("account has been disabled", "account_deactivated"),
    ("account disabled", "account_deactivated"),
    ("account deleted", "account_deactivated"),
    ("refresh_token_reused", "refresh_token_reused"),
    ("refresh token reused", "refresh_token_reused"),
    ("invalid_grant", "refresh_invalid_grant"),
    ("refresh_token_revoked", "refresh_token_revoked"),
    ("refresh token revoked", "refresh_token_revoked"),
    ("token has been revoked", "refresh_token_revoked"),
    ("refresh token is required", "missing_token"),
    ("missing refresh token", "missing_token"),
)
PERMANENT_REASONS = frozenset(reason for unused_marker, reason in PERMANENT_MARKERS)
QUOTA_MARKERS = (
    "weekly limit",
    "weekly quota",
    "usage_limit",
    "usage limit",
    "rate_limit",
    "rate limit",
    "quota",
    "too many requests",
)


@dataclass(frozen=True)
class ProbeContext:
    path: pathlib.Path
    digest: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ProbeCandidate:
    path: pathlib.Path
    digest: str
    reason: str


def _safe_bytes(path: pathlib.Path, maximum: int) -> Optional[bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            return None
        chunks: List[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        return raw if len(raw) <= maximum else None
    except OSError:
        return None
    finally:
        os.close(descriptor)


def contexts(auth_dir: pathlib.Path) -> List[ProbeContext]:
    if not auth_dir.is_dir() or auth_dir.is_symlink():
        return []
    result: List[ProbeContext] = []
    for path in sorted(auth_dir.glob("*.json")):
        raw = _safe_bytes(path, MAX_AUTH_FILE_BYTES)
        if raw is None:
            continue
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        if agent_identity.is_agent_identity(document):
            continue
        try:
            payloads = _expand_object(document, path.name)
        except RuntimeError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        for payload in payloads:
            result.append(ProbeContext(path, digest, payload))
            if len(result) > MAX_CONTEXTS:
                raise RuntimeError("local CPA probe context count exceeds the safety limit")
    return result


def _proxy_opener(proxy_url: str) -> Optional[Callable[..., object]]:
    value = str(proxy_url or "").strip()
    if not value:
        return None
    parsed = urllib.parse.urlsplit(value)
    try:
        unused_port = parsed.port
    except ValueError as exc:
        raise RuntimeError("local CPA probe proxy URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("local CPA probe proxy URL is invalid")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": value, "https": value})
    ).open


def transport_status(
    proxy_url: str,
    *,
    opener: Optional[Callable[..., object]] = None,
) -> str:
    active = opener or _proxy_opener(proxy_url) or urllib.request.urlopen
    request = urllib.request.Request(
        USAGE_ENDPOINT_CHATGPT,
        headers={"Accept": "application/json", "User-Agent": "codex-cli"},
        method="GET",
    )
    try:
        with active(request, timeout=5) as response:  # type: ignore[attr-defined]
            status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "transport_error"
    except Exception:
        return "transport_error"
    return "provider_error" if status == 429 or status >= 500 else "reachable"


def _jwt_expiry(token: str) -> Optional[float]:
    if token.count(".") < 2:
        return None
    try:
        encoded = token.split(".", 2)[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    value = payload.get("exp") if isinstance(payload, dict) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _headers(endpoint: str, payload: Dict[str, Any]) -> Dict[str, str]:
    access_token, unused_refresh, unused_id = _auth_tokens(payload)
    headers = {
        "Authorization": "Bearer %s" % access_token,
        "Accept": "application/json",
        "User-Agent": "codex-cli",
        "OpenAI-Beta": "codex=v1",
    }
    if endpoint.startswith("https://chatgpt.com/"):
        headers.update({"Origin": "https://chatgpt.com", "Referer": "https://chatgpt.com/"})
    account_id = _account_id(payload)
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _body(error: urllib.error.HTTPError) -> bytes:
    try:
        raw = error.read(MAX_RESPONSE_BYTES + 1)
    except Exception:
        return b""
    return raw if isinstance(raw, bytes) and len(raw) <= MAX_RESPONSE_BYTES else b""


def _classified_failure(status: int, raw: bytes, has_refresh: bool) -> Optional[Dict[str, Any]]:
    text = raw.decode("utf-8", "ignore").casefold()
    if status == 429 or any(marker in text for marker in QUOTA_MARKERS):
        return {"status": "limited"}
    for marker, reason in PERMANENT_MARKERS:
        if marker in text:
            return {
                "status": "invalid",
                "reason": reason,
                "permanent": True,
                "weekly_quota": False,
            }
    if status == 401:
        if has_refresh:
            return {"status": "login"}
        return {
            "status": "invalid",
            "reason": "authentication_unauthorized",
            "permanent": True,
            "weekly_quota": False,
        }
    return None


def _rate_limited(rate: object) -> bool:
    if not isinstance(rate, dict):
        return False
    if bool(rate.get("limit_reached")):
        return True
    for value in rate.values():
        if not isinstance(value, dict):
            continue
        remaining = value.get("remaining_percent")
        used = value.get("used_percent", value.get("utilization"))
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining <= 0:
            return True
        if isinstance(used, (int, float)) and not isinstance(used, bool) and used >= 100:
            return True
    return False


def _probe(payload: Dict[str, Any], opener: Callable[..., object]) -> Optional[Dict[str, Any]]:
    access_token, refresh_token, unused_id = _auth_tokens(payload)
    if access_token.count(".") < 2:
        return None
    expiry = _jwt_expiry(access_token)
    if expiry is not None and expiry <= datetime.now(timezone.utc).timestamp() + REFRESH_SKEW_SECONDS:
        if refresh_token:
            return {"status": "login"}
        return {"status": "invalid", "reason": "missing_token", "permanent": True, "weekly_quota": False}
    for endpoint in (USAGE_ENDPOINT_CHATGPT, USAGE_ENDPOINT_CODEXAPI):
        request = urllib.request.Request(endpoint, headers=_headers(endpoint, payload), method="GET")
        try:
            with opener(request, timeout=15) as response:  # type: ignore[attr-defined]
                status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
                raw = response.read(MAX_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
                if len(raw) > MAX_RESPONSE_BYTES:
                    continue
        except urllib.error.HTTPError as exc:
            classified = _classified_failure(int(getattr(exc, "code", 0) or 0), _body(exc), bool(refresh_token))
            if classified is not None:
                return classified
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        except Exception:
            continue
        if status >= 400:
            classified = _classified_failure(status, raw, bool(refresh_token))
            if classified is not None:
                return classified
            continue
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        rate = document.get("rate_limit") if isinstance(document.get("rate_limit"), dict) else document
        return {"status": "limited" if _rate_limited(rate) else "ready"}
    return None


def _probe_key(payload: Dict[str, Any]) -> str:
    access_token, refresh_token, unused_id = _auth_tokens(payload)
    raw = "\0".join((access_token, _account_id(payload), "1" if refresh_token else "0"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def probe_all(
    auth_dir: pathlib.Path,
    proxy_url: str,
    concurrency: int = DEFAULT_CONCURRENCY,
    *,
    opener: Optional[Callable[..., object]] = None,
) -> Tuple[Dict[str, Any], List[ProbeCandidate]]:
    selected = contexts(auth_dir)
    if not selected:
        return {"gate": "no_accounts", "total": 0, "concurrency": 0, "failed": 0}, []
    gate = transport_status(proxy_url, opener=opener)
    if gate != "reachable":
        return {"gate": gate, "total": len(selected), "concurrency": 0, "failed": len(selected)}, []
    active_opener = opener or _proxy_opener(proxy_url) or urllib.request.urlopen
    unique: Dict[str, Dict[str, Any]] = {}
    for context in selected:
        unique.setdefault(_probe_key(context.payload), context.payload)
    limit = min(len(unique), max(1, min(MAX_CONCURRENCY, int(concurrency))))
    with ThreadPoolExecutor(max_workers=limit, thread_name_prefix="cloudx-local-cpa-sweep") as executor:
        results = dict(zip(unique, executor.map(lambda item: _probe(item, active_opener), unique.values())))
    observations = [results[_probe_key(context.payload)] for context in selected]
    statuses = Counter(str((item or {}).get("status") or "unavailable") for item in observations)
    grouped: Dict[pathlib.Path, List[Tuple[Optional[Dict[str, Any]], str]]] = {}
    for context, observation in zip(selected, observations):
        grouped.setdefault(context.path, []).append((observation, context.digest))
    candidates: List[ProbeCandidate] = []
    for path, values in grouped.items():
        reasons = []
        digests = {digest for unused_item, digest in values}
        for item, unused_digest in values:
            if not isinstance(item, dict) or item.get("permanent") is not True or item.get("weekly_quota") is not False:
                reasons = []
                break
            reason = str(item.get("reason") or "")
            if reason not in PERMANENT_REASONS:
                reasons = []
                break
            reasons.append(reason)
        if len(reasons) == len(values) and len(digests) == 1:
            candidates.append(ProbeCandidate(path, next(iter(digests)), sorted(set(reasons))[0]))
    available = statuses["ready"] + statuses["warning"]
    limited = statuses["limited"]
    failed = len(observations) - available - limited
    return {
        "gate": "reachable",
        "total": len(observations),
        "uniqueCredentials": len(unique),
        "concurrency": limit,
        "available": available,
        "limited": limited,
        "invalid": statuses["invalid"],
        "failed": failed,
    }, candidates
