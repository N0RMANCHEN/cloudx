from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, Mapping, Tuple


AUTH_MODE = "agentIdentity"
EXTERNAL_CAPABILITY = "codex-agent-identity-v1"
_ED25519_PKCS8_PREFIX = bytes.fromhex("302e020100300506032b657004220420")
_ED25519_PKCS8_BYTES = len(_ED25519_PKCS8_PREFIX) + 32
_MAX_RUNTIME_ID = 256
_MAX_METADATA_TEXT = 512


class AgentIdentityError(ValueError):
    pass


def is_agent_identity(data: Mapping[str, Any]) -> bool:
    return str(data.get("auth_mode") or "").strip().casefold() == AUTH_MODE.casefold()


def _required_text(data: Mapping[str, Any], key: str, maximum: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentIdentityError("%s is required" % key)
    text = value.strip()
    if len(text) > maximum or any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise AgentIdentityError("%s is invalid" % key)
    return text


def _optional_text(data: Mapping[str, Any], key: str, maximum: int = _MAX_METADATA_TEXT) -> str:
    value = data.get(key)
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise AgentIdentityError("%s is invalid" % key)
    text = value.strip()
    if not text or len(text) > maximum or any(
        ord(character) < 32 or ord(character) == 127 for character in text
    ):
        raise AgentIdentityError("%s is invalid" % key)
    return text


def _private_key(data: Mapping[str, Any]) -> str:
    encoded = _required_text(data, "agent_private_key", 256)
    try:
        der = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise AgentIdentityError("agent_private_key is not valid base64 PKCS#8") from exc
    if len(der) != _ED25519_PKCS8_BYTES or not der.startswith(_ED25519_PKCS8_PREFIX):
        raise AgentIdentityError("agent_private_key is not an Ed25519 PKCS#8 private key")
    return encoded


def normalize(
    data: Mapping[str, Any],
    *,
    fallback_account_id: str = "",
    fallback_email: str = "",
) -> Dict[str, Any]:
    if not is_agent_identity(data):
        raise AgentIdentityError("auth_mode is not agentIdentity")
    runtime_id = _required_text(data, "agent_runtime_id", _MAX_RUNTIME_ID)
    private_key = _private_key(data)
    disabled = data.get("disabled", False)
    if not isinstance(disabled, bool):
        raise AgentIdentityError("disabled is invalid")

    result: Dict[str, Any] = {
        "type": "codex",
        "auth_kind": "oauth",
        "auth_mode": AUTH_MODE,
        "disabled": disabled,
        "websockets": False,
        "agent_runtime_id": runtime_id,
        "agent_private_key": private_key,
    }
    account_id = (
        _optional_text(data, "account_id", 256)
        or _optional_text(data, "chatgpt_account_id", 256)
        or str(fallback_account_id or "").strip()
    )
    email = _optional_text(data, "email", 320) or str(fallback_email or "").strip()
    if account_id:
        result["account_id"] = account_id
    if email:
        result["email"] = email
    for key, maximum in (
        ("chatgpt_account_id", 256),
        ("chatgpt_user_id", 256),
        ("workspace_id", 256),
        ("plan_type", 64),
        ("label", 256),
        ("source", 256),
    ):
        value = _optional_text(data, key, maximum)
        if value:
            result[key] = value
    fedramp = data.get("chatgpt_account_is_fedramp")
    if fedramp is not None:
        if not isinstance(fedramp, bool):
            raise AgentIdentityError("chatgpt_account_is_fedramp is invalid")
        result["chatgpt_account_is_fedramp"] = fedramp
    # A task belongs to the gateway process that registered it. The compatible
    # external CPA must register and cache a fresh task before first use.
    return result


def fingerprint_parts(data: Mapping[str, Any]) -> Tuple[str, ...]:
    if not is_agent_identity(data):
        return ()
    return (
        AUTH_MODE,
        str(data.get("agent_runtime_id") or "").strip(),
        str(data.get("agent_private_key") or "").strip(),
    )


def is_valid(data: Mapping[str, Any]) -> bool:
    if not is_agent_identity(data):
        return False
    try:
        normalize(data)
    except AgentIdentityError:
        return False
    return True
