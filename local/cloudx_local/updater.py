from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import pkgutil
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Sequence, Tuple

from .config import LocalConfig
from .files import atomic_json, atomic_write, ensure_private_directory
from .remote import RemoteClient
from .version import VERSION


MAX_BUNDLE_BYTES = 64 * 1024 * 1024
SIGNING_IDENTITY = "cloudx-release"
SIGNING_NAMESPACE = "cloudx-release"
VERSION_RE = re.compile(r"^v?([0-9]+\.[0-9]+\.[0-9]+)$")


def _version_tuple(value: str) -> Tuple[int, int, int]:
    match = VERSION_RE.match(value)
    if not match:
        raise RuntimeError("invalid release version: %s" % value)
    return tuple(int(part) for part in match.group(1).split("."))  # type: ignore[return-value]


def _trusted_signers() -> bytes:
    data = pkgutil.get_data("cloudx_local", "data/allowed_signers")
    if not data:
        raise RuntimeError("release signer trust root is missing")
    return data


def _shell_hook() -> bytes:
    data = pkgutil.get_data("cloudx_local", "data/cloudx.zsh")
    if not data:
        raise RuntimeError("Cloudx shell hook is missing")
    return data


def _digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _verify_signature(document: pathlib.Path, signature: pathlib.Path) -> None:
    with tempfile.NamedTemporaryFile(prefix="cloudx-signers-", delete=False) as handle:
        handle.write(_trusted_signers())
        signers = pathlib.Path(handle.name)
    try:
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(signers),
                "-I",
                SIGNING_IDENTITY,
                "-n",
                SIGNING_NAMESPACE,
                "-s",
                str(signature),
            ],
            input=document.read_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        signers.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise RuntimeError("release signature verification failed")


def _safe_extract(raw: bytes, destination: pathlib.Path) -> None:
    if len(raw) > MAX_BUNDLE_BYTES:
        raise RuntimeError("release bundle exceeds 64 MiB")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            path = pathlib.PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError("release bundle contains an unsafe path")
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise RuntimeError("release bundle contains an unsupported member")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("release bundle member could not be read")
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)


@contextlib.contextmanager
def release_source(source: pathlib.Path) -> Iterator[pathlib.Path]:
    if source.is_dir():
        yield source
        return
    if not source.is_file() or source.stat().st_size > MAX_BUNDLE_BYTES:
        raise RuntimeError("release source is missing or too large")
    with tempfile.TemporaryDirectory(prefix="cloudx-release-") as value:
        root = pathlib.Path(value)
        _safe_extract(source.read_bytes(), root)
        yield root


def _release_files(root: pathlib.Path, component: str) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, Dict[str, Any]]:
    manifests = list(root.rglob("manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("release source must contain exactly one manifest")
    manifest_path = manifests[0]
    signature_path = manifest_path.with_suffix(".json.sig")
    if not signature_path.is_file():
        raise RuntimeError("release signature is missing")
    _verify_signature(manifest_path, signature_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("release manifest is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "cloudx.release-manifest.v1":
        raise RuntimeError("release manifest schema is unsupported")
    if manifest.get("product") != "cloudx" or not isinstance(manifest.get("version"), str):
        raise RuntimeError("release product or version is invalid")
    activation = manifest.get("activation")
    if not isinstance(activation, dict) or activation.get("automatic") is not False:
        raise RuntimeError("release manifest permits automatic activation")
    records = [item for item in manifest.get("artifacts", []) if isinstance(item, dict) and item.get("component") == component]
    if len(records) != 1:
        raise RuntimeError("release manifest must contain one %s artifact" % component)
    artifact = manifest_path.parent / str(records[0].get("name") or "")
    if not artifact.is_file():
        raise RuntimeError("%s release artifact is missing" % component)
    if artifact.stat().st_size != records[0].get("size") or _digest(artifact) != records[0].get("sha256"):
        raise RuntimeError("%s release artifact hash does not match the manifest" % component)
    return manifest_path, signature_path, artifact, manifest


def _local_root(config: LocalConfig) -> pathlib.Path:
    return config.home / ".local/lib/cloudx"


def _verify_artifact_self_check(artifact: pathlib.Path, version: str, protocol: Any) -> None:
    completed = subprocess.run(
        [sys.executable, str(artifact), "self-check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20.0,
        check=False,
    )
    try:
        document = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("staged local artifact returned an invalid self-check") from exc
    if completed.returncode != 0 or not isinstance(document, dict):
        raise RuntimeError("staged local artifact failed its self-check")
    if document.get("schema") != "cloudx.self-check.v1" or document.get("component") != "local":
        raise RuntimeError("staged local artifact returned the wrong self-check contract")
    if document.get("version") != version:
        raise RuntimeError("staged local artifact failed version self-check")
    if document.get("protocol") != protocol:
        raise RuntimeError("staged local artifact failed protocol self-check")
    if document.get("status") != "ok":
        raise RuntimeError("staged local artifact self-check is not healthy")


def _bundle_bytes(release_directory: pathlib.Path, version: str) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        archive.add(release_directory, arcname="cloudx-%s" % version)
    raw = output.getvalue()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise RuntimeError("release bundle exceeds 64 MiB")
    return raw


def stage(config: LocalConfig, source: pathlib.Path, local_only: bool) -> Dict[str, Any]:
    with release_source(source) as root:
        manifest_path, signature_path, artifact, manifest = _release_files(root, "local")
        version = manifest["version"]
        local_root = _local_root(config)
        current = local_root / "current"
        if current.is_symlink() and _version_tuple(version) < _version_tuple(current.resolve().name):
            raise RuntimeError("staging a downgrade is not allowed; use rollback for the previous release")
        releases = local_root / "releases"
        ensure_private_directory(releases)
        destination = releases / version
        target = destination / "cloudx-local.pyz"
        if destination.exists():
            if not target.is_file() or _digest(target) != _digest(artifact):
                raise RuntimeError("a different local release is already staged at this version")
            local_status = "already-staged"
        else:
            temporary = releases / (".stage-%s-%d" % (version, os.getpid()))
            shutil.rmtree(temporary, ignore_errors=True)
            temporary.mkdir(mode=0o700)
            try:
                shutil.copy2(artifact, temporary / "cloudx-local.pyz")
                (temporary / "cloudx-local.pyz").chmod(0o755)
                shutil.copy2(manifest_path, temporary / "manifest.json")
                shutil.copy2(signature_path, temporary / "manifest.json.sig")
                (temporary / "allowed_signers").write_bytes(_trusted_signers())
                _verify_artifact_self_check(temporary / "cloudx-local.pyz", version, manifest.get("protocol"))
                os.replace(str(temporary), str(destination))
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
            local_status = "staged"
        remote_status = "not-requested"
        if not local_only:
            release_directory = manifest_path.parent
            remote = RemoteClient(config).stage_release(_bundle_bytes(release_directory, version))
            remote_status = str(remote.get("status") or "staged")
        return {
            "schema": "cloudx.release-stage.v1",
            "version": version,
            "local": local_status,
            "cloud": remote_status,
            "activated": False,
        }


@contextlib.contextmanager
def resolved_stage_source(config: LocalConfig, source: pathlib.Path) -> Iterator[pathlib.Path]:
    if source.exists():
        yield source
        return
    match = VERSION_RE.match(str(source))
    if not match:
        raise RuntimeError("release source does not exist")
    version = match.group(1)
    branch = "release-artifacts/v%s" % version
    with tempfile.TemporaryDirectory(prefix="cloudx-release-fetch-") as value:
        destination = pathlib.Path(value) / "release"
        completed = subprocess.run(
            ["git", "clone", "--quiet", "--depth=1", "--branch", branch, config.release_repository, str(destination)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120.0,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("could not fetch the requested signed release")
        yield destination


def _atomic_link(link: pathlib.Path, target: pathlib.Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.parent / (".%s.%d" % (link.name, os.getpid()))
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(str(temporary), str(link))


def _latest_staged_before(root: pathlib.Path, version: str, artifact_name: str) -> Optional[pathlib.Path]:
    releases = root / "releases"
    candidates = []
    if releases.is_dir():
        for path in releases.iterdir():
            if not path.is_dir() or not (path / artifact_name).is_file():
                continue
            try:
                parsed = _version_tuple(path.name)
            except RuntimeError:
                continue
            if parsed < _version_tuple(version):
                candidates.append((parsed, path))
    return max(candidates, default=(None, None), key=lambda item: item[0])[1]


def _activate_local(config: LocalConfig, version: str) -> Optional[str]:
    root = _local_root(config)
    destination = root / "releases" / version
    artifact = destination / "cloudx-local.pyz"
    if not artifact.is_file():
        raise RuntimeError("local release is not staged")
    current = root / "current"
    previous = root / "previous"
    old_target = current.resolve() if current.is_symlink() else None
    _atomic_link(current, destination)
    if old_target and old_target != destination:
        _atomic_link(previous, old_target)
    elif not previous.is_symlink():
        fallback = _latest_staged_before(root, version, "cloudx-local.pyz")
        if fallback:
            _atomic_link(previous, fallback)
    bin_dir = config.home / ".local/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    stable_artifact = current / "cloudx-local.pyz"
    for name in ("codexx", "cloud", "cloudx-update"):
        _atomic_link(bin_dir / name, stable_artifact)
    return old_target.name if old_target else None


def _rollback_local(config: LocalConfig, version: str) -> None:
    root = _local_root(config)
    current = root / "current"
    previous = root / "previous"
    if not previous.is_symlink() or previous.resolve().name != version:
        raise RuntimeError("requested local rollback version is not the previous release")
    old_current = current.resolve() if current.is_symlink() else None
    target = previous.resolve()
    _atomic_link(current, target)
    if old_current and old_current != target:
        _atomic_link(previous, old_current)


def install_shell_hook(config: LocalConfig) -> pathlib.Path:
    hook = config.home / ".config/cloudx/shell.zsh"
    atomic_write(hook, _shell_hook(), mode=0o644)
    zshrc = config.home / ".zshrc"
    original = zshrc.read_text(encoding="utf-8") if zshrc.is_file() else ""
    lines = original.splitlines()
    filtered = []
    skipping = False
    for line in lines:
        if line.strip() in ("# codexx shell hook start", "# cloudx shell hook start", "# >>> codexx >>>"):
            skipping = True
            continue
        if skipping and line.strip() in ("# codexx shell hook end", "# cloudx shell hook end", "# <<< codexx <<<"):
            skipping = False
            continue
        if not skipping:
            filtered.append(line)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if zshrc.is_file():
        backup = config.state_dir / "shell-backups" / ("zshrc-%s" % timestamp)
        atomic_write(backup, original.encode("utf-8"), mode=0o600)
    filtered.extend(["", "# cloudx shell hook start", "source %s" % hook, "# cloudx shell hook end"])
    atomic_write(zshrc, ("\n".join(filtered).rstrip() + "\n").encode("utf-8"), mode=0o644)
    return hook


def seed_native_profile(config: LocalConfig, account: str) -> pathlib.Path:
    source = config.accounts_dir / account / ".codex"
    required = [source / "auth.json", source / "config.toml"]
    if not all(path.is_file() for path in required):
        raise RuntimeError("source account lacks auth.json or config.toml: %s" % account)
    destination = config.home / ".codex"
    ensure_private_directory(destination)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config.state_dir / "native-profile-backups" / timestamp
    ensure_private_directory(backup)
    for name in ("auth.json", "config.toml"):
        target = destination / name
        if target.exists():
            shutil.copy2(target, backup / name)
        atomic_write(target, (source / name).read_bytes(), mode=0o600)
    marker = config.state_dir / "native-profile-seed.json"
    atomic_json(marker, {"account": account, "at": timestamp, "backup": str(backup)})
    return backup


def apply(
    config: LocalConfig,
    version: str,
    confirmation: str,
    local_only: bool,
    shell_hook: bool,
    seed_account: Optional[str],
    cloud_only: bool = False,
) -> Dict[str, Any]:
    if confirmation != version:
        raise RuntimeError("release activation confirmation does not match the version")
    if local_only == cloud_only:
        raise RuntimeError("select exactly one activation endpoint")
    if cloud_only:
        if shell_hook or seed_account:
            raise RuntimeError("shell hook and profile seeding are local-only activation options")
        remote = RemoteClient(config)
        activated = remote.activate_release(version)
        observed = remote.release_status()
        if observed.get("currentVersion") != version:
            previous = activated.get("previousVersion")
            if isinstance(previous, str) and previous:
                try:
                    remote.rollback_release(previous)
                except RuntimeError:
                    pass
            raise RuntimeError("cloud release status did not report the activated version")
        return {
            "schema": "cloudx.release-activate.v1",
            "endpoint": "cloud",
            "version": version,
            "status": "active",
            "previousCloud": activated.get("previousVersion"),
        }
    current = _local_root(config) / "current"
    if current.is_symlink() and _version_tuple(version) < _version_tuple(current.resolve().name):
        raise RuntimeError("release activation would be a downgrade; use rollback")
    destination = _local_root(config) / "releases" / version
    if not (destination / "cloudx-local.pyz").is_file():
        raise RuntimeError("local release is not staged")
    local_previous = _activate_local(config, version)
    hook_path = str(install_shell_hook(config)) if shell_hook else None
    backup_path = str(seed_native_profile(config, seed_account)) if seed_account else None
    return {
        "schema": "cloudx.release-activate.v1",
        "endpoint": "local",
        "version": version,
        "status": "active",
        "previousLocal": local_previous,
        "shellHook": hook_path,
        "nativeProfileBackup": backup_path,
    }


def rollback(config: LocalConfig, version: str, local_only: bool, cloud_only: bool = False) -> Dict[str, Any]:
    if local_only == cloud_only:
        raise RuntimeError("select exactly one rollback endpoint")
    if cloud_only:
        remote = RemoteClient(config)
        remote.rollback_release(version)
        observed = remote.release_status()
        if observed.get("currentVersion") != version:
            raise RuntimeError("cloud release status did not report the rollback version")
        endpoint = "cloud"
    else:
        _rollback_local(config, version)
        endpoint = "local"
    return {
        "schema": "cloudx.release-rollback.v1",
        "endpoint": endpoint,
        "version": version,
        "status": "active",
    }


def _fetch_stable(repository: str, cache: pathlib.Path) -> None:
    ensure_private_directory(cache)
    if not (cache / "HEAD").exists():
        completed = subprocess.run(["git", "init", "--bare", str(cache)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0:
            raise RuntimeError("could not initialize the update cache")
    fetched = subprocess.run(
        ["git", "--git-dir", str(cache), "fetch", "--force", "--depth=1", repository, "refs/heads/release/stable"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30.0,
        check=False,
    )
    if fetched.returncode != 0:
        raise RuntimeError("could not fetch the signed stable release index")


def _git_show(cache: pathlib.Path, name: str) -> bytes:
    shown = subprocess.run(
        ["git", "--git-dir", str(cache), "show", "FETCH_HEAD:%s" % name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if shown.returncode != 0:
        raise RuntimeError("stable release index is incomplete")
    return shown.stdout


def check(config: LocalConfig, index_dir: Optional[pathlib.Path], quiet: bool) -> Dict[str, Any]:
    if index_dir:
        index_bytes = (index_dir / "index.json").read_bytes()
        signature_bytes = (index_dir / "index.json.sig").read_bytes()
    else:
        cache = config.cache_dir / "update.git"
        _fetch_stable(config.release_repository, cache)
        index_bytes = _git_show(cache, "index.json")
        signature_bytes = _git_show(cache, "index.json.sig")
    with tempfile.TemporaryDirectory(prefix="cloudx-index-") as value:
        root = pathlib.Path(value)
        index_path = root / "index.json"
        signature_path = root / "index.json.sig"
        index_path.write_bytes(index_bytes)
        signature_path.write_bytes(signature_bytes)
        _verify_signature(index_path, signature_path)
        document = json.loads(index_bytes.decode("utf-8"))
    if not isinstance(document, dict) or document.get("schema") != "cloudx.release-index.v1":
        raise RuntimeError("stable release index schema is unsupported")
    available = str(document.get("version") or "")
    if _version_tuple(available) < _version_tuple(VERSION):
        raise RuntimeError("stable release index attempts a downgrade")
    if document.get("artifactRef") != "refs/heads/release-artifacts/v%s" % available:
        raise RuntimeError("stable release index artifact reference is invalid")
    if not re.match(r"^[a-f0-9]{64}$", str(document.get("manifestSha256") or "")):
        raise RuntimeError("stable release index manifest hash is invalid")
    result = {
        "schema": "cloudx.update-check.v1",
        "current": VERSION,
        "available": available,
        "updateAvailable": available != VERSION,
        "checkedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "activated": False,
    }
    atomic_json(config.state_dir / "update-check.json", result)
    if not quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return result


def maybe_schedule_check(config: LocalConfig) -> None:
    if os.environ.get("CLOUDX_DISABLE_UPDATE_CHECK") == "1":
        return
    state = config.state_dir / "update-check.json"
    try:
        if time.time() - state.stat().st_mtime < 24 * 60 * 60:
            return
    except OSError:
        pass
    target = pathlib.Path(os.environ.get("CLOUDX_LOCAL_ARTIFACT") or os.path.realpath(sys.argv[0]))
    log = config.state_dir / "update-check.log"
    ensure_private_directory(log.parent)
    with log.open("ab", buffering=0) as output:
        environment = dict(os.environ)
        for name in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "CODEX_HOME",
            "CODEXX_ACTIVE_ACCOUNT",
            "CODEXX_ACTIVE_HOME",
            "CODEXX_ACTIVE_PINNED",
        ):
            environment.pop(name, None)
        environment["CLOUDX_USER_HOME"] = str(config.home)
        subprocess.Popen(
            [sys.executable, str(target), "update", "check", "--quiet"],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
            env=environment,
        )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cloudx-update")
    sub = root.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--index-dir", type=pathlib.Path)
    check_parser.add_argument("--quiet", action="store_true")
    stage_parser = sub.add_parser("stage")
    stage_parser.add_argument("source", type=pathlib.Path)
    stage_parser.add_argument("--local-only", action="store_true")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("version")
    apply_parser.add_argument("--confirm", required=True)
    apply_endpoint = apply_parser.add_mutually_exclusive_group(required=True)
    apply_endpoint.add_argument("--local-only", action="store_true")
    apply_endpoint.add_argument("--cloud-only", action="store_true")
    apply_parser.add_argument("--install-shell-hook", action="store_true")
    apply_parser.add_argument("--seed-native-from")
    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--confirm", required=True)
    rollback_endpoint = rollback_parser.add_mutually_exclusive_group(required=True)
    rollback_endpoint.add_argument("--local-only", action="store_true")
    rollback_endpoint.add_argument("--cloud-only", action="store_true")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    config = LocalConfig.load()
    if args.command == "check":
        check(config, args.index_dir, args.quiet)
        return 0
    if args.command == "stage":
        with resolved_stage_source(config, args.source) as source:
            result = stage(config, source, args.local_only)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "apply":
        result = apply(
            config,
            args.version,
            args.confirm,
            args.local_only,
            args.install_shell_hook,
            args.seed_native_from,
            args.cloud_only,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "rollback":
        print(json.dumps(rollback(config, args.confirm, args.local_only, args.cloud_only), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("cloudx-update: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
