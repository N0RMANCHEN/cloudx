from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any, Dict, Optional, Sequence

from . import capacity, compatibility_profile, consumer_credential, consumer_traffic, cpa_auth, cpa_health, http_importer_gate
from . import legacy_health_bridge
from .account_state import AccountStateRejected, adapt_file
from .compatibility_scripts import SCRIPTS as COMPATIBILITY_SCRIPTS
from .compatibility_scripts import read_compatibility_script
from .config import Config
from .gateway import probe_gateway, read_credential
from .health import build_health, publish
from .importer import ImportRejected, ImportResult, import_records, read_limited, request_identity
from .public_metadata import emit_error, emit_json, emit_text
from .release import activate as activate_release
from .release import read_bundle, rollback as rollback_release, stage as stage_release
from .release import status as release_status
from .systemd_templates import TEMPLATES, read_template
from .version import IMPORT_CONTRACT_VERSION, PROTOCOL_MAX, PROTOCOL_MIN, VERSION


def emit(document: Dict[str, Any]) -> None:
    emit_json(document)


def handshake(config: Config) -> Dict[str, Any]:
    gateway = probe_gateway(config.gateway_url, config.client_credential_file)
    return {
        "schema": "cloudx.handshake.v1",
        "productVersion": VERSION,
        "buildCommit": config.build_commit,
        "protocol": {"min": PROTOCOL_MIN, "max": PROTOCOL_MAX},
        "capabilities": [
            "account-state-adapter.v1",
            "capacity.v1",
            "client-config.v1",
            "import-compatibility-script.v1",
            "cpa-health-native.v1",
            "cpa-health-templates.v1",
            "health.v1",
            "health-publisher-templates.v1",
            "http-importer-stop-gate.v1",
            "import.v1",
            "legacy-gateway.v1",
            "legacy-health-bridge.v1",
            "phi-cloud-consumer-credential.v1",
            "phi-cloud-consumer-traffic-policy.v1",
            "phi-mesh-compatibility-profile.v1",
        ],
        "deploymentId": config.deployment_id,
        "gateway": {"version": config.gateway_version, "status": gateway.status},
        "importerContractVersion": IMPORT_CONTRACT_VERSION,
    }


def client_config(config: Config) -> Dict[str, Any]:
    return {
        "schema": "cloudx.client-config.v1",
        "apiKey": read_credential(config.client_credential_file),
        "forwardHost": config.gateway_forward_host,
        "forwardPort": config.gateway_forward_port,
        "basePath": "/v1",
    }


def rejected(raw: bytes, error: ImportRejected, dry_run: bool) -> ImportResult:
    request_id, request_hash = request_identity(raw)
    return ImportResult(
        request_id=request_id,
        request_hash=request_hash,
        status="rejected",
        dry_run=dry_run,
        written=0,
        skipped=0,
        errors=({"code": error.code, "message": error.safe_message},),
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cloudx-remote")
    sub = root.add_subparsers(dest="command", required=True)
    handshake_parser = sub.add_parser("handshake")
    handshake_parser.add_argument("--json", action="store_true")
    health_parser = sub.add_parser("health")
    health_parser.add_argument("--json", action="store_true")
    capacity_parser = sub.add_parser("capacity")
    capacity_parser.add_argument("--json", action="store_true")
    capacity_parser.add_argument("--consumer-protocol-min", type=int, default=PROTOCOL_MIN)
    capacity_parser.add_argument("--consumer-protocol-max", type=int, default=PROTOCOL_MAX)
    publish_parser = sub.add_parser("publish-health")
    publish_parser.add_argument("--json", action="store_true")
    account_state_parser = sub.add_parser("adapt-account-state")
    account_state_parser.add_argument("--json", action="store_true")
    cpa_health_parser = sub.add_parser("cpa-health")
    cpa_health.add_arguments(cpa_health_parser)
    cpa_restore_parser = sub.add_parser("cpa-health-restore")
    cpa_health.add_restore_arguments(cpa_restore_parser)
    config_parser = sub.add_parser("client-config")
    config_parser.add_argument("--json", action="store_true")
    import_parser = sub.add_parser("import")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--force", action="store_true")
    sub.add_parser("release-stage")
    sub.add_parser("release-status")
    activate_parser = sub.add_parser("release-activate")
    activate_parser.add_argument("--version", required=True)
    activate_parser.add_argument("--confirm", required=True)
    rollback_parser = sub.add_parser("release-rollback")
    rollback_parser.add_argument("--confirm", required=True)
    template_parser = sub.add_parser("systemd-template")
    template_parser.add_argument("name", choices=TEMPLATES)
    compatibility_parser = sub.add_parser("compatibility-script")
    compatibility_parser.add_argument("name", choices=COMPATIBILITY_SCRIPTS)
    sub.add_parser("compatibility-profile")
    legacy_health_parser = sub.add_parser("legacy-health-bridge")
    legacy_health_parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=pathlib.Path("/run/cloudx/health.json"),
    )
    legacy_health_parser.add_argument("--publish-to", type=pathlib.Path)
    sub.add_parser("phi-consumer-credential-policy")
    sub.add_parser("phi-consumer-traffic-policy")
    sub.add_parser("http-importer-stop-gate")
    sub.add_parser("self-check")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "systemd-template":
        emit_text(read_template(args.name))
        return 0
    if args.command == "compatibility-script":
        emit_text(read_compatibility_script(args.name))
        return 0
    if args.command == "compatibility-profile":
        try:
            emit(compatibility_profile.read_profile())
        except RuntimeError as exc:
            emit_error("compatibility-profile", exc)
            return 1
        return 0
    if args.command == "legacy-health-bridge":
        try:
            emit(legacy_health_bridge.bridge_file(
                args.source,
                args.publish_to,
                producer_revision=os.environ.get("CLOUDX_BUILD_COMMIT", "unknown"),
            ))
        except (legacy_health_bridge.LegacyHealthRejected, OSError, ValueError) as exc:
            emit_error("legacy-health-bridge", exc)
            return 1
        return 0
    if args.command == "phi-consumer-credential-policy":
        try:
            emit(consumer_credential.read_policy())
        except RuntimeError as exc:
            emit_error("phi-consumer-credential-policy", exc)
            return 1
        return 0
    if args.command == "phi-consumer-traffic-policy":
        try:
            emit(consumer_traffic.read_policy())
        except RuntimeError as exc:
            emit_error("phi-consumer-traffic-policy", exc)
            return 1
        return 0
    if args.command == "http-importer-stop-gate":
        try:
            document = http_importer_gate.evaluate_stream(sys.stdin.buffer)
        except http_importer_gate.EvidenceRejected as exc:
            emit_error("http-importer-stop-gate", exc)
            return 1
        emit(document)
        return 0 if document["preconditionsSatisfied"] else 2
    if args.command == "cpa-health":
        try:
            return cpa_health.run(args)
        except (cpa_auth.CpaAuthRejected, cpa_health.CpaHealthUnavailable, OSError) as exc:
            emit_error("cpa-health", exc)
            return 1
    if args.command == "cpa-health-restore":
        try:
            return cpa_health.restore_run(args)
        except (cpa_auth.CpaAuthRejected, cpa_health.CpaHealthUnavailable, OSError) as exc:
            emit_error("cpa-health-restore", exc)
            return 1
    config = Config.from_environment()
    if args.command == "handshake":
        emit(handshake(config))
        return 0
    if args.command == "client-config":
        try:
            emit(client_config(config))
        except (OSError, ValueError, RuntimeError) as exc:
            emit_error("client-config unavailable", exc)
            return 1
        return 0
    if args.command in ("health", "publish-health"):
        document = build_health(config)
        if args.command == "publish-health":
            publish(config.health_path, document)
        emit(document)
        return 0
    if args.command == "capacity":
        try:
            emit(capacity.build_capacity(config, args.consumer_protocol_min, args.consumer_protocol_max))
        except (OSError, ValueError, RuntimeError) as exc:
            emit_error("capacity", exc)
            return 1
        return 0
    if args.command == "adapt-account-state":
        try:
            emit(adapt_file(config.account_state_source_path, config.account_state_path))
        except (AccountStateRejected, OSError) as exc:
            emit_error("adapt-account-state", exc)
            return 1
        return 0
    if args.command == "import":
        raw = b""
        try:
            raw = read_limited(sys.stdin.buffer)
            result = import_records(raw, config.auth_dir, config.import_lock_path, args.dry_run, args.force)
        except ImportRejected as exc:
            result = rejected(raw, exc, args.dry_run) if raw else ImportResult(
                request_id="unavailable",
                request_hash="0" * 64,
                status="rejected",
                dry_run=args.dry_run,
                written=0,
                skipped=0,
                errors=({"code": exc.code, "message": exc.safe_message},),
            )
            emit(result.as_dict())
            return 2
        emit(result.as_dict())
        return 0
    if args.command == "release-stage":
        try:
            emit(stage_release(read_bundle(sys.stdin.buffer)))
        except (OSError, ValueError, RuntimeError) as exc:
            emit_error("release-stage", exc)
            return 1
        return 0
    if args.command == "release-status":
        try:
            emit(release_status())
        except (OSError, RuntimeError) as exc:
            emit_error("release-status", exc)
            return 1
        return 0
    if args.command == "release-activate":
        try:
            emit(activate_release(args.version, args.confirm))
        except (OSError, RuntimeError) as exc:
            emit_error("release-activate", exc)
            return 1
        return 0
    if args.command == "release-rollback":
        try:
            emit(rollback_release(args.confirm))
        except (OSError, RuntimeError) as exc:
            emit_error("release-rollback", exc)
            return 1
        return 0
    if args.command == "self-check":
        emit({
            "schema": "cloudx.self-check.v1",
            "component": "cloud",
            "version": VERSION,
            "protocol": {"min": PROTOCOL_MIN, "max": PROTOCOL_MAX},
            "status": "ok",
        })
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
