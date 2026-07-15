#!/usr/bin/env python3
"""Create a private recovery bundle for the local codex-plus API/CPA path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import pwd
import stat
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CONFIRMATION = "BACK UP LOCAL CODEX-PLUS API AND CPA"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def user_home() -> pathlib.Path:
    return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)


def runtime_paths(home: pathlib.Path) -> List[pathlib.Path]:
    runtime = home / ".local/bin/codexx_app"
    if not runtime.is_dir() or runtime.is_symlink():
        return []
    return [
        path
        for path in sorted(runtime.rglob("*"))
        if (path.is_file() or path.is_symlink()) and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]


def candidate_paths(home: pathlib.Path) -> List[pathlib.Path]:
    relative = [
        ".zshrc",
        ".local/bin/codexx",
        ".local/bin/codexx.py",
        ".local/bin/cli-proxy-api",
        ".config/codexx/config.toml",
        "Library/LaunchAgents/com.codexx.cliproxyapi.plist",
        ".codex-accounts/api/.codex/auth.json",
        ".codex-accounts/api/.codex/config.toml",
        ".codex-accounts/api/.local/bin/codexx",
        ".codex-accounts/api/.local/bin/git",
        ".codex-accounts/cpa/.codex/auth.json",
        ".codex-accounts/cpa/.codex/config.toml",
    ]
    paths = [home / name for name in relative]
    cpa = home / ".cli-proxy-api"
    if cpa.is_dir() and not cpa.is_symlink():
        paths.extend(path for path in sorted(cpa.iterdir()) if path.is_file() or path.is_symlink())
    paths.extend(runtime_paths(home))
    unique = {str(path): path for path in paths}
    return [unique[name] for name in sorted(unique)]


def source_metadata(paths: Iterable[pathlib.Path]) -> List[Tuple[pathlib.Path, os.stat_result]]:
    result = []
    total = 0
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("legacy backup source must be a regular file: %s" % path)
        if metadata.st_size > MAX_FILE_BYTES:
            raise RuntimeError("legacy backup source exceeds 64 MiB: %s" % path)
        total += metadata.st_size
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError("legacy backup exceeds 128 MiB")
        result.append((path, metadata))
    if not result:
        raise RuntimeError("no legacy API or CPA files were found")
    return result


def read_regular(path: pathlib.Path, expected: os.stat_result) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_ino != expected.st_ino:
            raise RuntimeError("legacy backup source changed during read: %s" % path)
        if opened.st_size > MAX_FILE_BYTES:
            raise RuntimeError("legacy backup source exceeds 64 MiB: %s" % path)
        with os.fdopen(descriptor, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
        descriptor = -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > MAX_FILE_BYTES:
        raise RuntimeError("legacy backup source exceeds 64 MiB: %s" % path)
    return raw


def atomic_write(path: pathlib.Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    try:
        os.fchmod(descriptor, mode)
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


def create_backup(home: pathlib.Path, destination: pathlib.Path) -> Dict[str, Any]:
    sources = source_metadata(candidate_paths(home))
    destination.mkdir(parents=True, mode=0o700)
    destination.chmod(0o700)
    records = []
    total = 0
    for source, metadata in sources:
        raw = read_regular(source, metadata)
        relative = source.relative_to(home)
        target = destination / "home" / relative
        mode = stat.S_IMODE(metadata.st_mode)
        atomic_write(target, raw, mode)
        total += len(raw)
        records.append({
            "source": str(source),
            "backup": str(target.relative_to(destination)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "mode": "%04o" % mode,
        })
    document = {
        "schema": "cloudx.legacy-local-backup.v1",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "home": str(home),
        "fileCount": len(records),
        "totalBytes": total,
        "files": records,
    }
    manifest = destination / "manifest.json"
    atomic_write(manifest, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return {
        "schema": "cloudx.legacy-local-backup-result.v1",
        "status": "created",
        "backup": str(destination),
        "manifest": str(manifest),
        "fileCount": len(records),
        "totalBytes": total,
    }


def augment_runtime(home: pathlib.Path, destination: pathlib.Path) -> Dict[str, Any]:
    manifest = destination / "manifest.json"
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("legacy backup manifest is unavailable or invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != "cloudx.legacy-local-backup.v1":
        raise RuntimeError("legacy backup manifest schema is unsupported")
    records = document.get("files")
    if not isinstance(records, list):
        raise RuntimeError("legacy backup manifest has no file records")
    existing = {str(item.get("backup")) for item in records if isinstance(item, dict)}
    added = 0
    total = int(document.get("totalBytes") or 0)
    for source in candidate_paths(home):
        relative = source.relative_to(home)
        target = destination / "home" / relative
        backup_name = str(target.relative_to(destination))
        if backup_name in existing:
            continue
        if not source.exists() and not source.is_symlink():
            continue
        metadata = source_metadata([source])[0][1]
        raw = read_regular(source, metadata)
        if total + len(raw) > MAX_TOTAL_BYTES:
            raise RuntimeError("legacy backup exceeds 128 MiB")
        mode = stat.S_IMODE(metadata.st_mode)
        atomic_write(target, raw, mode)
        total += len(raw)
        added += 1
        records.append({
            "source": str(source),
            "backup": backup_name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "mode": "%04o" % mode,
        })
    document["files"] = sorted(records, key=lambda item: str(item.get("backup")))
    document["fileCount"] = len(document["files"])
    document["totalBytes"] = total
    document["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    atomic_write(manifest, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return {
        "schema": "cloudx.legacy-local-backup-result.v1",
        "status": "augmented",
        "backup": str(destination),
        "manifest": str(manifest),
        "addedFiles": added,
        "fileCount": document["fileCount"],
        "totalBytes": total,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Back up the local codex-plus API and CPA recovery path")
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--augment-runtime", type=pathlib.Path)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    home = user_home()
    if args.augment_runtime:
        if not args.apply:
            print(json.dumps({
                "schema": "cloudx.legacy-local-backup-plan.v1",
                "status": "confirmation-required",
                "confirmation": CONFIRMATION,
                "operation": "augment-runtime",
                "backup": str(args.augment_runtime),
                "candidateFileCount": len(candidate_paths(home)),
            }, sort_keys=True, separators=(",", ":")))
            return 0
        if args.confirm != CONFIRMATION:
            raise RuntimeError("legacy local backup confirmation does not match")
        print(json.dumps(augment_runtime(home, args.augment_runtime), sort_keys=True, separators=(",", ":")))
        return 0
    sources = source_metadata(candidate_paths(home))
    if not args.apply:
        print(json.dumps({
            "schema": "cloudx.legacy-local-backup-plan.v1",
            "status": "confirmation-required",
            "confirmation": CONFIRMATION,
            "fileCount": len(sources),
            "totalBytes": sum(metadata.st_size for _, metadata in sources),
            "includes": [
                "legacy codexx entrypoints and shell configuration",
                "legacy codexx_app runtime package",
                "api and cpa account profiles",
                "local CLIProxyAPI binary, launchd definition, config, and top-level credentials",
            ],
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("legacy local backup confirmation does not match")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = home / ".local/state/cloudx/legacy-backups" / timestamp
    print(json.dumps(create_backup(home, destination), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("backup_legacy_local.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
