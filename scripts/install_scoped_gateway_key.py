#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pathlib
import pwd
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


CONFIRMATION = "RESTART cliproxy.service FOR CLOUDX SCOPED KEY"
DEFAULT_CONFIG = pathlib.Path("/etc/cliproxy/config.yaml")
DEFAULT_CREDENTIAL = pathlib.Path("/etc/cloudx/client-credential")
DEFAULT_ENVIRONMENT = pathlib.Path("/etc/cloudx/cloudx-shadow.env")


@dataclass(frozen=True)
class Snapshot:
    existed: bool
    data: bytes
    mode: int
    uid: int
    gid: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def probe(host: str, port: int, key: str, timeout: float = 20.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
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
                status = int(parts[1]) if len(parts) >= 2 else 0
                if status == 200:
                    return status
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("scoped gateway key did not pass the model probe")


def inotify_watch_count(pid: int) -> int:
    total = 0
    for path in pathlib.Path("/proc/%d/fdinfo" % pid).glob("*"):
        try:
            total += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("inotify wd:"))
        except (OSError, UnicodeDecodeError):
            continue
    return total


def environment_document(artifact: str, commit: str, gateway_version: str, host: str, port: int) -> bytes:
    return ("\n".join([
        "CLOUDX_CLOUD_ARTIFACT=%s" % artifact,
        "CLOUDX_AUTH_DIR=/var/lib/cloudx/shadow-auth",
        "CLOUDX_IMPORT_LOCK=/run/cloudx-shadow/import.lock",
        "CLOUDX_HEALTH_PATH=/run/cloudx-shadow/health.json",
        "CLOUDX_ACCOUNT_STATE_PATH=/run/cloudx-shadow/accounts.json",
        "CLOUDX_ACCOUNT_STATE_SOURCE=/var/lib/codex-quota-monitor/state.json",
        "CLOUDX_GATEWAY_URL=http://%s:%d" % (host, port),
        "CLOUDX_GATEWAY_FORWARD_HOST=%s" % host,
        "CLOUDX_GATEWAY_FORWARD_PORT=%d" % port,
        "CLOUDX_GATEWAY_VERSION=%s" % gateway_version,
        "CLOUDX_CLIENT_CREDENTIAL_FILE=/etc/cloudx/client-credential",
        "CLOUDX_DEPLOYMENT_ID=shadow-0.1.1",
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
    root.add_argument("--artifact", default="/opt/cloudx/releases/0.1.1/cloudx-cloud.pyz")
    root.add_argument("--build-commit", required=True)
    root.add_argument("--gateway-version", required=True)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not args.apply:
        print(json.dumps({
            "schema": "cloudx.scoped-key-plan.v1",
            "status": "confirmation-required",
            "confirmation": CONFIRMATION,
            "unit": args.unit,
            "config": str(args.config),
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("restart confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("installer must run as root")
    if args.config != DEFAULT_CONFIG or args.unit != "cliproxy.service":
        raise RuntimeError("installer is restricted to the declared gateway contract")

    cloudx = pwd.getpwnam("cloudx")
    cloudx_group = grp.getgrnam("cloudx")
    config_before = snapshot(args.config)
    credential_before = snapshot(args.credential)
    environment_before = snapshot(args.environment)
    if not config_before.existed:
        raise RuntimeError("gateway config is missing")
    old_pid = int(systemctl("show", args.unit, "-p", "MainPID", "--value", capture=True) or "0")
    host = top_level_value(config_before.data, "host")
    port = int(top_level_value(config_before.data, "port"))
    key = "cloudx-" + secrets.token_urlsafe(36)
    config_after, old_key_count = append_api_key(config_before.data, key)
    backups = args.config.parent / "backups"
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = backups / ("config.yaml.before-cloudx-%d" % int(time.time()))
    atomic_write(backup, config_before.data, 0o600, 0, 0)

    try:
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
            environment_document(args.artifact, args.build_commit, args.gateway_version, host, port),
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
    except Exception as exc:
        restore(args.config, config_before)
        restore(args.credential, credential_before)
        restore(args.environment, environment_before)
        systemctl("restart", args.unit)
        wait_active(args.unit)
        backup.unlink(missing_ok=True)
        raise RuntimeError("scoped key installation failed and was rolled back") from exc

    print(json.dumps({
        "schema": "cloudx.scoped-key-install.v1",
        "status": "installed",
        "unit": args.unit,
        "oldPid": old_pid,
        "newPid": new_pid,
        "gatewayHttpStatus": status,
        "gatewayKeyCountBefore": old_key_count,
        "gatewayKeyCountAfter": old_key_count + 1,
        "inotifyWatches": watches,
        "configSha256Before": sha256(config_before.data),
        "configSha256After": sha256(config_after),
        "backup": str(backup),
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("install_scoped_gateway_key.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
