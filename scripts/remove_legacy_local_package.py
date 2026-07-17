#!/usr/bin/env python3
"""Quarantine the live local codex-plus package while retaining rollback."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import pwd
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple


CONFIRMATION = "QUARANTINE LOCAL CODEX-PLUS PACKAGE WITH AUTOMATIC RESTORE"
VERSION_RE = __import__("re").compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
BACKUP_ID_RE = __import__("re").compile(r"^[0-9]{8}T[0-9]{6}Z$")
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILES = 10000
TARGETS = (
    ("legacyRuntime", pathlib.PurePosixPath(".local/bin/codexx_app")),
    ("legacyLauncher", pathlib.PurePosixPath(".local/bin/codexx.py")),
    ("recoveryEntrypoint", pathlib.PurePosixPath(".local/bin/codexx-legacy")),
)


@dataclass(frozen=True)
class FileRecord:
    relative: str
    size: int
    mode: int
    sha256: str


def user_home() -> pathlib.Path:
    return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)


def _private_directory(path: pathlib.Path, label: str) -> pathlib.Path:
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("%s is unsafe" % label)
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("%s permissions are too broad" % label)
    return path


@contextmanager
def _transaction_lock(home: pathlib.Path) -> Iterator[None]:
    state = _private_directory(home / ".local/state/cloudx", "legacy removal state directory")
    lock = state / "legacy-local-removal.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("legacy removal lock is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise RuntimeError("legacy removal lock ownership is invalid")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("legacy removal lock permissions are too broad")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _safe_file(path: pathlib.Path, label: str, maximum: int) -> Tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("%s is unavailable or unsafe" % label) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("%s must be a regular non-symlink file" % label)
        if metadata.st_size > maximum:
            raise RuntimeError("%s exceeds the size limit" % label)
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise RuntimeError("%s exceeds the size limit" % label)
        return raw, metadata
    finally:
        os.close(descriptor)


def _tree_records(path: pathlib.Path) -> List[FileRecord]:
    try:
        root = path.lstat()
    except OSError as exc:
        raise RuntimeError("legacy runtime is unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(root.st_mode):
        raise RuntimeError("legacy runtime must be a real directory")
    records = []
    total = 0
    for candidate in sorted(path.rglob("*"), key=lambda item: str(item)):
        metadata = candidate.lstat()
        if candidate.is_symlink():
            raise RuntimeError("legacy runtime contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("legacy runtime contains a non-regular file")
        if metadata.st_size > MAX_FILE_BYTES:
            raise RuntimeError("legacy runtime file exceeds the size limit")
        total += metadata.st_size
        if total > MAX_TOTAL_BYTES or len(records) >= MAX_FILES:
            raise RuntimeError("legacy runtime inventory exceeds the bounded limit")
        raw, opened = _safe_file(candidate, "legacy runtime file", MAX_FILE_BYTES)
        if opened.st_ino != metadata.st_ino:
            raise RuntimeError("legacy runtime changed during inventory")
        records.append(FileRecord(
            relative=str(candidate.relative_to(path)),
            size=len(raw),
            mode=stat.S_IMODE(opened.st_mode),
            sha256=hashlib.sha256(raw).hexdigest(),
        ))
    if not records:
        raise RuntimeError("legacy runtime is empty")
    return records


def _recovery_bundle(home: pathlib.Path) -> Tuple[pathlib.Path, Mapping[str, Any]]:
    entrypoint = home / ".local/bin/codexx-legacy"
    try:
        metadata = entrypoint.lstat()
        target = entrypoint.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("legacy recovery entrypoint is unavailable") from exc
    if not stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("legacy recovery entrypoint must be a symlink")
    backups = home / ".local/state/cloudx/legacy-backups"
    try:
        backup_metadata = backups.lstat()
        resolved_backups = backups.resolve(strict=True)
        relative = target.relative_to(resolved_backups)
    except (OSError, ValueError) as exc:
        raise RuntimeError("legacy recovery entrypoint escapes the private backup root") from exc
    if backups.is_symlink() or not stat.S_ISDIR(backup_metadata.st_mode):
        raise RuntimeError("legacy recovery backup root is unsafe")
    if backup_metadata.st_uid != os.geteuid() or stat.S_IMODE(backup_metadata.st_mode) & 0o022:
        raise RuntimeError("legacy recovery backup root is writable by another identity")
    if (
        len(relative.parts) != 5
        or not BACKUP_ID_RE.fullmatch(relative.parts[0])
        or relative.parts[1:] != ("home", ".local", "bin", "codexx")
    ):
        raise RuntimeError("legacy recovery entrypoint targets an unexpected launcher")
    bundle = resolved_backups / relative.parts[0]
    bundle_metadata = bundle.lstat()
    if bundle.is_symlink() or not stat.S_ISDIR(bundle_metadata.st_mode):
        raise RuntimeError("legacy recovery bundle is unsafe")
    if bundle_metadata.st_uid != os.geteuid() or stat.S_IMODE(bundle_metadata.st_mode) & 0o077:
        raise RuntimeError("legacy recovery bundle permissions are too broad")
    manifest_path = bundle / "manifest.json"
    raw, manifest_metadata = _safe_file(manifest_path, "legacy recovery manifest", MAX_MANIFEST_BYTES)
    if stat.S_IMODE(manifest_metadata.st_mode) & 0o077:
        raise RuntimeError("legacy recovery manifest permissions are too broad")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("legacy recovery manifest is invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != "cloudx.legacy-local-backup.v1"
        or document.get("home") != str(home)
        or not isinstance(document.get("files"), list)
    ):
        raise RuntimeError("legacy recovery manifest contract is invalid")
    return bundle, document


def _verify_recovery_copy(
    home: pathlib.Path,
    runtime_records: Sequence[FileRecord],
    launcher_sha256: str,
    manifest: Mapping[str, Any],
) -> None:
    indexed = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise RuntimeError("legacy recovery manifest contains an invalid record")
        source = item.get("source")
        digest = item.get("sha256")
        if not isinstance(source, str) or not isinstance(digest, str):
            raise RuntimeError("legacy recovery manifest contains an invalid record")
        indexed[source] = digest
    launcher = str(home / ".local/bin/codexx.py")
    if indexed.get(launcher) != launcher_sha256:
        raise RuntimeError("legacy launcher does not match the private recovery bundle")
    runtime_root = home / ".local/bin/codexx_app"
    checked = 0
    for record in runtime_records:
        if "__pycache__" in pathlib.PurePosixPath(record.relative).parts or record.relative.endswith(".pyc"):
            continue
        source = str(runtime_root / record.relative)
        if indexed.get(source) != record.sha256:
            raise RuntimeError("legacy runtime does not match the private recovery bundle")
        checked += 1
    if checked == 0:
        raise RuntimeError("legacy recovery comparison covered no runtime files")


def _active_release(home: pathlib.Path, version: str) -> Tuple[pathlib.Path, Dict[str, str]]:
    release_root = home / ".local/lib/cloudx/releases"
    selectors = {}
    for name in ("current", "previous"):
        path = home / ".local/lib/cloudx" / name
        try:
            metadata = path.lstat()
            target = path.resolve(strict=True)
            relative = target.relative_to(release_root)
        except (OSError, ValueError) as exc:
            raise RuntimeError("local Cloudx selector is unavailable or unsafe") from exc
        if not stat.S_ISLNK(metadata.st_mode) or len(relative.parts) != 1 or not VERSION_RE.fullmatch(relative.parts[0]):
            raise RuntimeError("local Cloudx selector does not name an exact release")
        selectors[name] = relative.parts[0]
    if selectors["current"] != version:
        raise RuntimeError("the requested native-import release is not active")
    artifact = release_root / version / "cloudx-local.pyz"
    completed = subprocess.run(
        [sys.executable, str(artifact), "self-check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20.0,
        check=False,
    )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("active local artifact self-check is invalid") from exc
    if (
        completed.returncode != 0
        or document.get("schema") != "cloudx.self-check.v1"
        or document.get("component") != "local"
        or document.get("version") != version
        or document.get("status") != "ok"
    ):
        raise RuntimeError("active local artifact does not match the removal release")
    return artifact, selectors


def _shell_snapshot(home: pathlib.Path) -> Dict[str, Any]:
    zshrc = home / ".zshrc"
    raw, metadata = _safe_file(zshrc, "zsh configuration", 1024 * 1024)
    text = raw.decode("utf-8")
    if text.count("# cloudx shell hook start") != 1 or text.count("# cloudx shell hook end") != 1:
        raise RuntimeError("zsh configuration does not have one Cloudx hook")
    for marker in ("# codexx shell hook start", "# >>> codexx >>>", "source ~/.local/bin/codexx"):
        if marker in text:
            raise RuntimeError("zsh configuration still contains a legacy hook")
    entrypoints = {}
    for name in ("codexx", "cloud", "cloudx-update"):
        path = home / ".local/bin" / name
        try:
            link_metadata = path.lstat()
            target = os.readlink(path)
        except OSError as exc:
            raise RuntimeError("Cloudx local entrypoint is unavailable") from exc
        if not stat.S_ISLNK(link_metadata.st_mode):
            raise RuntimeError("Cloudx local entrypoint must be a symlink")
        entrypoints[name] = target
    return {
        "zshrcSha256": hashlib.sha256(raw).hexdigest(),
        "zshrcMode": stat.S_IMODE(metadata.st_mode),
        "entrypoints": entrypoints,
    }


def _port_open(port: int) -> bool:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(0.25)
        return connection.connect_ex(("127.0.0.1", port)) == 0
    finally:
        connection.close()


def _process_inventory(home: pathlib.Path) -> Tuple[List[str], Dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,lstart=,command="],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20.0,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 8 * 1024 * 1024:
        raise RuntimeError("local process inventory is unavailable")
    runtime = str(home / ".local/bin/codexx_app")
    launcher = str(home / ".local/bin/codexx.py")
    legacy = []
    cpa = []
    for line in completed.stdout.splitlines():
        if runtime in line or launcher in line:
            legacy.append(line.strip())
        if str(home / ".local/bin/cli-proxy-api") in line:
            cpa.append(line.strip())
    if len(cpa) != 1:
        raise RuntimeError("external local CPA process identity is ambiguous")
    fields = cpa[0].split(None, 2)
    if len(fields) < 3:
        raise RuntimeError("external local CPA process identity is invalid")
    return legacy, {"pid": int(fields[0]), "identity": cpa[0]}


def _native_import_dry_run(artifact: pathlib.Path) -> None:
    fixture = {
        "type": "codex",
        "email": "cloudx-removal-canary@example.test",
        "access_token": "header.fixture.signature",
        "refresh_token": "refresh.fixture.signature",
        "id_token": "id.fixture.signature",
        "account_id": "cloudx-removal-canary",
    }
    with tempfile.TemporaryDirectory(prefix="cloudx-legacy-removal-canary-") as value:
        source = pathlib.Path(value) / "credential.json"
        source.write_text(json.dumps(fixture), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(artifact), "import", str(source), "--dry-run", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30.0,
            check=False,
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("native local import dry-run returned invalid JSON") from exc
    counts = document.get("counts", {})
    if (
        completed.returncode != 0
        or document.get("schema") != "cloudx.local-cpa-import.v1"
        or document.get("status") != "preview"
        or document.get("dryRun") is not True
        or document.get("adapter") != "cloudx_native_compatibility"
        or document.get("errors") != []
        or not isinstance(counts.get("parsed"), int)
        or counts["parsed"] < 1
        or document.get("externalService") != {"managed": False, "restarted": False}
    ):
        raise RuntimeError("native local import dry-run was not accepted")


def _fresh_shell(home: pathlib.Path) -> None:
    path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    expected_codex = shutil.which("codex", path=path)
    if not expected_codex or expected_codex.startswith(str(home)):
        raise RuntimeError("official Codex executable is unavailable")
    script = "\n".join([
        "set -e",
        "source \"$HOME/.zshrc\"",
        "[[ \"$(whence -p codex)\" = \"$EXPECTED_CODEX\" ]]",
        "[[ \"$(whence -p git)\" = \"/usr/bin/git\" ]]",
        "[[ \"$(whence -w codexx)\" = \"codexx: function\" ]]",
        "codexx api >/dev/null",
        "[[ \"$CODEXX_ACTIVE_ACCOUNT\" = \"api\" ]]",
        "codexx exit >/dev/null",
        "[[ \"$CODEXX_ACTIVE_ACCOUNT\" = \"native\" ]]",
        "print -r -- accepted",
    ])
    environment = {
        "HOME": str(home),
        "USER": pwd.getpwuid(os.getuid()).pw_name,
        "LOGNAME": pwd.getpwuid(os.getuid()).pw_name,
        "PATH": path,
        "SHELL": "/bin/zsh",
        "EXPECTED_CODEX": expected_codex,
        "CLOUDX_DISABLE_UPDATE_CHECK": "1",
    }
    completed = subprocess.run(
        ["/bin/zsh", "-f", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        timeout=30.0,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "accepted":
        raise RuntimeError("fresh-shell Cloudx acceptance failed")


def _prepare_quarantine(
    home: pathlib.Path,
    runtime: Sequence[FileRecord],
    launcher_sha256: str,
    recovery_bundle: pathlib.Path,
) -> Tuple[str, pathlib.Path]:
    backup_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise RuntimeError("legacy removal backup identity is invalid")
    parent = _private_directory(
        home / ".local/state/cloudx/legacy-removal-backups",
        "legacy removal backup directory",
    )
    root = parent / backup_id
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    manifest = {
        "schema": "cloudx.legacy-local-removal-backup.v1",
        "backupId": backup_id,
        "releaseScope": "current_user_home",
        "runtimeFileCount": len(runtime),
        "runtimeTotalBytes": sum(item.size for item in runtime),
        "runtimeTreeSha256": hashlib.sha256(
            "\n".join("%s:%s" % (item.relative, item.sha256) for item in runtime).encode("utf-8")
        ).hexdigest(),
        "launcherSha256": launcher_sha256,
        "recoveryBundleRetained": True,
        "recoveryBundleId": recovery_bundle.name,
        "targets": [name for name, _relative in TARGETS],
    }
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest.", dir=str(root))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, root / "manifest.json")
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise
    return backup_id, root


def _move_targets(home: pathlib.Path, quarantine: pathlib.Path) -> List[Tuple[pathlib.Path, pathlib.Path]]:
    moved = []
    destination = quarantine / "live"
    destination.mkdir(mode=0o700)
    try:
        for name, relative in TARGETS:
            source = home / relative
            target = destination / name
            if source.lstat().st_dev != destination.lstat().st_dev:
                raise RuntimeError("legacy removal target is not on the quarantine filesystem")
            os.replace(source, target)
            moved.append((source, target))
    except Exception:
        for source, target in reversed(moved):
            os.replace(target, source)
        raise
    return moved


def _restore_targets(moved: Iterable[Tuple[pathlib.Path, pathlib.Path]]) -> None:
    errors = []
    for source, target in reversed(list(moved)):
        try:
            os.replace(target, source)
        except OSError:
            errors.append(source.name)
    if errors:
        raise RuntimeError("legacy local target restoration was incomplete")


def plan(release_version: str) -> Dict[str, Any]:
    return {
        "schema": "cloudx.legacy-local-removal-plan.v1",
        "status": "confirmation-required",
        "confirmation": CONFIRMATION,
        "releaseVersion": release_version,
        "endpointScope": "current_user_home",
        "targets": [name for name, _relative in TARGETS],
        "preserved": [
            "cloudx_entrypoints",
            "cloudx_shell_hook",
            "official_codex",
            "official_git",
            "external_local_cpa",
            "local_cpa_launch_agent",
            "local_cpa_configuration",
            "account_profiles",
            "private_recovery_bundle",
        ],
        "automaticAction": False,
        "preconditions": [
            "native_import_release_active",
            "private_recovery_bundle_verified",
            "no_legacy_processes",
            "legacy_port_18317_closed",
            "external_local_cpa_healthy",
            "fresh_shell_acceptance",
        ],
        "authorization": {
            "legacyRuntimeQuarantine": False,
            "legacyLauncherQuarantine": False,
            "recoveryEntrypointQuarantine": False,
            "shellHookWrite": False,
            "cloudxEntrypointWrite": False,
            "accountProfileMutation": False,
            "localCpaMutation": False,
            "processTermination": False,
            "serviceRestart": False,
            "recoveryBundleRemoval": False,
            "quarantineRemoval": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--apply", action="store_true")
    root.add_argument("--confirm", default="")
    root.add_argument("--release-version", required=True)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not VERSION_RE.fullmatch(args.release_version):
        raise RuntimeError("release version must be an exact semantic version")
    if not args.apply:
        print(json.dumps(plan(args.release_version), sort_keys=True, separators=(",", ":")))
        return 0
    if args.confirm != CONFIRMATION:
        raise RuntimeError("legacy local removal confirmation does not match")

    home = user_home()
    with _transaction_lock(home):
        artifact, selectors_before = _active_release(home, args.release_version)
        shell_before = _shell_snapshot(home)
        legacy_processes, cpa_before = _process_inventory(home)
        if legacy_processes:
            raise RuntimeError("legacy codex-plus processes are still active")
        if _port_open(18317):
            raise RuntimeError("legacy local tunnel port 18317 is still listening")
        if not _port_open(8317):
            raise RuntimeError("external local CPA port 8317 is unavailable")
        runtime_path = home / ".local/bin/codexx_app"
        runtime = _tree_records(runtime_path)
        launcher_raw, launcher_metadata = _safe_file(
            home / ".local/bin/codexx.py",
            "legacy launcher",
            MAX_FILE_BYTES,
        )
        if stat.S_IMODE(launcher_metadata.st_mode) & 0o022:
            raise RuntimeError("legacy launcher permissions are too broad")
        launcher_sha256 = hashlib.sha256(launcher_raw).hexdigest()
        recovery_bundle, recovery_manifest = _recovery_bundle(home)
        _verify_recovery_copy(home, runtime, launcher_sha256, recovery_manifest)
        _native_import_dry_run(artifact)
        _fresh_shell(home)

        backup_id, quarantine = _prepare_quarantine(
            home,
            runtime,
            launcher_sha256,
            recovery_bundle,
        )
        moved: List[Tuple[pathlib.Path, pathlib.Path]] = []
        try:
            moved = _move_targets(home, quarantine)
            if any((home / relative).exists() or (home / relative).is_symlink() for _name, relative in TARGETS):
                raise RuntimeError("legacy local target remained live after quarantine")
            _fresh_shell(home)
            _native_import_dry_run(artifact)
            if _active_release(home, args.release_version)[1] != selectors_before:
                raise RuntimeError("local Cloudx selectors changed during legacy removal")
            if _shell_snapshot(home) != shell_before:
                raise RuntimeError("Cloudx shell or entrypoints changed during legacy removal")
            legacy_after, cpa_after = _process_inventory(home)
            if legacy_after or cpa_after != cpa_before or not _port_open(8317):
                raise RuntimeError("external local CPA continuity changed during legacy removal")
        except Exception as exc:
            recovery_errors = []
            if moved:
                try:
                    _restore_targets(moved)
                except Exception:  # pragma: no cover - hard failure path
                    recovery_errors.append("legacy target restore failed")
            try:
                if _active_release(home, args.release_version)[1] != selectors_before:
                    recovery_errors.append("local selector continuity changed")
                if _shell_snapshot(home) != shell_before:
                    recovery_errors.append("shell continuity changed")
                _legacy, cpa_recovered = _process_inventory(home)
                if cpa_recovered != cpa_before or not _port_open(8317):
                    recovery_errors.append("external CPA continuity changed")
            except Exception:  # pragma: no cover - hard recovery audit
                recovery_errors.append("recovery audit failed")
            if not recovery_errors:
                shutil.rmtree(quarantine)
                raise RuntimeError("legacy local removal failed and live paths were restored") from exc
            raise RuntimeError(
                "legacy local removal failed; recovery incomplete: %s"
                % "; ".join(recovery_errors)
            ) from exc

    print(json.dumps({
        "schema": "cloudx.legacy-local-removal.v1",
        "status": "quarantined",
        "releaseVersion": args.release_version,
        "endpointScope": "current_user_home",
        "backupId": backup_id,
        "targetsQuarantined": len(TARGETS),
        "freshShellAccepted": True,
        "nativeImportDryRunAccepted": True,
        "officialCodexPreserved": True,
        "officialGitPreserved": True,
        "cloudxEntrypointsUnchanged": True,
        "shellHookUnchanged": True,
        "externalLocalCpaUnchanged": True,
        "accountProfilesRetained": True,
        "localCpaLaunchAgentRetained": True,
        "localCpaConfigurationRetained": True,
        "privateRecoveryBundleRetained": True,
        "legacyRuntimeLive": False,
        "legacyLauncherLive": False,
        "recoveryEntrypointLive": False,
        "processTerminated": False,
        "serviceRestarted": False,
        "quarantineRetained": True,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("remove_legacy_local_package.py: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
