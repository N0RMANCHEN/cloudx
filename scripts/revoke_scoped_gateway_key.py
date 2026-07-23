#!/usr/bin/env python3
"""Revoke exactly one previously rotated Cloudx gateway key with rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
from typing import Any, Dict, Optional, Sequence, Tuple

from install_scoped_gateway_key import (
    DEFAULT_CONFIG,
    DEFAULT_CREDENTIAL,
    DEFAULT_ROTATION_ROOT,
    ROTATION_SCHEMA,
    TRANSACTION_RE,
    VERSION_RE,
    Snapshot,
    _safe_snapshot,
    api_keys,
    atomic_json,
    atomic_write,
    inotify_watch_count,
    probe,
    restore,
    sha256,
    scoped_key_lock,
    systemctl,
    top_level_value,
    verify_artifact,
    wait_active,
    wait_status,
)


CONFIRMATION = "RESTART cliproxy.service TO REVOKE PREVIOUS CLOUDX SCOPED KEY"
PLAN_SCHEMA = "cloudx.scoped-key-revocation-plan.v1"
RESULT_SCHEMA = "cloudx.scoped-key-revocation.v1"
DEFAULT_UNIT = "cliproxy.service"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_CREDENTIAL_BYTES = 4096
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _safe_bytes(path: pathlib.Path, label: str, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            raise RuntimeError("%s is unsafe" % label)
        data = os.read(descriptor, maximum + 1)
        if len(data) != metadata.st_size:
            raise RuntimeError("%s changed while being read" % label)
        return data
    finally:
        os.close(descriptor)


def _manifest(path: pathlib.Path, transaction_id: str, release_version: str) -> Dict[str, Any]:
    try:
        document = json.loads(_safe_bytes(path, "rotation manifest", MAX_MANIFEST_BYTES))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("rotation manifest is invalid") from exc
    expected_keys = {
        "schema", "status", "transactionId", "releaseVersion", "artifact", "unit",
        "config", "credential", "environment", "oldCredentialSha256",
        "newCredentialSha256", "configSha256Before", "configSha256After",
        "gatewayKeyCountBefore", "gatewayKeyCountAfter", "oldPid", "newPid",
        "gatewayHttpStatus", "inotifyWatches", "backup", "previousCredentialRetained",
        "previousCredentialRevoked",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise RuntimeError("rotation manifest shape is unsupported")
    if (
        document.get("schema") != ROTATION_SCHEMA
        or document.get("status") != "rotated"
        or document.get("transactionId") != transaction_id
        or document.get("releaseVersion") != release_version
        or document.get("artifact")
        != "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % release_version
        or document.get("unit") != DEFAULT_UNIT
        or document.get("config") != str(DEFAULT_CONFIG)
        or document.get("credential") != str(DEFAULT_CREDENTIAL)
        or document.get("previousCredentialRetained") is not True
        or document.get("previousCredentialRevoked") is not False
    ):
        raise RuntimeError("rotation manifest does not authorize this revocation")
    for name in (
        "oldCredentialSha256", "newCredentialSha256", "configSha256Before", "configSha256After"
    ):
        if not SHA256_RE.fullmatch(str(document.get(name) or "")):
            raise RuntimeError("rotation manifest digest is invalid")
    before = document.get("gatewayKeyCountBefore")
    after = document.get("gatewayKeyCountAfter")
    if not isinstance(before, int) or not isinstance(after, int) or after != before + 1:
        raise RuntimeError("rotation manifest key counts are invalid")
    return document


def remove_api_key_by_digest(original: bytes, digest: str) -> Tuple[bytes, str, int]:
    keys = api_keys(original)
    matches = [key for key in keys if hashlib.sha256(key.encode("utf-8")).hexdigest() == digest]
    if len(matches) != 1:
        raise RuntimeError("previous credential digest does not match exactly one gateway key")
    target = matches[0]
    lines = original.decode("utf-8").splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("api-keys:")]
    removed = 0
    output: list[str] = []
    in_keys = False
    for index, line in enumerate(lines):
        if index == starts[0]:
            in_keys = True
            output.append(line)
            continue
        stripped = line.strip()
        if in_keys and stripped and not stripped.startswith("#") and not line[0].isspace():
            in_keys = False
        if in_keys and stripped.startswith("-"):
            value = json.loads(stripped[1:].strip())
            if value == target:
                removed += 1
                continue
        output.append(line)
    if removed != 1:
        raise RuntimeError("previous credential line was not removed exactly once")
    updated = "".join(output).encode("utf-8")
    expected = list(keys)
    expected.remove(target)
    if api_keys(updated) != expected:
        raise RuntimeError("revocation changed an unrelated gateway key")
    return updated, target, len(keys)


def _transaction_directory(transaction_id: str) -> pathlib.Path:
    if not TRANSACTION_RE.fullmatch(transaction_id):
        raise RuntimeError("rotation transaction identity is invalid")
    root_metadata = DEFAULT_ROTATION_ROOT.lstat()
    if (
        DEFAULT_ROTATION_ROOT.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != 0
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("rotation root is unsafe")
    transaction = DEFAULT_ROTATION_ROOT / transaction_id
    metadata = transaction.lstat()
    if (
        transaction.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("rotation transaction directory is unsafe")
    return transaction


def plan(release_version: str, transaction_id: str) -> Dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % release_version,
        "transactionId": transaction_id,
        "unit": DEFAULT_UNIT,
        "gatewayRestartRequired": True,
        "automaticAction": False,
        "authorization": {
            "gatewayConfigWrite": False,
            "gatewayRestart": False,
            "previousCredentialRevocation": False,
            "credentialWrite": False,
            "otherKeyMutation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    root.add_argument("--transaction-id", required=True)
    root.add_argument("--artifact", type=pathlib.Path)
    root.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    root.add_argument("--credential", type=pathlib.Path, default=DEFAULT_CREDENTIAL)
    root.add_argument("--unit", default=DEFAULT_UNIT)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if not TRANSACTION_RE.fullmatch(args.transaction_id):
        raise RuntimeError("rotation transaction identity is invalid")
    artifact = args.artifact or pathlib.Path(
        "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % args.release_version
    )
    if (
        artifact != pathlib.Path("/opt/cloudx/releases/%s/cloudx-cloud.pyz" % args.release_version)
        or args.config != DEFAULT_CONFIG
        or args.credential != DEFAULT_CREDENTIAL
        or args.unit != DEFAULT_UNIT
    ):
        raise RuntimeError("revocation is restricted to the declared gateway contract")
    if not args.apply:
        print(json.dumps(plan(args.release_version, args.transaction_id), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("revocation confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("revocation must run as root")
    verify_artifact(artifact, args.release_version)
    with scoped_key_lock():
        return _apply(args, artifact)


def _apply(args: argparse.Namespace, artifact: pathlib.Path) -> int:
    del artifact

    transaction = _transaction_directory(args.transaction_id)
    manifest_path = transaction / "manifest.json"
    manifest_before = _safe_snapshot(manifest_path, "rotation manifest", MAX_MANIFEST_BYTES)
    manifest = _manifest(manifest_path, args.transaction_id, args.release_version)
    config_before = _safe_snapshot(args.config, "gateway config", MAX_CONFIG_BYTES)
    credential = _safe_snapshot(args.credential, "Cloudx client credential", MAX_CREDENTIAL_BYTES)
    if credential.mode & 0o077:
        raise RuntimeError("Cloudx client credential permissions are too broad")
    try:
        current_key = credential.data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("Cloudx client credential is invalid") from exc
    if sha256(current_key.encode("utf-8")) != manifest["newCredentialSha256"]:
        raise RuntimeError("current credential does not match the rotated credential")
    if sha256(config_before.data) != manifest["configSha256After"]:
        raise RuntimeError("gateway config changed after rotation")
    if api_keys(config_before.data).count(current_key) != 1:
        raise RuntimeError("current credential is not unique in gateway config")
    config_after, old_key, count_before = remove_api_key_by_digest(
        config_before.data, manifest["oldCredentialSha256"]
    )
    if old_key == current_key:
        raise RuntimeError("revocation would remove the current credential")
    if count_before != manifest["gatewayKeyCountAfter"]:
        raise RuntimeError("gateway key count changed after rotation")

    host = top_level_value(config_before.data, "host")
    port = int(top_level_value(config_before.data, "port"))
    old_pid = int(systemctl("show", args.unit, "-p", "MainPID", "--value", capture=True) or "0")
    backup = transaction / "config.before-revocation.yaml"
    receipt = transaction / "revocation.json"
    if backup.exists() or receipt.exists():
        raise RuntimeError("revocation artifacts already exist")
    atomic_write(backup, config_before.data, 0o600, 0, 0)
    try:
        atomic_write(
            args.config,
            config_after,
            config_before.mode,
            config_before.uid,
            config_before.gid,
        )
        systemctl("restart", args.unit)
        new_pid = wait_active(args.unit)
        new_status = probe(host, port, current_key)
        old_status = wait_status(host, port, old_key, 401)
        watches = inotify_watch_count(new_pid)
        if watches < 2:
            raise RuntimeError("gateway config and auth watches were not restored")
        credential_after = _safe_snapshot(
            args.credential, "Cloudx client credential", MAX_CREDENTIAL_BYTES
        )
        if credential_after != credential:
            raise RuntimeError("Cloudx client credential changed during revocation")
        config_observed = _safe_snapshot(args.config, "gateway config", MAX_CONFIG_BYTES)
        if config_observed.data != config_after:
            raise RuntimeError("gateway config changed during revocation")
        result = {
            "schema": RESULT_SCHEMA,
            "status": "revoked",
            "transactionId": args.transaction_id,
            "releaseVersion": args.release_version,
            "unit": args.unit,
            "oldPid": old_pid,
            "newPid": new_pid,
            "gatewayKeyCountBefore": count_before,
            "gatewayKeyCountAfter": count_before - 1,
            "newCredentialHttpStatus": new_status,
            "oldCredentialHttpStatus": old_status,
            "inotifyWatches": watches,
            "configSha256Before": sha256(config_before.data),
            "configSha256After": sha256(config_after),
            "currentCredentialUnchanged": True,
            "previousCredentialRevoked": True,
            "otherGatewayKeysUnchanged": True,
            "backup": str(backup),
        }
        atomic_json(receipt, result)
        manifest.update({
            "status": "revoked",
            "previousCredentialRevoked": True,
            "revocationReceipt": str(receipt),
            "revokedConfigSha256": sha256(config_after),
        })
        atomic_json(manifest_path, manifest)
    except Exception as exc:
        recovery_error: Optional[Exception] = None
        try:
            restore(args.config, config_before)
            systemctl("restart", args.unit)
            wait_active(args.unit)
            rollback_new = probe(host, port, current_key)
            rollback_old = probe(host, port, old_key)
            if rollback_new != 200 or rollback_old != 200:
                raise RuntimeError("restored gateway keys did not pass rollback canaries")
        except Exception as recovery_exc:
            recovery_error = recovery_exc
        try:
            restore(manifest_path, manifest_before)
            receipt.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            recovery_error = recovery_error or cleanup_exc
        if recovery_error is not None:
            raise RuntimeError("revocation failed and rollback verification is incomplete") from recovery_error
        raise RuntimeError("revocation failed and was rolled back") from exc

    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("revoke_scoped_gateway_key.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
