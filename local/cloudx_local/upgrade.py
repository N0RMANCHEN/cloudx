from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Dict, Optional, Sequence

from . import updater
from .config import LocalConfig
from .remote import RemoteClient
from .version import VERSION


SCHEMA = "cloudx.upgrade.v1"


def _local_current(config: LocalConfig) -> str:
    current = config.home / ".local/lib/cloudx/current"
    if not current.is_symlink():
        raise RuntimeError("active local Cloudx release selector is unavailable")
    try:
        version = current.resolve(strict=True).name
    except OSError as exc:
        raise RuntimeError("active local Cloudx release is unavailable") from exc
    if version != VERSION:
        raise RuntimeError("running Cloudx version does not match the active local selector")
    return version


def _cloud_current(config: LocalConfig) -> str:
    document = RemoteClient(config).release_status()
    version = str(document.get("currentVersion") or "")
    updater._version_tuple(version)
    return version


def _result(
    endpoint: str,
    status: str,
    current_before: str,
    available: str,
    current_after: str,
    artifact_ref: str,
    manifest_sha256: str,
    *,
    staged: Optional[Dict[str, Any]] = None,
    activated: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "endpoint": endpoint,
        "currentBefore": current_before,
        "available": available,
        "currentAfter": current_after,
        "artifactRef": artifact_ref,
        "manifestSha256": manifest_sha256,
        "stageStatus": (
            str(staged.get("local") or "")
            if staged is not None and endpoint == "local"
            else str(staged.get("cloud") or "") if staged is not None else None
        ),
        "activationStatus": str(activated.get("status") or "") if activated is not None else None,
        "signedIndexVerified": True,
        "verificationScope": (
            "complete-release-chain" if status == "upgraded" else "signed-index-only"
        ),
        "explicitInvocation": True,
        "backgroundActivation": False,
        "serviceRestarted": False,
        "externalCpaManaged": False,
        "officialCodexReplaced": False,
        "shellReloadRecommended": endpoint == "local" and status == "upgraded",
    }


def upgrade_endpoint(
    config: LocalConfig,
    endpoint: str,
    *,
    check_only: bool = False,
    index_dir: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    if endpoint not in {"local", "cloud"}:
        raise RuntimeError("upgrade endpoint is invalid")
    index = updater.stable_index(config, index_dir)
    available = str(index["version"])
    artifact_ref = str(index["artifactRef"])
    manifest_sha256 = str(index["manifestSha256"])
    current = _local_current(config) if endpoint == "local" else _cloud_current(config)
    available_tuple = updater._version_tuple(available)
    current_tuple = updater._version_tuple(current)
    if available_tuple < current_tuple:
        raise RuntimeError("signed stable release would downgrade the selected endpoint")
    if available_tuple == current_tuple:
        return _result(
            endpoint,
            "up-to-date",
            current,
            available,
            current,
            artifact_ref,
            manifest_sha256,
        )
    if check_only:
        return _result(
            endpoint,
            "update-available",
            current,
            available,
            current,
            artifact_ref,
            manifest_sha256,
        )

    with updater.resolved_stage_source(config, pathlib.Path(available)) as source:
        if endpoint == "local":
            staged = updater.stage(
                config,
                source,
                local_only=True,
                expected_manifest_sha256=manifest_sha256,
                expected_version=available,
            )
        else:
            staged = updater.stage_cloud(
                config,
                source,
                expected_manifest_sha256=manifest_sha256,
                expected_version=available,
            )

    if endpoint == "cloud":
        activated = updater.apply(
            config,
            available,
            available,
            False,
            False,
            None,
            cloud_only=True,
        )
        current_after = _cloud_current(config)
    else:
        activated = None
        try:
            activated = updater.apply(
                config,
                available,
                available,
                True,
                True,
                None,
            )
            current_after = (config.home / ".local/lib/cloudx/current").resolve(strict=True).name
            if current_after != available:
                raise RuntimeError("local release selector did not activate the signed release")
        except Exception as exc:
            try:
                selected = (config.home / ".local/lib/cloudx/current").resolve(strict=True).name
                if selected == available:
                    updater.rollback(config, current, local_only=True)
                elif selected != current:
                    raise RuntimeError("local selector changed to an unexpected release")
                restored = (config.home / ".local/lib/cloudx/current").resolve(strict=True).name
            except Exception as recovery_exc:
                raise RuntimeError("local upgrade failed; rollback verification also failed") from recovery_exc
            if restored != current:
                raise RuntimeError("local upgrade failed; rollback did not restore the prior release") from exc
            raise RuntimeError("local upgrade failed and restored the prior release") from exc

    if current_after != available:
        raise RuntimeError("upgrade acceptance did not observe the signed target version")
    return _result(
        endpoint,
        "upgraded",
        current,
        available,
        current_after,
        artifact_ref,
        manifest_sha256,
        staged=staged,
        activated=activated,
    )


def _render(document: Dict[str, Any]) -> None:
    labels = {
        "up-to-date": "already up to date",
        "update-available": "update available (no changes made)",
        "upgraded": "upgraded",
    }
    print("Cloudx upgrade")
    print("  Status: %s" % labels.get(str(document.get("status")), "failed"))
    print("  Destination: %s" % ("this computer" if document.get("endpoint") == "local" else "cloud helper"))
    print("  Before: %s" % document.get("currentBefore"))
    print("  Available: %s" % document.get("available"))
    print("  Current: %s" % document.get("currentAfter"))
    if document.get("verificationScope") == "complete-release-chain":
        print("  Verification: signed index, exact manifest, artifact digest, and self-check")
    else:
        print("  Verification: signed stable index only; no release artifact fetched")
    print("  Service restarted: no")
    if document.get("shellReloadRecommended"):
        print("  Next: open a new shell to load the upgraded command surface")


def run(config: LocalConfig, endpoint: str, arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="codexx upgrade" if endpoint == "local" else "codexx cloud upgrade")
    parser.add_argument("--check", action="store_true", help="check the signed stable release without changing either endpoint")
    parser.add_argument("--json", action="store_true", help="emit cloudx.upgrade.v1 JSON")
    parser.add_argument("--index-dir", type=pathlib.Path, help=argparse.SUPPRESS)
    args = parser.parse_args(list(arguments))
    document = upgrade_endpoint(
        config,
        endpoint,
        check_only=args.check,
        index_dir=args.index_dir,
    )
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        _render(document)
    return 0
