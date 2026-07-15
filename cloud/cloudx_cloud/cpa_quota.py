from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .cpa_auth import auth_account_id, auth_tokens


USAGE_ENDPOINT_CHATGPT = "https://chatgpt.com/backend-api/wham/usage"
USAGE_ENDPOINT_CODEXAPI = "https://api.openai.com/api/codex/usage"
USAGE_METHOD = "http-usage"
WARNING_PERCENT_THRESHOLD = 25
ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 5 * 60
MAX_USAGE_RESPONSE_BYTES = 1024 * 1024


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _decode_jwt_payload(token: object) -> Dict[str, Any]:
    if not isinstance(token, str) or token.count(".") < 2:
        return {}
    try:
        encoded = token.split(".", 2)[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _token_supported(token: object) -> bool:
    return isinstance(token, str) and token.count(".") >= 2


def _token_needs_refresh(token: object, *, now: Optional[datetime] = None) -> bool:
    expires_at = _decode_jwt_payload(token).get("exp")
    if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
        return False
    current = now or _now_utc()
    return float(expires_at) <= current.timestamp() + ACCESS_TOKEN_REFRESH_SKEW_SECONDS


def _percent_or_none(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _clamp_percent(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return min(100, max(0, value))


def _remaining_from_used(used: Optional[int]) -> Optional[int]:
    return None if used is None else _clamp_percent(100 - used)


def _remaining_percent(window: Dict[str, Any]) -> Optional[int]:
    remaining = _percent_or_none(window.get("remaining_percent"))
    if remaining is not None:
        return _clamp_percent(remaining)
    used = _percent_or_none(window.get("used_percent"))
    if used is not None:
        return _remaining_from_used(used)
    utilization = _percent_or_none(window.get("utilization"))
    return _remaining_from_used(utilization)


def _used_percent(window: Dict[str, Any]) -> Optional[int]:
    used = _percent_or_none(window.get("used_percent"))
    if used is not None:
        return _clamp_percent(used)
    utilization = _percent_or_none(window.get("utilization"))
    if utilization is not None:
        return _clamp_percent(utilization)
    remaining = _percent_or_none(window.get("remaining_percent"))
    return _remaining_from_used(remaining)


def _window(rate_limit: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    for key in keys:
        value = rate_limit.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _unavailable_until(window: Dict[str, Any]) -> Optional[str]:
    reset_at = window.get("reset_at")
    if isinstance(reset_at, (int, float)) and not isinstance(reset_at, bool) and reset_at > 0:
        return _iso(datetime.fromtimestamp(float(reset_at), tz=timezone.utc))
    resets_at = window.get("resets_at")
    if isinstance(resets_at, str) and resets_at.strip():
        return resets_at.strip()
    for key in ("reset_after_seconds", "retry_after_seconds"):
        offset = window.get(key)
        if isinstance(offset, (int, float)) and not isinstance(offset, bool) and offset > 0:
            return _iso(datetime.fromtimestamp(_now_utc().timestamp() + float(offset), tz=timezone.utc))
    return None


def _build_probe_success(
    payload: Dict[str, Any],
    started: datetime,
    endpoint: str,
) -> Dict[str, Any]:
    rate_limit = payload.get("rate_limit") if isinstance(payload.get("rate_limit"), dict) else payload
    if not isinstance(rate_limit, dict):
        rate_limit = {}
    primary = _window(rate_limit, "primary_window", "short_window", "five_hour")
    secondary = _window(rate_limit, "secondary_window", "weekly_window", "seven_day")
    primary_remaining = _remaining_percent(primary)
    secondary_remaining = _remaining_percent(secondary)
    primary_used = _used_percent(primary)
    secondary_used = _used_percent(secondary)
    remaining_percents: List[int] = []
    if primary_remaining is not None:
        remaining_percents.append(primary_remaining)
    if secondary_remaining is not None:
        remaining_percents.append(secondary_remaining)

    status_parts: List[str] = []
    if primary_remaining is not None:
        status_parts.append("5h %d%% left" % primary_remaining)
    if secondary_remaining is not None:
        status_parts.append("weekly %d%% left" % secondary_remaining)
    status_line = " · ".join(status_parts) if status_parts else None

    limit_reached = bool(rate_limit.get("limit_reached"))
    reached_type = str(rate_limit.get("rate_limit_reached_type") or "").strip().lower()
    primary_exhausted = primary_remaining is not None and primary_remaining <= 0
    secondary_exhausted = secondary_remaining is not None and secondary_remaining <= 0
    unavailable_until: Optional[str] = None
    warning: Optional[str] = None
    warning_percent: Optional[int] = None
    warning_window: Optional[str] = None
    if limit_reached or primary_exhausted or secondary_exhausted:
        status = "limited"
        if reached_type == "secondary" or (secondary_exhausted and primary_remaining not in {None, 0}):
            unavailable_until = _unavailable_until(secondary) or _unavailable_until(primary)
            warning_window = "7d"
            warning_percent = secondary_remaining
        elif primary_exhausted:
            unavailable_until = _unavailable_until(primary) or _unavailable_until(secondary)
            warning_window = "5h"
            warning_percent = primary_remaining
        else:
            unavailable_until = _unavailable_until(secondary) or _unavailable_until(primary)
            warning_window = "7d"
            warning_percent = secondary_remaining
        warning = status_line
    elif primary_remaining is not None and primary_remaining <= WARNING_PERCENT_THRESHOLD:
        status = "warning"
        warning = status_line
        warning_percent = primary_remaining
        warning_window = "5h"
    elif secondary_remaining is not None and secondary_remaining <= WARNING_PERCENT_THRESHOLD:
        status = "warning"
        warning = status_line
        warning_percent = secondary_remaining
        warning_window = "7d"
    else:
        status = "ready"

    summary_parts: List[str] = []
    if primary_used is not None:
        summary_parts.append("5h used %d%%" % primary_used)
    elif primary_remaining is not None:
        summary_parts.append("5h left %d%%" % primary_remaining)
    if secondary_used is not None:
        summary_parts.append("weekly used %d%%" % secondary_used)
    elif secondary_remaining is not None:
        summary_parts.append("weekly left %d%%" % secondary_remaining)
    summary = " · ".join(summary_parts) if summary_parts else "usage endpoint returned no quota data"
    return {
        "status": status,
        "checked_at": _iso(started),
        "method": USAGE_METHOD,
        "warning": warning,
        "warning_percent": warning_percent,
        "warning_window": warning_window,
        "unavailable_until": unavailable_until,
        "exit_code": 200,
        "summary": summary,
        "status_line": status_line,
        "remaining_percent": primary_remaining,
        "remaining_percents": remaining_percents,
        "quota_checked_at": _iso(started) if remaining_percents else None,
        "endpoint": endpoint,
        "incomplete": not bool(remaining_percents),
    }


def _build_probe_error(
    status: str,
    started: datetime,
    summary: str,
    exit_code: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "status": status,
        "checked_at": _iso(started),
        "method": USAGE_METHOD,
        "warning": None,
        "warning_percent": None,
        "warning_window": None,
        "unavailable_until": None,
        "exit_code": exit_code,
        "summary": summary,
        "status_line": None,
        "remaining_percent": None,
        "remaining_percents": [],
        "quota_checked_at": None,
        "incomplete": False,
    }


def _endpoint_candidates(auth: Dict[str, Any]) -> List[str]:
    mode = str(auth.get("auth_mode") or "").strip().lower()
    if mode in {"", "chatgpt", "chatgptauthtokens"}:
        return [USAGE_ENDPOINT_CHATGPT, USAGE_ENDPOINT_CODEXAPI]
    return [USAGE_ENDPOINT_CODEXAPI, USAGE_ENDPOINT_CHATGPT]


def _usage_headers(endpoint: str, access_token: str, account_id: str) -> Dict[str, str]:
    headers = {
        "Authorization": "Bearer %s" % access_token,
        "Accept": "application/json",
        "User-Agent": "codex-cli",
        "OpenAI-Beta": "codex=v1",
    }
    if endpoint.startswith("https://chatgpt.com/"):
        headers["Origin"] = "https://chatgpt.com"
        headers["Referer"] = "https://chatgpt.com/"
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _perform_request(
    endpoint: str,
    headers: Dict[str, str],
    timeout_seconds: float,
    *,
    url_opener: Optional[Callable[..., object]] = None,
) -> Tuple[int, bytes]:
    request = urllib.request.Request(endpoint, headers=headers, method="GET")
    opener = url_opener or urllib.request.urlopen
    with opener(request, timeout=timeout_seconds) as response:  # type: ignore[attr-defined]
        body = response.read(MAX_USAGE_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
        if len(body) > MAX_USAGE_RESPONSE_BYTES:
            raise ValueError("usage response exceeds safety limit")
        status_code = int(
            getattr(response, "status", None)
            or getattr(response, "code", 0)
            or 0
        )
        return status_code, body


def probe_account_quota_http(
    config: Dict[str, Any],
    account: Dict[str, Any],
    *,
    timeout_seconds: float = 10,
    url_opener: Optional[Callable[..., object]] = None,
    auth_override: Optional[Dict[str, Any]] = None,
    allow_auth_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    del config, account, allow_auth_refresh
    started = _now_utc()
    auth = auth_override if isinstance(auth_override, dict) else {}
    access_token, unused_refresh_token, unused_id_token = auth_tokens(auth)
    account_id = auth_account_id(auth)
    if not _token_supported(access_token):
        return None
    if _token_needs_refresh(access_token, now=started):
        return _build_probe_error("login", started, "access token needs refresh")

    for endpoint in _endpoint_candidates(auth):
        try:
            status_code, body = _perform_request(
                endpoint,
                _usage_headers(endpoint, access_token, account_id),
                timeout_seconds,
                url_opener=url_opener,
            )
        except urllib.error.HTTPError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if code == 401:
                return _build_probe_error(
                    "login",
                    started,
                    "usage endpoint rejected token (HTTP 401)",
                    401,
                )
            if code == 429:
                return _build_probe_error(
                    "limited",
                    started,
                    "usage endpoint returned HTTP 429",
                    429,
                )
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        except Exception:
            continue
        if status_code and status_code >= 400:
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        return _build_probe_success(payload, started, endpoint)
    return None
