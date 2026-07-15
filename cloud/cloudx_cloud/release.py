from __future__ import annotations

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
from typing import Any, Dict, Optional, Tuple


MAX_BUNDLE_BYTES = 64 * 1024 * 1024
SIGNING_IDENTITY = "cloudx-release"
SIGNING_NAMESPACE = "cloudx-release"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _version_tuple(value: str) -> Tuple[int, int, int]:
    if not VERSION_RE.match(value):
        raise RuntimeError("invalid release version")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def release_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLOUDX_RELEASE_ROOT", "/opt/cloudx")).expanduser()


def read_bundle(stream: Any) -> bytes:
    raw = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise RuntimeError("release bundle exceeds 64 MiB")
    if not raw:
        raise RuntimeError("release bundle is empty")
    return raw


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _extract(raw: bytes, destination: pathlib.Path) -> None:
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


def _allowed_signers() -> bytes:
    data = pkgutil.get_data("cloudx_cloud", "data/allowed_signers")
    if not data:
        raise RuntimeError("release signer trust root is missing")
    return data


def _verify_signature(manifest: pathlib.Path, signature: pathlib.Path) -> None:
    with tempfile.NamedTemporaryFile(prefix="cloudx-signers-", delete=False) as handle:
        handle.write(_allowed_signers())
        signer_path = pathlib.Path(handle.name)
    try:
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(signer_path),
                "-I",
                SIGNING_IDENTITY,
                "-n",
                SIGNING_NAMESPACE,
                "-s",
                str(signature),
            ],
            input=manifest.read_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        signer_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise RuntimeError("release signature verification failed")


def _release_files(extracted: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, Dict[str, Any]]:
    manifests = list(extracted.rglob("manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("release bundle must contain exactly one manifest")
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
        raise RuntimeError("release manifest product or version is invalid")
    activation = manifest.get("activation")
    if not isinstance(activation, dict) or activation.get("automatic") is not False:
        raise RuntimeError("release manifest permits automatic activation")
    records = [item for item in manifest.get("artifacts", []) if isinstance(item, dict) and item.get("component") == "cloud"]
    if len(records) != 1:
        raise RuntimeError("release manifest must contain one cloud artifact")
    artifact = manifest_path.parent / str(records[0].get("name") or "")
    if not artifact.is_file():
        raise RuntimeError("cloud release artifact is missing")
    if artifact.stat().st_size != records[0].get("size") or digest(artifact) != records[0].get("sha256"):
        raise RuntimeError("cloud release artifact hash does not match the manifest")
    return manifest_path, signature_path, artifact, manifest


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
        raise RuntimeError("staged cloud artifact returned an invalid self-check") from exc
    if completed.returncode != 0 or not isinstance(document, dict):
        raise RuntimeError("staged cloud artifact failed its self-check")
    if document.get("schema") != "cloudx.self-check.v1" or document.get("component") != "cloud":
        raise RuntimeError("staged cloud artifact returned the wrong self-check contract")
    if document.get("version") != version:
        raise RuntimeError("staged cloud artifact failed version self-check")
    if document.get("protocol") != protocol:
        raise RuntimeError("staged cloud artifact failed protocol self-check")
    if document.get("status") != "ok":
        raise RuntimeError("staged cloud artifact self-check is not healthy")


def stage(raw: bytes) -> Dict[str, Any]:
    root = release_root()
    with tempfile.TemporaryDirectory(prefix="cloudx-release-stage-") as value:
        extracted = pathlib.Path(value)
        _extract(raw, extracted)
        manifest_path, signature_path, artifact, manifest = _release_files(extracted)
        version = manifest["version"]
        current = root / "current"
        if current.is_symlink() and _version_tuple(version) < _version_tuple(current.resolve().name):
            raise RuntimeError("staging a downgrade is not allowed; use rollback")
        destination = root / "releases" / version
        target = destination / "cloudx-cloud.pyz"
        if destination.exists():
            if target.is_file() and digest(target) == digest(artifact):
                return {"schema": "cloudx.release-stage.v1", "version": version, "status": "already-staged"}
            raise RuntimeError("a different release is already staged at this version")
        releases = root / "releases"
        releases.mkdir(parents=True, exist_ok=True, mode=0o755)
        temporary = releases / (".stage-%s-%d" % (version, os.getpid()))
        shutil.rmtree(temporary, ignore_errors=True)
        temporary.mkdir(mode=0o755)
        try:
            target = temporary / "cloudx-cloud.pyz"
            shutil.copy2(artifact, target)
            target.chmod(0o755)
            shutil.copy2(manifest_path, temporary / "manifest.json")
            shutil.copy2(signature_path, temporary / "manifest.json.sig")
            (temporary / "allowed_signers").write_bytes(_allowed_signers())
            _verify_artifact_self_check(target, version, manifest.get("protocol"))
            os.replace(str(temporary), str(destination))
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return {"schema": "cloudx.release-stage.v1", "version": version, "status": "staged"}


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


def _release_link_version(root: pathlib.Path, name: str) -> Optional[str]:
    link = root / name
    if not link.is_symlink():
        if link.exists():
            raise RuntimeError("cloud release %s is not a symlink" % name)
        return None
    target = link.resolve()
    releases = (root / "releases").resolve()
    if target.parent != releases:
        raise RuntimeError("cloud release %s points outside the release root" % name)
    version = target.name
    _version_tuple(version)
    if not (target / "cloudx-cloud.pyz").is_file():
        raise RuntimeError("cloud release %s target is incomplete" % name)
    return version


def status() -> Dict[str, Any]:
    root = release_root()
    current = _release_link_version(root, "current")
    previous = _release_link_version(root, "previous")
    artifact = root / "releases" / current / "cloudx-cloud.pyz" if current else None
    return {
        "schema": "cloudx.release-status.v1",
        "status": "active" if current else "inactive",
        "currentVersion": current,
        "previousVersion": previous,
        "currentArtifactSha256": digest(artifact) if artifact else None,
    }


def activate(version: str, confirmation: str) -> Dict[str, Any]:
    if confirmation != version:
        raise RuntimeError("release activation confirmation does not match the version")
    root = release_root()
    current = root / "current"
    current_version = _release_link_version(root, "current")
    if current_version and _version_tuple(version) < _version_tuple(current_version):
        raise RuntimeError("release activation would be a downgrade; use rollback")
    destination = root / "releases" / version
    if not (destination / "cloudx-cloud.pyz").is_file():
        raise RuntimeError("cloud release is not staged")
    previous = root / "previous"
    old_target = root / "releases" / current_version if current_version else None
    _atomic_link(current, destination)
    if old_target and old_target != destination:
        _atomic_link(previous, old_target)
    elif not previous.is_symlink():
        fallback = _latest_staged_before(root, version, "cloudx-cloud.pyz")
        if fallback:
            _atomic_link(previous, fallback)
    observed = status()
    return {
        "schema": "cloudx.release-activate.v1",
        "version": version,
        "status": "active",
        "previousVersion": observed["previousVersion"],
    }


def rollback(confirmation: str) -> Dict[str, Any]:
    root = release_root()
    current = root / "current"
    previous = root / "previous"
    version = _release_link_version(root, "previous")
    if not version:
        raise RuntimeError("no previous cloud release is available")
    if confirmation != version:
        raise RuntimeError("rollback confirmation does not match the previous version")
    current_version = _release_link_version(root, "current")
    old_current = root / "releases" / current_version if current_version else None
    target = root / "releases" / version
    _atomic_link(current, target)
    if old_current and old_current != target:
        _atomic_link(previous, old_current)
    observed = status()
    return {
        "schema": "cloudx.release-rollback.v1",
        "version": version,
        "status": "active",
        "previousVersion": observed["previousVersion"],
    }
