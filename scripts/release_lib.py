"""Shared release manifest and verification functions."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any, Dict, Iterable, List


RELEASE_NAMESPACE = "cloudx-release"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: pathlib.Path, component: str) -> Dict[str, Any]:
    return {
        "name": path.name,
        "component": component,
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if manifest.get("schema") != "cloudx.release-manifest.v1":
        errors.append("unsupported manifest schema")
    if manifest.get("product") != "cloudx":
        errors.append("wrong product")
    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        errors.append("invalid version")
    activation = manifest.get("activation")
    if not isinstance(activation, dict) or activation.get("automatic") is not False:
        errors.append("automatic activation must be false")
    protocol = manifest.get("protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("min"), int) or not isinstance(protocol.get("max"), int):
        errors.append("invalid protocol range")
    elif protocol["min"] > protocol["max"]:
        errors.append("inverted protocol range")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        components = {item.get("component") for item in artifacts if isinstance(item, dict)}
        if components != {"local", "cloud"}:
            errors.append("manifest must contain local and cloud artifacts")
        for item in artifacts:
            if not isinstance(item, dict):
                errors.append("invalid artifact record")
                continue
            if not re.match(r"^[a-f0-9]{64}$", str(item.get("sha256", ""))):
                errors.append("invalid artifact hash")
            if not isinstance(item.get("size"), int) or item["size"] < 1:
                errors.append("invalid artifact size")
    return errors


def verify_artifacts(manifest: Dict[str, Any], directory: pathlib.Path) -> List[str]:
    errors: List[str] = []
    for item in manifest.get("artifacts", []):
        path = directory / item["name"]
        if not path.is_file():
            errors.append("missing artifact: %s" % item["name"])
            continue
        if path.stat().st_size != item["size"]:
            errors.append("size mismatch: %s" % item["name"])
        if sha256(path) != item["sha256"]:
            errors.append("hash mismatch: %s" % item["name"])
    return errors


def verify_signature(
    manifest_path: pathlib.Path,
    signature_path: pathlib.Path,
    allowed_signers: pathlib.Path,
    identity: str,
) -> None:
    command = [
        "ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(allowed_signers),
        "-I",
        identity,
        "-n",
        RELEASE_NAMESPACE,
        "-s",
        str(signature_path),
    ]
    result = subprocess.run(command, input=manifest_path.read_bytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError("release signature verification failed: %s" % detail)


def load_manifest(path: pathlib.Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object")
    return data


def version_tuple(value: str) -> Iterable[int]:
    if not VERSION_RE.match(value):
        raise ValueError("invalid version: %s" % value)
    return tuple(int(part) for part in value.split("."))
