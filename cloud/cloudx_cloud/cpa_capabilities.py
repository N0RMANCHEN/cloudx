from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from .config import Config


SCHEMA = "cloudx.cloud-cpa-capabilities.v1"
CAPABILITY_HEADER = "X-Cloudx-CPA-Capabilities"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_BINARY_BYTES = 256 * 1024 * 1024
_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CpaCapabilityError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CapabilityAttestation:
    runtime_version: str
    binary_sha256: str
    capabilities: Tuple[str, ...]


def _safe_regular_bytes(path: pathlib.Path, maximum: int, reason: str) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise CpaCapabilityError(reason)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise CpaCapabilityError(reason) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise CpaCapabilityError(reason)
        chunks = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise CpaCapabilityError(reason) from exc
    finally:
        os.close(descriptor)
    if len(raw) > maximum or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise CpaCapabilityError(reason)
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise CpaCapabilityError(reason) from exc
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise CpaCapabilityError(reason)
    return raw


def _bounded_text(value: Any, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > maximum or any(
        ord(character) < 32 or ord(character) == 127 for character in text
    ):
        return ""
    return text


def _manifest(config: Config) -> Dict[str, Any]:
    configured = config.cpa_capability_manifest
    if configured is None:
        raise CpaCapabilityError("manifest_missing")
    path = pathlib.Path(configured).expanduser()
    raw = _safe_regular_bytes(path, MAX_MANIFEST_BYTES, "manifest_unavailable")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CpaCapabilityError("manifest_invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise CpaCapabilityError("manifest_invalid")
    return document


def _binary(config: Config, document: Dict[str, Any]) -> str:
    manifest_binary = _bounded_text(document.get("binary"), 1024)
    if not manifest_binary:
        raise CpaCapabilityError("binary_unbound")
    declared = pathlib.Path(manifest_binary).expanduser()
    path = pathlib.Path(config.cpa_binary).expanduser() if config.cpa_binary is not None else declared
    if not path.is_absolute() or not declared.is_absolute():
        raise CpaCapabilityError("binary_unbound")
    if path.resolve(strict=False) != declared.resolve(strict=False):
        raise CpaCapabilityError("binary_unbound")
    raw = _safe_regular_bytes(path, MAX_BINARY_BYTES, "binary_unavailable")
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
    except OSError as exc:
        raise CpaCapabilityError("binary_unavailable") from exc
    if not mode & stat.S_IXUSR:
        raise CpaCapabilityError("binary_unavailable")
    return hashlib.sha256(raw).hexdigest()


def _declared_capabilities(document: Dict[str, Any]) -> Tuple[str, ...]:
    values = document.get("capabilities")
    if not isinstance(values, list) or not values:
        raise CpaCapabilityError("manifest_invalid")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise CpaCapabilityError("manifest_invalid")
        capability = value.strip().casefold()
        if not _CAPABILITY.fullmatch(capability):
            raise CpaCapabilityError("manifest_invalid")
        if capability not in result:
            result.append(capability)
    return tuple(result)


def _probe_url(config: Config) -> str:
    value = config.gateway_url.rstrip("/") + "/healthz"
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise CpaCapabilityError("probe_invalid") from exc
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/healthz"
        or parsed.query
        or parsed.fragment
    ):
        raise CpaCapabilityError("probe_invalid")
    return value


def _live_capabilities(
    config: Config,
    opener: Optional[Callable[..., object]],
) -> Tuple[str, ...]:
    request = urllib.request.Request(
        _probe_url(config),
        headers={"Accept": "application/json", "User-Agent": "cloudx-capability-probe"},
        method="GET",
    )
    active = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    try:
        with active(request, timeout=2.0) as response:  # type: ignore[attr-defined]
            status_code = int(
                getattr(response, "status", None) or getattr(response, "code", 0) or 0
            )
            headers = getattr(response, "headers", None)
            value = headers.get(CAPABILITY_HEADER, "") if headers is not None else ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise CpaCapabilityError("probe_unavailable") from exc
    if status_code != 200 or not isinstance(value, str):
        raise CpaCapabilityError("probe_rejected")
    capabilities = []
    for item in value.split(","):
        capability = item.strip().casefold()
        if capability and _CAPABILITY.fullmatch(capability) and capability not in capabilities:
            capabilities.append(capability)
    return tuple(capabilities)


def attest(
    config: Config,
    required: str,
    *,
    opener: Optional[Callable[..., object]] = None,
) -> CapabilityAttestation:
    capability = str(required or "").strip().casefold()
    if not _CAPABILITY.fullmatch(capability):
        raise CpaCapabilityError("capability_invalid")
    document = _manifest(config)
    actual_digest = _binary(config, document)
    expected_digest = _bounded_text(document.get("binarySha256"), 64).casefold()
    runtime_version = _bounded_text(document.get("runtimeVersion"), 128)
    declared = _declared_capabilities(document)
    if not _SHA256.fullmatch(expected_digest) or actual_digest != expected_digest:
        raise CpaCapabilityError("binary_digest_mismatch")
    if not runtime_version or capability not in declared:
        raise CpaCapabilityError("capability_missing")
    live = _live_capabilities(config, opener)
    if capability not in live:
        raise CpaCapabilityError("live_capability_missing")
    return CapabilityAttestation(runtime_version, actual_digest, declared)


def check(config: Config, required: str) -> str:
    try:
        attest(config, required)
    except CpaCapabilityError as exc:
        return exc.reason
    return ""
