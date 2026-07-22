#!/usr/bin/env python3
"""Cold-bootstrap and real-communication helpers for local CPA activation."""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Dict

MAX_BOOTSTRAP_SOURCE_BYTES = 16 * 1024 * 1024
MAX_AUTH_FILE_BYTES = 2 * 1024 * 1024
COMMUNICATION_CANARY_TEXT = "LOCAL_CPA_POLICY_COMMUNICATION_OK"


class SupportRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    mode: int
    uid: int
    gid: int


def _read(path: pathlib.Path, maximum: int) -> Snapshot:
    if not path.is_absolute() or path.is_symlink():
        raise SupportRejected("local CPA bootstrap path is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise SupportRejected("local CPA bootstrap file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise SupportRejected("local CPA bootstrap file is unsafe or oversized")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum:
            raise SupportRejected("local CPA bootstrap file is oversized")
        return Snapshot(raw, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)
    finally:
        os.close(descriptor)


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path: pathlib.Path, raw: bytes, snapshot: Snapshot | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = pathlib.Path(temporary)
    try:
        os.fchmod(descriptor, snapshot.mode if snapshot else 0o600)
        os.fchown(descriptor, snapshot.uid if snapshot else os.geteuid(), snapshot.gid if snapshot else os.getegid())
        os.write(descriptor, raw)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def probe_local_communication(value: Dict[str, Any], *, allow_auth_unavailable: bool = False) -> str:
    codex_binary = value["codexBinary"]
    codex_home = value["communicationCodexHome"]
    if not codex_binary.is_file() or not os.access(codex_binary, os.X_OK):
        raise SupportRejected("official Codex communication canary binary is unavailable")
    if codex_home.is_symlink() or not codex_home.is_dir():
        raise SupportRejected("local CPA communication account is unavailable")
    environment = dict(os.environ)
    environment.update({"HOME": str(pathlib.Path.home().resolve()), "CODEX_HOME": str(codex_home)})
    for name in (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CLOUDX_MODE",
        "CLOUDX_MODE_LEASE_ID", "CLOUDX_MODE_BROKER_PORT", "CODEXX_ACTIVE_ACCOUNT",
        "CODEXX_ACTIVE_HOME", "CODEXX_ACTIVE_PINNED", "HTTP_PROXY", "HTTPS_PROXY",
        "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    ):
        environment.pop(name, None)
    environment.update({"NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1"})
    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-communication-canary-") as temporary:
        try:
            completed = subprocess.run(
                [str(codex_binary), "exec", "--skip-git-repo-check", "Reply with exactly %s" % COMMUNICATION_CANARY_TEXT],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=180.0, check=False, env=environment, cwd=temporary,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SupportRejected("local CPA real Codex communication canary failed") from exc
    output = completed.stdout + "\n" + completed.stderr
    if allow_auth_unavailable and "auth_unavailable: no auth available" in output:
        return "auth-unavailable"
    if completed.returncode != 0 or COMMUNICATION_CANARY_TEXT not in output:
        raise SupportRejected("local CPA real Codex communication canary failed")
    return "passed"


def bootstrap_source(path: pathlib.Path) -> bytes:
    snapshot = _read(path, MAX_BOOTSTRAP_SOURCE_BYTES)
    if not snapshot.data:
        raise SupportRejected("local CPA bootstrap source is empty")
    return snapshot.data


def auth_json_snapshots(directory: pathlib.Path) -> Dict[pathlib.Path, Snapshot]:
    if directory.is_symlink() or not directory.is_dir():
        raise SupportRejected("local CPA auth directory is unsafe")
    paths = sorted(directory.glob("*.json"))
    if len(paths) > 1024:
        raise SupportRejected("local CPA auth inventory is oversized")
    return {path: _read(path, MAX_AUTH_FILE_BYTES) for path in paths}


def restore_auth_json(directory: pathlib.Path, before: Dict[pathlib.Path, Snapshot]) -> None:
    for path in set(directory.glob("*.json")) - set(before):
        if path.is_symlink() or not path.is_file():
            raise SupportRejected("local CPA bootstrap rollback target is unsafe")
        path.unlink()
    for path, snapshot in before.items():
        _write(path, snapshot.data, snapshot)
    _fsync_directory(directory)


def import_bootstrap_agent_identity(value: Dict[str, Any], source: bytes) -> Dict[str, Any]:
    release = pathlib.Path.home() / ".local/lib/cloudx/releases" / value["requiredActiveCloudxVersion"] / "cloudx-local.pyz"
    if release.is_symlink() or not release.is_file():
        raise SupportRejected("release-matched local CPA bootstrap importer is unavailable")
    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-bootstrap-") as temporary:
        source_path = pathlib.Path(temporary) / "agent-identity.json"
        _write(source_path, source)
        try:
            completed = subprocess.run(
                [sys.executable, str(release), "codexx", "import", str(source_path), "--json"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=60.0, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SupportRejected("local CPA bootstrap Agent Identity import failed") from exc
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SupportRejected("local CPA bootstrap importer returned invalid output") from exc
    counts = document.get("counts") if isinstance(document, dict) else None
    if (completed.returncode != 0 or document.get("schema") != "cloudx.local-cpa-import.v1"
            or document.get("status") != "accepted" or not isinstance(counts, dict)
            or int(counts.get("verified", 0)) < 1):
        raise SupportRejected("local CPA bootstrap Agent Identity import failed")
    return document
