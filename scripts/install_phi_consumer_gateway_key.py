#!/usr/bin/env python3
"""Install or rotate the dedicated Phi Cloudx gateway credential with rollback."""

from __future__ import annotations

import argparse
import grp
import json
import os
import pathlib
import re
import secrets
import stat
import sys
import time
from typing import Any, Dict, Optional, Sequence

from install_scoped_gateway_key import (
    Snapshot,
    append_api_key,
    atomic_write,
    inotify_watch_count,
    probe,
    snapshot,
    systemctl,
    top_level_value,
    verify_artifact,
    wait_active,
)


CONFIRMATION = "RESTART cliproxy.service FOR PHI CLOUDX CONSUMER KEY"
DEFAULT_CONFIG = pathlib.Path("/etc/cliproxy/config.yaml")
DEFAULT_CREDENTIAL = pathlib.Path("/etc/cloudx/consumers/phi-cloud/credential")
DEFAULT_CLOUDX_CLIENT_CREDENTIAL = pathlib.Path("/etc/cloudx/client-credential")
DEFAULT_GROUP = "phi-cloudx-consumer"
DEFAULT_UNIT = "cliproxy.service"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_CREDENTIAL_BYTES = 4096


def _safe_snapshot(
    path: pathlib.Path,
    label: str,
    *,
    required: bool,
    maximum: int,
) -> Snapshot:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if required:
            raise RuntimeError("%s is missing" % label)
        return Snapshot(False, b"", 0, 0, 0)
    except OSError as exc:
        raise RuntimeError("%s is unavailable" % label) from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("%s must be a regular non-symlink file" % label)
    if metadata.st_size > maximum:
        raise RuntimeError("%s exceeds the size limit" % label)
    return snapshot(path)


def _validate_credential_directory(path: pathlib.Path, group_gid: int) -> None:
    directory = path.parent
    try:
        metadata = directory.lstat()
    except OSError as exc:
        raise RuntimeError("Phi consumer credential directory is unavailable") from exc
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("Phi consumer credential directory must be a real directory")
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid != 0 or metadata.st_gid != group_gid or mode != 0o750:
        raise RuntimeError("Phi consumer credential directory must be root:group mode 0750")


def _restore(path: pathlib.Path, value: Snapshot) -> None:
    if value.existed:
        atomic_write(path, value.data, value.mode, value.uid, value.gid)
    else:
        path.unlink(missing_ok=True)


def _previous_key_is_retained(config: bytes, credential: Snapshot) -> bool:
    if not credential.existed:
        return False
    try:
        key = credential.data.decode("utf-8").strip()
        text = config.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("existing Phi consumer credential is invalid") from exc
    if not key or len(key) > 512 or json.dumps(key) not in text:
        raise RuntimeError("existing Phi consumer credential is not retained by the gateway")
    return True


def plan(release_version: str, artifact: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": "cloudx.phi-consumer-key-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "releaseArtifact": str(artifact),
        "unit": DEFAULT_UNIT,
        "credentialClass": "scoped_phi_consumer",
        "credentialPath": str(DEFAULT_CREDENTIAL),
        "credentialGroup": DEFAULT_GROUP,
        "gatewayRestartRequired": True,
        "phiServiceRestartRequired": False,
        "preconditions": [
            "signed_cloud_artifact_staged",
            "phi_consumer_group_exists",
            "credential_directory_root_group_0750",
            "cloudx_client_credential_private",
        ],
        "automaticAction": False,
        "authorization": {
            "gatewayConfigWrite": False,
            "credentialWrite": False,
            "gatewayRestart": False,
            "phiServiceRestart": False,
            "previousCredentialRevocation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    root.add_argument("--artifact", type=pathlib.Path)
    root.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    root.add_argument("--credential", type=pathlib.Path, default=DEFAULT_CREDENTIAL)
    root.add_argument(
        "--cloudx-client-credential",
        type=pathlib.Path,
        default=DEFAULT_CLOUDX_CLIENT_CREDENTIAL,
    )
    root.add_argument("--consumer-group", default=DEFAULT_GROUP)
    root.add_argument("--unit", default=DEFAULT_UNIT)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
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
        or args.credential != DEFAULT_CREDENTIAL
        or args.cloudx_client_credential != DEFAULT_CLOUDX_CLIENT_CREDENTIAL
        or args.consumer_group != DEFAULT_GROUP
        or args.unit != DEFAULT_UNIT
    ):
        raise RuntimeError("Phi consumer key installer is restricted to the declared contract")
    if not args.apply:
        print(json.dumps(plan(args.release_version, artifact), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("Phi consumer key confirmation does not match")
    if os.geteuid() != 0:
        raise RuntimeError("Phi consumer key installer must run as root")
    verify_artifact(artifact, args.release_version)
    try:
        consumer_group = grp.getgrnam(DEFAULT_GROUP)
    except KeyError as exc:
        raise RuntimeError("Phi consumer credential group is missing") from exc
    _validate_credential_directory(args.credential, consumer_group.gr_gid)

    config_before = _safe_snapshot(
        args.config,
        "gateway config",
        required=True,
        maximum=MAX_CONFIG_BYTES,
    )
    credential_before = _safe_snapshot(
        args.credential,
        "Phi consumer credential",
        required=False,
        maximum=MAX_CREDENTIAL_BYTES,
    )
    if credential_before.existed and (
        credential_before.mode != 0o640
        or credential_before.uid != 0
        or credential_before.gid != consumer_group.gr_gid
    ):
        raise RuntimeError("existing Phi consumer credential ownership or mode is invalid")
    cloudx_client_before = _safe_snapshot(
        args.cloudx_client_credential,
        "Cloudx client credential",
        required=True,
        maximum=MAX_CREDENTIAL_BYTES,
    )
    if cloudx_client_before.mode & 0o077:
        raise RuntimeError("Cloudx client credential permissions are too broad")
    previous_retained = _previous_key_is_retained(config_before.data, credential_before)
    old_pid = int(systemctl("show", args.unit, "-p", "MainPID", "--value", capture=True) or "0")
    host = top_level_value(config_before.data, "host")
    port = int(top_level_value(config_before.data, "port"))
    key = "cloudx-phi-" + secrets.token_urlsafe(36)
    config_after, old_key_count = append_api_key(config_before.data, key)
    backups = args.config.parent / "backups"
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = backups / ("config.yaml.before-phi-consumer-%d" % time.time_ns())
    atomic_write(backup, config_before.data, 0o600, 0, 0)

    try:
        atomic_write(
            args.config,
            config_after,
            config_before.mode,
            config_before.uid,
            config_before.gid,
        )
        atomic_write(
            args.credential,
            (key + "\n").encode("utf-8"),
            0o640,
            0,
            consumer_group.gr_gid,
        )
        systemctl("restart", args.unit)
        new_pid = wait_active(args.unit)
        status = probe(host, port, key)
        watches = inotify_watch_count(new_pid)
        if watches < 2:
            raise RuntimeError("gateway config and auth watches were not restored")
        cloudx_client_after = _safe_snapshot(
            args.cloudx_client_credential,
            "Cloudx client credential",
            required=True,
            maximum=MAX_CREDENTIAL_BYTES,
        )
        if cloudx_client_after != cloudx_client_before:
            raise RuntimeError("Cloudx client credential changed during Phi credential install")
    except Exception as exc:
        _restore(args.config, config_before)
        _restore(args.credential, credential_before)
        systemctl("restart", args.unit)
        wait_active(args.unit)
        backup.unlink(missing_ok=True)
        raise RuntimeError("Phi consumer key installation failed and was rolled back") from exc

    print(json.dumps({
        "schema": "cloudx.phi-consumer-key-install.v1",
        "status": "installed",
        "releaseVersion": args.release_version,
        "unit": args.unit,
        "credentialClass": "scoped_phi_consumer",
        "credentialMode": "0640",
        "credentialGroup": DEFAULT_GROUP,
        "oldPid": old_pid,
        "newPid": new_pid,
        "gatewayHttpStatus": status,
        "gatewayKeyCountBefore": old_key_count,
        "gatewayKeyCountAfter": old_key_count + 1,
        "inotifyWatches": watches,
        "cloudxClientCredentialUnchanged": True,
        "previousCredentialRetained": previous_retained,
        "previousCredentialRevoked": False,
        "phiServiceRestarted": False,
        "backup": str(backup),
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("install_phi_consumer_gateway_key.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
