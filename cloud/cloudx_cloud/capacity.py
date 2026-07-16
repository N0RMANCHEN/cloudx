from __future__ import annotations

from typing import Any, Dict, Tuple

from .config import Config
from .gateway import GatewayProbe
from .health import observe_health, utc_now
from .version import PROTOCOL_MAX, PROTOCOL_MIN, VERSION


HEALTH_SCHEMA = "cloudx.health.v1"
COUNT_KEYS = ("total", "available", "limited", "unavailable")
PROBE_REASONS = {
    "credential_invalid": "gateway_credential_invalid",
    "network": "gateway_network_failure",
    "authentication": "gateway_authentication_failed",
    "client_response": "gateway_client_response",
    "server_response": "gateway_server_response",
}


def _protocol_range(minimum: int, maximum: int) -> Dict[str, int]:
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or minimum < 1
        or maximum < minimum
    ):
        raise ValueError("consumer protocol range is invalid")
    return {"min": minimum, "max": maximum}


def _counts(health: Dict[str, Any]) -> Tuple[Dict[str, int], int, bool]:
    raw = health.get("accountCounts")
    counts = {key: 0 for key in COUNT_KEYS}
    if not isinstance(raw, dict):
        return counts, 0, False
    for key in COUNT_KEYS:
        value = raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return counts, 0, False
        counts[key] = value
    classified = counts["available"] + counts["limited"] + counts["unavailable"]
    if classified > counts["total"]:
        return counts, 0, False
    return counts, counts["total"] - classified, True


def _freshness(health: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    raw = health.get("freshness")
    if not isinstance(raw, dict):
        return {"state": "unknown", "ageSeconds": 0}, False
    state = raw.get("state")
    age = raw.get("ageSeconds")
    if state not in ("fresh", "stale", "unknown"):
        return {"state": "unknown", "ageSeconds": 0}, False
    if not isinstance(age, int) or isinstance(age, bool) or age < 0:
        return {"state": "unknown", "ageSeconds": 0}, False
    return {"state": state, "ageSeconds": age}, True


def classify_capacity(
    health: Dict[str, Any],
    gateway: GatewayProbe,
    consumer_protocol_min: int,
    consumer_protocol_max: int,
) -> Dict[str, Any]:
    consumer = _protocol_range(consumer_protocol_min, consumer_protocol_max)
    producer = {"min": PROTOCOL_MIN, "max": PROTOCOL_MAX}
    counts, unobserved, counts_valid = _counts(health)
    freshness, freshness_valid = _freshness(health)
    health_schema = str(health.get("schema") or "unknown")
    health_protocol = health.get("protocolVersion")
    probe = gateway.detail if gateway.detail == "ok" or gateway.detail in PROBE_REASONS else "invalid"
    checked_at = health.get("checkedAt")
    if not isinstance(checked_at, str) or not checked_at.strip():
        checked_at = utc_now()

    state = "unknown_observation"
    reason = "missing_health_observation"
    if health_schema != HEALTH_SCHEMA:
        state, reason = "incompatible_producer", "health_schema_mismatch"
    elif not isinstance(health_protocol, int) or isinstance(health_protocol, bool) or not (
        PROTOCOL_MIN <= health_protocol <= PROTOCOL_MAX
    ):
        state, reason = "incompatible_producer", "health_protocol_mismatch"
    elif max(PROTOCOL_MIN, consumer_protocol_min) > min(PROTOCOL_MAX, consumer_protocol_max):
        state, reason = "incompatible_producer", "protocol_range_mismatch"
    elif gateway.status != "healthy" or gateway.detail != "ok":
        state = "probe_failure"
        reason = PROBE_REASONS.get(gateway.detail, "gateway_probe_invalid")
    elif freshness["state"] == "stale":
        state, reason = "stale_contract", "stale_health_observation"
    elif not freshness_valid or freshness["state"] == "unknown":
        state, reason = "unknown_observation", "missing_health_observation"
    elif not counts_valid:
        state, reason = "unknown_observation", "invalid_account_counts"
    elif counts["available"] > 0:
        state, reason = "healthy_capacity", "available_accounts_observed"
    elif unobserved > 0:
        state, reason = "unknown_observation", "unobserved_accounts"
    else:
        state, reason = "exhausted_capacity", "no_available_accounts"

    return {
        "schema": "cloudx.capacity.v1",
        "state": state,
        "reason": reason,
        "producer": {
            "cloudxVersion": VERSION,
            "protocol": producer,
            "healthSchema": health_schema,
        },
        "consumerProtocol": consumer,
        "gateway": {
            "status": gateway.status if gateway.status in ("healthy", "degraded", "unavailable", "unknown") else "unknown",
            "probe": probe,
            "httpStatus": (
                gateway.http_status
                if isinstance(gateway.http_status, int) and not isinstance(gateway.http_status, bool)
                else None
            ),
        },
        "accountCounts": counts,
        "unobservedAccounts": unobserved,
        "checkedAt": checked_at,
        "freshness": freshness,
    }


def build_capacity(
    config: Config,
    consumer_protocol_min: int = PROTOCOL_MIN,
    consumer_protocol_max: int = PROTOCOL_MAX,
) -> Dict[str, Any]:
    health, gateway = observe_health(config)
    return classify_capacity(health, gateway, consumer_protocol_min, consumer_protocol_max)
