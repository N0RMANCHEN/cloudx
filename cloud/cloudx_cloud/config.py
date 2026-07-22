from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Optional


def _path(name: str, default: str) -> pathlib.Path:
    return pathlib.Path(os.environ.get(name, default)).expanduser()


@dataclass(frozen=True)
class Config:
    auth_dir: pathlib.Path
    import_lock_path: pathlib.Path
    health_path: pathlib.Path
    account_state_path: pathlib.Path
    account_state_source_path: pathlib.Path
    gateway_url: str
    gateway_version: str
    gateway_forward_host: str
    gateway_forward_port: int
    client_credential_file: pathlib.Path
    deployment_id: str
    build_commit: str
    cpa_binary: Optional[pathlib.Path] = None
    cpa_capability_manifest: Optional[pathlib.Path] = None

    @classmethod
    def from_environment(cls) -> "Config":
        auth_dir = _path("CLOUDX_AUTH_DIR", "/var/lib/cloudx/shadow-auth")
        configured_binary = os.environ.get("CLOUDX_CPA_BINARY")
        return cls(
            auth_dir=auth_dir,
            import_lock_path=_path("CLOUDX_IMPORT_LOCK", "/run/cloudx-shadow/import.lock"),
            health_path=_path("CLOUDX_HEALTH_PATH", "/run/cloudx-shadow/health.json"),
            account_state_path=_path("CLOUDX_ACCOUNT_STATE_PATH", "/run/cloudx-shadow/accounts.json"),
            account_state_source_path=_path(
                "CLOUDX_ACCOUNT_STATE_SOURCE", "/var/lib/codex-quota-monitor/state.json"
            ),
            gateway_url=os.environ.get("CLOUDX_GATEWAY_URL", "http://127.0.0.1:8317").rstrip("/"),
            gateway_version=os.environ.get("CLOUDX_GATEWAY_VERSION", "external"),
            gateway_forward_host=os.environ.get("CLOUDX_GATEWAY_FORWARD_HOST", "127.0.0.1"),
            gateway_forward_port=int(os.environ.get("CLOUDX_GATEWAY_FORWARD_PORT", "8317")),
            client_credential_file=_path("CLOUDX_CLIENT_CREDENTIAL_FILE", "/etc/cloudx/client-credential"),
            deployment_id=os.environ.get("CLOUDX_DEPLOYMENT_ID", "shadow"),
            build_commit=os.environ.get("CLOUDX_BUILD_COMMIT", "development"),
            cpa_binary=pathlib.Path(configured_binary).expanduser() if configured_binary else None,
            cpa_capability_manifest=_path(
                "CLOUDX_CPA_CAPABILITY_MANIFEST",
                "/etc/cloudx/cloud-cpa-capabilities.json",
            ),
        )
