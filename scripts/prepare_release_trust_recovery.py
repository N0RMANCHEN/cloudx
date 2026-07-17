#!/usr/bin/env python3
"""Prepare a replacement Cloudx release trust root without publishing or activating."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = "cloudx.release-trust-recovery.v1"
PLAN_SCHEMA = "cloudx.release-trust-recovery-plan.v1"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SIGNER_PATHS = (
    pathlib.Path("release/allowed_signers"),
    pathlib.Path("local/cloudx_local/data/allowed_signers"),
    pathlib.Path("cloud/cloudx_cloud/data/allowed_signers"),
)


class RecoveryRejected(RuntimeError):
    pass


def confirmation(version: str) -> str:
    return "ROTATE CLOUDX RELEASE TRUST %s" % version


def _version(root: pathlib.Path) -> str:
    try:
        value = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RecoveryRejected("repository VERSION is unavailable") from exc
    if not VERSION_RE.fullmatch(value):
        raise RecoveryRejected("repository VERSION is invalid")
    return value


def _signer_bytes(root: pathlib.Path) -> bytes:
    values = []
    for relative in SIGNER_PATHS:
        try:
            value = (root / relative).read_bytes()
        except OSError as exc:
            raise RecoveryRejected("release trust root is unavailable") from exc
        if not value or len(value) > 4096:
            raise RecoveryRejected("release trust root is empty or oversized")
        values.append(value)
    if len(set(values)) != 1:
        raise RecoveryRejected("repository, local, and cloud trust roots differ")
    return values[0]


def _fingerprint(public_data: bytes) -> str:
    completed = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=public_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RecoveryRejected("release trust root is not a valid SSH public key")
    fields = completed.stdout.decode("utf-8", errors="replace").split()
    if len(fields) < 2 or not fields[1].startswith("SHA256:"):
        raise RecoveryRejected("release trust fingerprint is unavailable")
    return fields[1]


def _git_clean(root: pathlib.Path) -> None:
    completed = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RecoveryRejected("repository Git status is unavailable")
    if completed.stdout.strip():
        raise RecoveryRejected("repository must be clean before trust recovery")


def _validate_key_path(root: pathlib.Path, private_key: pathlib.Path) -> pathlib.Path:
    if not private_key.is_absolute():
        raise RecoveryRejected("private key path must be absolute")
    root_resolved = root.resolve()
    resolved = private_key.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        pass
    else:
        raise RecoveryRejected("private key path must remain outside the repository")
    if private_key.exists() or private_key.is_symlink() or private_key.with_suffix(private_key.suffix + ".pub").exists():
        raise RecoveryRejected("private key or public companion already exists")
    parent = private_key.parent
    if parent.is_symlink():
        raise RecoveryRejected("private key directory must not be a symlink")
    existed = parent.exists()
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    mode = stat.S_IMODE(parent.stat().st_mode)
    if existed and mode != 0o700:
        raise RecoveryRejected("existing private key directory must already be mode 0700")
    if not existed and mode != 0o700:
        try:
            parent.chmod(0o700)
        except OSError as exc:
            raise RecoveryRejected("private key directory permissions could not be secured") from exc
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise RecoveryRejected("private key directory must be mode 0700")
    return resolved


def _allowed_signers(public_key: pathlib.Path) -> bytes:
    try:
        fields = public_key.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise RecoveryRejected("generated public key is unavailable") from exc
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise RecoveryRejected("generated release key is not Ed25519")
    return ("cloudx-release %s %s\n" % (fields[0], fields[1])).encode("utf-8")


def _atomic_write(path: pathlib.Path, payload: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".cloudx-trust-", dir=str(path.parent))
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _remove_generated(private_key: pathlib.Path) -> None:
    for path in (private_key, private_key.with_suffix(private_key.suffix + ".pub")):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def plan(root: pathlib.Path = ROOT, version: Optional[str] = None, key_configured: bool = False) -> Dict[str, Any]:
    selected = version or _version(root)
    if selected != _version(root):
        raise RecoveryRejected("requested version must equal repository VERSION")
    current_fingerprint = _fingerprint(_signer_bytes(root))
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "version": selected,
        "currentFingerprint": current_fingerprint,
        "privateKeyConfigured": key_configured,
        "confirmation": confirmation(selected),
        "actions": [
            "generate repository-external Ed25519 private key",
            "set private key mode 0600 and parent mode 0700",
            "derive cloudx-release allowed signer",
            "atomically update repository, local, and cloud public trust roots",
            "verify all public roots and the replacement fingerprint",
        ],
        "forbiddenActions": [
            "commit",
            "tag",
            "publish release",
            "move stable release",
            "stage endpoint",
            "activate endpoint",
            "restart service",
            "remove legacy path",
        ],
        "automaticAction": False,
        "authorization": {
            "keyGeneration": False,
            "trustRootWrite": False,
            "releasePublication": False,
            "endpointStage": False,
            "endpointActivation": False,
            "serviceRestart": False,
        },
    }


def prepare(
    root: pathlib.Path,
    version: str,
    private_key: pathlib.Path,
    *,
    check_git: bool = True,
) -> Dict[str, Any]:
    if version != _version(root):
        raise RecoveryRejected("requested version must equal repository VERSION")
    original = _signer_bytes(root)
    original_fingerprint = _fingerprint(original)
    if check_git:
        _git_clean(root)
    key_path = _validate_key_path(root, private_key)
    originals = {relative: (root / relative).read_bytes() for relative in SIGNER_PATHS}
    changed: List[pathlib.Path] = []
    try:
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "cloudx-release",
                "-f",
                str(key_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise RecoveryRejected("replacement release key generation failed")
        key_path.chmod(0o600)
        public_path = key_path.with_suffix(key_path.suffix + ".pub")
        public_path.chmod(0o644)
        if stat.S_IMODE(key_path.stat().st_mode) != 0o600:
            raise RecoveryRejected("replacement private key is not mode 0600")
        replacement = _allowed_signers(public_path)
        replacement_fingerprint = _fingerprint(replacement)
        if replacement_fingerprint == original_fingerprint:
            raise RecoveryRejected("replacement release key matches the current trust root")
        for relative in SIGNER_PATHS:
            target = root / relative
            _atomic_write(target, replacement, 0o644)
            changed.append(target)
        if _signer_bytes(root) != replacement:
            raise RecoveryRejected("replacement public trust roots do not match")
        if _fingerprint(replacement) != replacement_fingerprint:
            raise RecoveryRejected("replacement public trust fingerprint changed unexpectedly")
    except Exception as exc:
        rollback_failed = False
        for relative in SIGNER_PATHS:
            try:
                _atomic_write(root / relative, originals[relative], 0o644)
            except Exception:
                rollback_failed = True
        _remove_generated(key_path)
        if rollback_failed:
            raise RecoveryRejected("trust recovery failed and public-root rollback was incomplete") from exc
        if isinstance(exc, RecoveryRejected):
            raise
        raise RecoveryRejected("trust recovery failed before preparation completed") from exc
    return {
        "schema": SCHEMA,
        "status": "prepared",
        "version": version,
        "previousFingerprint": original_fingerprint,
        "replacementFingerprint": replacement_fingerprint,
        "privateKeyCreated": True,
        "privateKeyMode": "0600",
        "privateKeyInRepository": False,
        "publicRootsUpdated": len(changed),
        "publicRootsMatch": True,
        "automaticAction": False,
        "authorization": {
            "commit": False,
            "tag": False,
            "releasePublication": False,
            "endpointStage": False,
            "endpointActivation": False,
            "serviceRestart": False,
        },
    }


def main(argv: Optional[Sequence[str]] = None, root: pathlib.Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=_version(root))
    parser.add_argument("--private-key", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if not args.apply:
            result = plan(root, args.version, key_configured=args.private_key is not None)
        else:
            if args.confirm != confirmation(args.version):
                raise RecoveryRejected("trust recovery confirmation does not match")
            if args.private_key is None:
                raise RecoveryRejected("--private-key is required for trust recovery")
            result = prepare(root, args.version, args.private_key)
    except RecoveryRejected as exc:
        print("release-trust-recovery: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
