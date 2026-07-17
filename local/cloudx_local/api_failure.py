from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional


MAX_ERROR_BYTES = 256 * 1024
ROOT_CAUSE_WINDOW_SECONDS = 15 * 60

CAUSE_ACCOUNT_DEACTIVATED = "account_deactivated"
CAUSE_QUOTA_EXHAUSTED = "quota_exhausted"
CAUSE_RATE_LIMITED = "rate_limited"
CAUSE_LOGIN_REQUIRED = "login_required"
CAUSE_ACCESS_DENIED = "access_denied"
CAUSE_NO_USABLE_ACCOUNTS = "no_usable_accounts"
CAUSE_GATEWAY_AUTHENTICATION = "gateway_authentication_failed"
CAUSE_GATEWAY_UNREACHABLE = "gateway_unreachable"
CAUSE_GATEWAY_FAILURE = "gateway_failure"
CAUSE_UPSTREAM_FAILURE = "upstream_failure"
CAUSE_UNKNOWN = "unknown"

DEFINITIVE_ACCOUNT_CAUSES = {
    CAUSE_ACCOUNT_DEACTIVATED,
    CAUSE_QUOTA_EXHAUSTED,
    CAUSE_RATE_LIMITED,
    CAUSE_LOGIN_REQUIRED,
    CAUSE_ACCESS_DENIED,
}

SIGNAL_NONE = "none"
SIGNAL_OTHER = "other"
KNOWN_SIGNALS = {
    "account_deactivated",
    "account_disabled",
    "account_suspended",
    "usage_limit_reached",
    "insufficient_quota",
    "quota_exceeded",
    "billing_hard_limit_reached",
    "credits_exhausted",
    "rate_limit_error",
    "rate_limit_exceeded",
    "too_many_requests",
    "refresh_token_reused",
    "invalid_grant",
    "invalid_token",
    "token_expired",
    "invalid_api_key",
    "authentication_error",
    "unauthorized",
    "permission_denied",
    "forbidden",
    "model_not_found",
    "auth_unavailable",
    "internal_server_error",
}

_HTTP_STATUS = re.compile(rb"(?:^|\r\n)HTTP/1\.[01]\s+([1-5][0-9]{2})\b")
_ERROR_MARKERS = (
    b'"type":"error"',
    b'"type": "error"',
    b"response.failed",
    b"usage_limit_reached",
    b"insufficient_quota",
    b"account_deactivated",
    b"account_suspended",
    b"refresh_token_reused",
    b"auth_unavailable",
    b"rate_limit_exceeded",
)


@dataclass(frozen=True)
class ApiFailure:
    cause: str
    http_status: Optional[int]
    signal: str
    observed_at: str
    retry_at: Optional[str]
    definitive: bool

    def as_observation(self, source: str) -> Dict[str, Any]:
        return {
            "cause": self.cause,
            "httpStatus": self.http_status,
            "signal": self.signal,
            "observedAt": self.observed_at,
            "retryAt": self.retry_at,
            "definitive": self.definitive,
            "source": source,
            "maskedBy": None,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_document(text: str) -> Dict[str, Any]:
    candidates = []
    stripped = text.strip()
    if stripped.startswith("data:"):
        candidates.append(stripped[5:].strip())
    candidates.append(stripped)
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if candidate.startswith("data:"):
            candidate = candidate[5:].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            candidates.append(candidate)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def _error_fields(document: Dict[str, Any]) -> Dict[str, Any]:
    error = document.get("error")
    if not isinstance(error, dict):
        response = document.get("response")
        error = response.get("error") if isinstance(response, dict) else None
    if not isinstance(error, dict):
        error = document
    return error if isinstance(error, dict) else {}


def _normalized_signal(fields: Dict[str, Any]) -> str:
    for key in ("type", "code", "error_type"):
        value = str(fields.get(key) or "").strip().casefold().replace("-", "_")
        if value in KNOWN_SIGNALS:
            return value
    return SIGNAL_OTHER


def _retry_at(fields: Dict[str, Any], observed_at: datetime) -> Optional[str]:
    for key in ("resets_at", "reset_at"):
        value = fields.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            try:
                return iso_utc(datetime.fromtimestamp(float(value), tz=timezone.utc))
            except (OSError, OverflowError, ValueError):
                pass
        if isinstance(value, str):
            parsed = parse_timestamp(value)
            if parsed is not None:
                return iso_utc(parsed)
    for key in ("resets_in_seconds", "retry_after_seconds", "reset_after_seconds"):
        value = fields.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return iso_utc(observed_at + timedelta(seconds=float(value)))
    return None


def classify_http_failure(
    status_code: Optional[int],
    body: bytes,
    *,
    observed_at: Optional[datetime] = None,
) -> ApiFailure:
    current = observed_at or utc_now()
    bounded = body[-MAX_ERROR_BYTES:]
    text = bounded.decode("utf-8", errors="replace")
    document = _error_document(text)
    fields = _error_fields(document)
    signal = _normalized_signal(fields)
    message = str(fields.get("message") or document.get("message") or "").strip().casefold()
    lower = text.casefold()
    searchable = message or (lower if isinstance(status_code, int) and status_code >= 400 else "")
    retry_at = _retry_at(fields, current)

    deactivated = signal in {"account_deactivated", "account_disabled", "account_suspended"} or any(
        phrase in searchable
        for phrase in (
            "account has been deactivated",
            "account was deactivated",
            "account is deactivated",
            "account has been suspended",
            "account is suspended",
        )
    )
    quota = signal in {
        "usage_limit_reached",
        "insufficient_quota",
        "quota_exceeded",
        "billing_hard_limit_reached",
        "credits_exhausted",
    } or any(
        phrase in searchable
        for phrase in (
            "usage limit has been reached",
            "you've hit your usage limit",
            "you’ve hit your usage limit",
            "exceeded your current quota",
            "billing hard limit has been reached",
            "credit balance is too low",
            "no credits remaining",
            "quota exhausted",
        )
    )
    login = signal in {
        "refresh_token_reused",
        "invalid_grant",
        "invalid_token",
        "token_expired",
        "invalid_api_key",
        "authentication_error",
        "unauthorized",
    } or any(
        phrase in searchable
        for phrase in (
            "invalid or expired token",
            "token has expired",
            "token was revoked",
            "refresh token has already been used",
            "refresh token was already used",
            "please try signing in again",
            "please log out and sign in again",
        )
    )
    rate_limited = signal in {"rate_limit_error", "rate_limit_exceeded", "too_many_requests"} or any(
        phrase in message
        for phrase in ("rate limit reached", "rate limit exceeded", "too many requests")
    )
    no_usable = signal == "auth_unavailable" or any(
        phrase in searchable
        for phrase in ("auth_unavailable", "no auth available", "no usable accounts")
    )
    access_denied = signal in {"permission_denied", "forbidden", "model_not_found"} or any(
        phrase in message
        for phrase in ("permission denied", "does not have access", "model is not supported")
    )

    if deactivated:
        cause, definitive = CAUSE_ACCOUNT_DEACTIVATED, True
        if signal == SIGNAL_OTHER:
            signal = "account_deactivated"
    elif quota:
        cause, definitive = CAUSE_QUOTA_EXHAUSTED, True
        if signal == SIGNAL_OTHER:
            signal = "usage_limit_reached"
    elif login:
        cause, definitive = CAUSE_LOGIN_REQUIRED, True
        if signal == SIGNAL_OTHER:
            signal = "authentication_error"
    elif rate_limited:
        cause, definitive = CAUSE_RATE_LIMITED, True
        if signal == SIGNAL_OTHER:
            signal = "rate_limit_exceeded"
    elif no_usable:
        cause, definitive, signal = CAUSE_NO_USABLE_ACCOUNTS, False, "auth_unavailable"
    elif access_denied:
        cause, definitive = CAUSE_ACCESS_DENIED, True
        if signal == SIGNAL_OTHER:
            signal = "forbidden"
    elif status_code == 401:
        cause, definitive, signal = CAUSE_LOGIN_REQUIRED, True, "http_401"
    elif status_code == 403:
        cause, definitive, signal = CAUSE_ACCESS_DENIED, True, "http_403"
    elif status_code == 429:
        cause, definitive, signal = CAUSE_RATE_LIMITED, True, "http_429"
    elif isinstance(status_code, int) and status_code >= 500:
        cause, definitive, signal = CAUSE_UPSTREAM_FAILURE, False, "http_5xx"
    else:
        cause, definitive = CAUSE_UNKNOWN, False
        if signal == SIGNAL_OTHER:
            signal = SIGNAL_NONE

    if signal == SIGNAL_OTHER and isinstance(status_code, int):
        signal = "http_%d" % status_code if status_code in {401, 403, 429, 500, 502, 503, 504} else SIGNAL_OTHER
    return ApiFailure(
        cause=cause,
        http_status=status_code,
        signal=signal,
        observed_at=iso_utc(current),
        retry_at=retry_at,
        definitive=definitive,
    )


class ApiResponseObserver:
    """Observe plaintext gateway responses without changing forwarded bytes."""

    def __init__(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self.callback = callback
        self.buffer = bytearray()
        self.status_code: Optional[int] = None
        self.last_signature = None
        self.total_bytes = 0
        self.buffer_start = 0
        self.last_status_offset = -1
        self.marker_tail = b""
        self.failure_marker_seen = False
        self.response_observed_at: Optional[datetime] = None

    def feed(self, data: bytes) -> None:
        if not data:
            return
        self.buffer.extend(data)
        self.total_bytes += len(data)
        if len(self.buffer) > MAX_ERROR_BYTES:
            del self.buffer[:-MAX_ERROR_BYTES]
        self.buffer_start = self.total_bytes - len(self.buffer)
        statuses = list(_HTTP_STATUS.finditer(bytes(self.buffer)))
        if statuses:
            latest = statuses[-1]
            absolute = self.buffer_start + latest.start()
            if absolute > self.last_status_offset:
                if self.last_status_offset >= 0:
                    del self.buffer[:latest.start()]
                    self.buffer_start = absolute
                self.last_status_offset = absolute
                self.last_signature = None
                self.marker_tail = b""
                self.failure_marker_seen = False
                self.response_observed_at = utc_now()
            self.status_code = int(latest.group(1))
        marker_input = (self.marker_tail + data).lower()
        self.marker_tail = marker_input[-128:]
        if any(marker in marker_input for marker in _ERROR_MARKERS):
            self.failure_marker_seen = True
            if self.response_observed_at is None:
                self.response_observed_at = utc_now()
        if not self._may_contain_failure():
            return
        self._emit_if_classified(force=False)

    def close(self) -> None:
        self._emit_if_classified(force=True)

    def _may_contain_failure(self) -> bool:
        if isinstance(self.status_code, int) and self.status_code >= 400:
            raw = bytes(self.buffer)
            separator = raw.rfind(b"\r\n\r\n")
            return separator >= 0 and len(raw) > separator + 4
        return self.failure_marker_seen

    def _emit_if_classified(self, *, force: bool) -> None:
        if self.response_observed_at is None:
            self.response_observed_at = utc_now()
        failure = classify_http_failure(
            self.status_code,
            bytes(self.buffer),
            observed_at=self.response_observed_at,
        )
        if failure.cause == CAUSE_UNKNOWN:
            return
        if failure.cause == CAUSE_UPSTREAM_FAILURE and not force:
            return
        signature = (failure.cause, failure.http_status, failure.signal, failure.retry_at)
        if signature == self.last_signature:
            return
        self.last_signature = signature
        self.callback(failure.as_observation("tunnel_observation"))
