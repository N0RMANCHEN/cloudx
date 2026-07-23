#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import grp
import hashlib
import json
import os
import pathlib
import pwd
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from contextlib import contextmanager
from typing import Optional, Sequence, Tuple


CONFIRMATION = "RESTART cliproxy.service FOR CLOUDX SCOPED KEY"
ROTATION_SCHEMA = "cloudx.scoped-key-rotation.v1"
DEFAULT_CONFIG = pathlib.Path("/etc/cliproxy/config.yaml")
DEFAULT_CREDENTIAL = pathlib.Path("/etc/cloudx/client-credential")
DEFAULT_ENVIRONMENT = pathlib.Path("/etc/cloudx/cloudx-shadow.env")
DEFAULT_ROTATION_ROOT = pathlib.Path("/var/lib/cloudx/scoped-key-rotations")
DEFAULT_LOCK = pathlib.Path("/run/lock/cloudx-scoped-key.lock")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_CREDENTIAL_BYTES = 4096
TRANSACTION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
PLAIN_KEY_RE = re.compile(r"^[A-Za-z0-9._~-]{1,512}$")


@dataclass(frozen=True)
class Snapshot:
    existed: bool
    data: bytes
    mode: int
    uid: int
    gid: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_snapshot(path: pathlib.Path, label: str, maximum: int) -> Snapshot:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("%s must be a regular non-symlink file" % label)
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        raise RuntimeError("%s has an invalid size" % label)
    return snapshot(path)


def snapshot(path: pathlib.Path) -> Snapshot:
    if not path.exists():
        return Snapshot(False, b"", 0, 0, 0)
    metadata = path.stat()
    return Snapshot(True, path.read_bytes(), stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)


def atomic_write(path: pathlib.Path, data: bytes, mode: int, uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_json(path: pathlib.Path, document: dict) -> None:
    atomic_write(
        path,
        (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o600,
        0,
        0,
    )


def restore(path: pathlib.Path, value: Snapshot) -> None:
    if value.existed:
        atomic_write(path, value.data, value.mode, value.uid, value.gid)
    else:
        path.unlink(missing_ok=True)


def append_api_key(original: bytes, key: str) -> Tuple[bytes, int]:
    text = original.decode("utf-8")
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("api-keys:")]
    if len(starts) != 1 or lines[starts[0]].strip() != "api-keys:":
        raise RuntimeError("gateway api-keys is not a supported block list")
    start = starts[0]
    end = len(lines)
    count = 0
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#") and not lines[index][0].isspace():
            end = index
            break
        if stripped.startswith("-"):
            count += 1
    lines.insert(end, "  - %s\n" % json.dumps(key))
    return "".join(lines).encode("utf-8"), count


def api_keys(original: bytes) -> list[str]:
    try:
        lines = original.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("gateway config is not UTF-8") from exc
    starts = [index for index, line in enumerate(lines) if line.startswith("api-keys:")]
    if len(starts) != 1 or lines[starts[0]].strip() != "api-keys:":
        raise RuntimeError("gateway api-keys is not a supported block list")
    result: list[str] = []
    for line in lines[starts[0] + 1:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not line[0].isspace():
            break
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith("-"):
            continue
        result.append(parse_api_key_scalar(stripped[1:].strip()))
    if not result:
        raise RuntimeError("gateway api-keys is empty")
    return result


def parse_api_key_scalar(value: str) -> str:
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("gateway api-key entry has invalid double-quoted syntax") from exc
    elif value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise RuntimeError("gateway api-key entry has invalid single-quoted syntax")
        inner = value[1:-1]
        parts: list[str] = []
        index = 0
        while index < len(inner):
            if inner[index] != "'":
                parts.append(inner[index])
                index += 1
                continue
            if index + 1 >= len(inner) or inner[index + 1] != "'":
                raise RuntimeError("gateway api-key entry has invalid single-quoted syntax")
            parts.append("'")
            index += 2
        parsed = "".join(parts)
    elif PLAIN_KEY_RE.fullmatch(value):
        parsed = value
    else:
        raise RuntimeError("gateway api-key entry is not a supported scalar")
    if not isinstance(parsed, str) or not parsed or len(parsed) > 512:
        raise RuntimeError("gateway api-key entry is invalid")
    return parsed


def top_level_value(original: bytes, name: str) -> str:
    prefix = name + ":"
    matches = [line[len(prefix):].strip() for line in original.decode("utf-8").splitlines() if line.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError("gateway config has no usable %s" % name)
    value = matches[0].split(" #", 1)[0].strip()
    if value[:1] == value[-1:] and value[:1] in ("'", '"'):
        value = value[1:-1]
    return value


def systemctl(*arguments: str, capture: bool = False) -> str:
    completed = subprocess.run(
        ["systemctl", *arguments],
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        check=True,
    )
    return completed.stdout.strip() if capture else ""


def wait_active(unit: str, timeout: float = 20.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = subprocess.run(
            ["systemctl", "is-active", unit],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        ).stdout.strip()
        if active == "active":
            value = systemctl("show", unit, "-p", "MainPID", "--value", capture=True)
            pid = int(value or "0")
            if pid > 0:
                return pid
        time.sleep(0.25)
    raise RuntimeError("gateway service did not become active")


def request_status(host: str, port: int, key: str) -> int:
    with socket.create_connection((host, port), timeout=2.0) as connection:
        request = (
            "GET /v1/models HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Authorization: Bearer %s\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n\r\n" % (host, key)
        ).encode("ascii")
        connection.sendall(request)
        parts = connection.recv(128).split(b"\r\n", 1)[0].split()
        return int(parts[1]) if len(parts) >= 2 else 0


def wait_status(host: str, port: int, key: str, expected: int, timeout: float = 20.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = request_status(host, port, key)
            if status == expected:
                return status
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("scoped gateway key did not reach HTTP %d" % expected)


def probe(host: str, port: int, key: str, timeout: float = 20.0) -> int:
    try:
        return wait_status(host, port, key, 200, timeout)
    except RuntimeError as exc:
        raise RuntimeError("scoped gateway key did not pass the model probe") from exc


def _prepare_rotation_directory() -> tuple[str, pathlib.Path]:
    transaction_id = "%s-%s" % (
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        secrets.token_hex(4),
    )
    if not TRANSACTION_RE.fullmatch(transaction_id):
        raise RuntimeError("rotation transaction identity is invalid")
    _private_root_directory(DEFAULT_ROTATION_ROOT, "rotation root")
    transaction = DEFAULT_ROTATION_ROOT / transaction_id
    transaction.mkdir(mode=0o700)
    os.chown(transaction, 0, 0)
    return transaction_id, transaction


def _private_root_directory(path: pathlib.Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("%s must be a root-owned mode-0700 directory" % label)


@contextmanager
def scoped_key_lock():
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(DEFAULT_LOCK), flags, 0o600)
    except OSError as exc:
        raise RuntimeError("scoped key transaction lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("scoped key transaction lock is unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("another scoped key transaction is active") from exc
        yield
    finally:
        os.close(descriptor)


def inotify_watch_count(pid: int) -> int:
    total = 0
    for path in pathlib.Path("/proc/%d/fdinfo" % pid).glob("*"):
        try:
            total += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("inotify wd:"))
        except (OSError, UnicodeDecodeError):
            continue
    return total


def verify_artifact(artifact: pathlib.Path, release_version: str) -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(artifact), "self-check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("staged cloud artifact self-check could not run") from exc
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("staged cloud artifact returned an invalid self-check") from exc
    if (
        completed.returncode != 0
        or not isinstance(document, dict)
        or document.get("schema") != "cloudx.self-check.v1"
        or document.get("component") != "cloud"
        or document.get("version") != release_version
        or document.get("status") != "ok"
    ):
        raise RuntimeError("staged cloud artifact does not match the requested release")


def environment_document(
    artifact: str,
    release_version: str,
    commit: str,
    gateway_version: str,
    host: str,
    port: int,
) -> bytes:
    return ("\n".join([
        "CLOUDX_CLOUD_ARTIFACT=%s" % artifact,
        "CLOUDX_AUTH_DIR=/var/lib/cloudx/shadow-auth",
        "CLOUDX_IMPORT_LOCK=/run/cloudx-shadow/import.lock",
        "CLOUDX_HEALTH_PATH=/run/cloudx-shadow/health.json",
        "CLOUDX_ACCOUNT_STATE_PATH=/run/cloudx-shadow/accounts.json",
        "CLOUDX_ACCOUNT_STATE_SOURCE=/var/lib/cloudx/cpa-health/state.json",
        "CLOUDX_GATEWAY_URL=http://%s:%d" % (host, port),
        "CLOUDX_GATEWAY_FORWARD_HOST=%s" % host,
        "CLOUDX_GATEWAY_FORWARD_PORT=%d" % port,
        "CLOUDX_GATEWAY_VERSION=%s" % gateway_version,
        "CLOUDX_CLIENT_CREDENTIAL_FILE=/etc/cloudx/client-credential",
        "CLOUDX_DEPLOYMENT_ID=shadow-%s" % release_version,
        "CLOUDX_BUILD_COMMIT=%s" % commit,
        "",
    ])).encode("utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Install a dedicated Cloudx gateway key with restart rollback")
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    root.add_argument("--unit", default="cliproxy.service")
    root.add_argument("--credential", type=pathlib.Path, default=DEFAULT_CREDENTIAL)
    root.add_argument("--environment", type=pathlib.Path, default=DEFAULT_ENVIRONMENT)
    root.add_argument("--release-version", required=True)
    root.add_argument("--artifact", type=pathlib.Path)
    root.add_argument("--build-commit", required=True)
    root.add_argument("--gateway-version", required=True)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.match(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    artifact = args.artifact or pathlib.Path(
        "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % args.release_version
    )
    expected_artifact = pathlib.Path(
        "/opt/cloudx/releases/%s/cloudx-cloud.pyz" % args.release_version
    )
    if (
        artifact != expected_artifact
        or args.config != DEFAULT_CONFIG
        or args.unit != "cliproxy.service"
        or args.credential != DEFAULT_CREDENTIAL
        or args.environment != DEFAULT_ENVIRONMENT
    ):
        raise RuntimeError("installer is restricted to the declared gateway contract")
    if not args.apply:
        print(json.dumps({
            "schema": "cloudx.scoped-key-plan.v1",
            "status": "confirmation-required",
            "confirmation": CONFIRMATION,
            "unit": args.unit,
            "config": str(args.config),
            "releaseVersion": args.release_version,
            "artifact": str(artifact),
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("restart confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("installer must run as root")
    verify_artifact(artifact, args.release_version)
    with scoped_key_lock():
        return _apply(args, artifact)


def _apply(args: argparse.Namespace, artifact: pathlib.Path) -> int:

    cloudx = pwd.getpwnam("cloudx")
    cloudx_group = grp.getgrnam("cloudx")
    credential_before = _safe_snapshot(
        args.credential, "Cloudx client credential", MAX_CREDENTIAL_BYTES
    )
    environment_before = _safe_snapshot(
        args.environment, "Cloudx shadow environment", MAX_CONFIG_BYTES
    )
    config_before = _safe_snapshot(args.config, "gateway config", MAX_CONFIG_BYTES)
    if credential_before.mode & 0o077:
        raise RuntimeError("Cloudx client credential permissions are too broad")
    try:
        old_key = credential_before.data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("Cloudx client credential is invalid") from exc
    existing_keys = api_keys(config_before.data)
    if not old_key or existing_keys.count(old_key) != 1:
        raise RuntimeError("Cloudx client credential is not unique in gateway config")
    old_pid = int(systemctl("show", args.unit, "-p", "MainPID", "--value", capture=True) or "0")
    host = top_level_value(config_before.data, "host")
    port = int(top_level_value(config_before.data, "port"))
    key = "cloudx-" + secrets.token_urlsafe(36)
    config_after, old_key_count = append_api_key(config_before.data, key)
    if api_keys(config_after) != existing_keys + [key]:
        raise RuntimeError("gateway key append changed an unrelated entry")
    transaction_id, transaction = _prepare_rotation_directory()
    backups = args.config.parent / "backups"
    backup = backups / ("config.yaml.before-cloudx-%s" % transaction_id)
    manifest = {
        "schema": ROTATION_SCHEMA,
        "status": "prepared",
        "transactionId": transaction_id,
        "releaseVersion": args.release_version,
        "artifact": str(artifact),
        "unit": args.unit,
        "config": str(args.config),
        "credential": str(args.credential),
        "environment": str(args.environment),
        "oldCredentialSha256": sha256(old_key.encode("utf-8")),
        "newCredentialSha256": sha256(key.encode("utf-8")),
        "configSha256Before": sha256(config_before.data),
        "configSha256After": sha256(config_after),
        "gatewayKeyCountBefore": old_key_count,
        "gatewayKeyCountAfter": old_key_count + 1,
        "oldPid": old_pid,
        "newPid": 0,
        "gatewayHttpStatus": 0,
        "inotifyWatches": 0,
        "backup": str(backup),
        "previousCredentialRetained": True,
        "previousCredentialRevoked": False,
    }
    try:
        _private_root_directory(backups, "gateway backup directory")
        if backup.exists():
            raise RuntimeError("gateway rotation backup already exists")
        atomic_write(backup, config_before.data, 0o600, 0, 0)
        atomic_json(transaction / "manifest.json", manifest)
    except Exception as exc:
        backup.unlink(missing_ok=True)
        shutil.rmtree(transaction, ignore_errors=True)
        raise RuntimeError("scoped key rotation preparation failed before gateway mutation") from exc

    try:
        environment_after = environment_document(
            str(artifact),
            args.release_version,
            args.build_commit,
            args.gateway_version,
            host,
            port,
        )
        atomic_write(
            args.config,
            config_after,
            config_before.mode,
            config_before.uid,
            config_before.gid,
        )
        atomic_write(args.credential, (key + "\n").encode("utf-8"), 0o600, cloudx.pw_uid, cloudx_group.gr_gid)
        atomic_write(
            args.environment,
            environment_after,
            0o640,
            0,
            cloudx_group.gr_gid,
        )
        systemctl("restart", args.unit)
        new_pid = wait_active(args.unit)
        status = probe(host, port, key)
        watches = inotify_watch_count(new_pid)
        if watches < 2:
            raise RuntimeError("gateway config and auth watches were not restored")
        config_observed = _safe_snapshot(args.config, "gateway config", MAX_CONFIG_BYTES)
        credential_observed = _safe_snapshot(
            args.credential, "Cloudx client credential", MAX_CREDENTIAL_BYTES
        )
        environment_observed = _safe_snapshot(
            args.environment, "Cloudx shadow environment", MAX_CONFIG_BYTES
        )
        if config_observed.data != config_after:
            raise RuntimeError("gateway config changed during scoped key rotation")
        if credential_observed.data != (key + "\n").encode("utf-8"):
            raise RuntimeError("Cloudx client credential changed during scoped key rotation")
        if environment_observed.data != environment_after:
            raise RuntimeError("Cloudx shadow environment changed during scoped key rotation")
        manifest.update({
            "status": "rotated",
            "newPid": new_pid,
            "gatewayHttpStatus": status,
            "inotifyWatches": watches,
        })
        atomic_json(transaction / "manifest.json", manifest)
    except Exception as exc:
        recovery_error: Optional[Exception] = None
        try:
            restore(args.config, config_before)
            restore(args.credential, credential_before)
            restore(args.environment, environment_before)
            systemctl("restart", args.unit)
            wait_active(args.unit)
            rollback_old = probe(host, port, old_key)
            rollback_new = wait_status(host, port, key, 401)
            if rollback_old != 200 or rollback_new != 401:
                raise RuntimeError("restored gateway keys did not pass rotation rollback canaries")
            if _safe_snapshot(args.config, "gateway config", MAX_CONFIG_BYTES) != config_before:
                raise RuntimeError("gateway config was not restored exactly")
            if _safe_snapshot(
                args.credential, "Cloudx client credential", MAX_CREDENTIAL_BYTES
            ) != credential_before:
                raise RuntimeError("Cloudx client credential was not restored exactly")
            if _safe_snapshot(
                args.environment, "Cloudx shadow environment", MAX_CONFIG_BYTES
            ) != environment_before:
                raise RuntimeError("Cloudx shadow environment was not restored exactly")
        except Exception as recovery_exc:
            recovery_error = recovery_exc
        try:
            backup.unlink(missing_ok=True)
            shutil.rmtree(transaction, ignore_errors=True)
        except Exception as cleanup_exc:
            recovery_error = recovery_error or cleanup_exc
        if recovery_error is not None:
            raise RuntimeError(
                "scoped key installation failed and rollback verification is incomplete"
            ) from recovery_error
        raise RuntimeError("scoped key installation failed and was rolled back") from exc

    print(json.dumps({
        "schema": "cloudx.scoped-key-install.v1",
        "status": "installed",
        "unit": args.unit,
        "releaseVersion": args.release_version,
        "oldPid": old_pid,
        "newPid": new_pid,
        "gatewayHttpStatus": status,
        "gatewayKeyCountBefore": old_key_count,
        "gatewayKeyCountAfter": old_key_count + 1,
        "inotifyWatches": watches,
        "configSha256Before": sha256(config_before.data),
        "configSha256After": sha256(config_after),
        "backup": str(backup),
        "transactionId": transaction_id,
        "rotationManifest": str(transaction / "manifest.json"),
        "previousCredentialRetained": True,
        "previousCredentialRevoked": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("install_scoped_gateway_key.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
