from __future__ import annotations

import fcntl
import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from .config import Config
from .gateway import probe_gateway
from .version import PROTOCOL_MAX, VERSION


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _observed_age(value: Any) -> int:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("account state observation time is missing")
    text = value.strip()
    observed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if observed.tzinfo is None:
        raise ValueError("account state observation time has no timezone")
    return max(0, int(datetime.now(timezone.utc).timestamp() - observed.timestamp()))


def _account_counts(config: Config) -> Tuple[Dict[str, int], str, int]:
    counts = {"total": 0, "available": 0, "limited": 0, "unavailable": 0}
    if config.account_state_path.is_file():
        try:
            data = json.loads(config.account_state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("account state must be an object")
            raw_counts = data.get("accountCounts", data)
            for key in counts:
                value = raw_counts.get(key) if isinstance(raw_counts, dict) else None
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError("account state contains invalid counts")
                counts[key] = value
            if data.get("schema") == "cloudx.account-state.v1":
                unobserved = data.get("unobservedAccounts")
                if not isinstance(unobserved, int) or isinstance(unobserved, bool) or unobserved < 0:
                    raise ValueError("account state contains an invalid unobserved count")
                classified = counts["available"] + counts["limited"] + counts["unavailable"]
                if counts["total"] != classified + unobserved:
                    raise ValueError("account state counts do not add up")
                age = _observed_age(data.get("observedAt"))
            else:
                age = max(
                    0,
                    int(datetime.now(timezone.utc).timestamp() - config.account_state_path.stat().st_mtime),
                )
            return counts, "fresh" if age <= 900 else "stale", age
        except (OSError, ValueError, TypeError):
            pass
    return counts, "unknown", 0


def _import_status(config: Config) -> str:
    config.import_lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with config.import_lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "busy"
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    except OSError:
        return "unavailable"
    return "ready"


def build_health(config: Config) -> Dict[str, Any]:
    gateway = probe_gateway(config.gateway_url, config.client_credential_file)
    counts, freshness, age = _account_counts(config)
    return {
        "schema": "cloudx.health.v1",
        "cloudxVersion": VERSION,
        "protocolVersion": PROTOCOL_MAX,
        "gatewayStatus": gateway.status,
        "importStatus": _import_status(config),
        "accountCounts": counts,
        "checkedAt": utc_now(),
        "freshness": {"state": freshness, "ageSeconds": age},
    }


def publish(path: pathlib.Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temp_name = tempfile.mkstemp(prefix=".cloudx-health-", dir=str(path.parent))
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
