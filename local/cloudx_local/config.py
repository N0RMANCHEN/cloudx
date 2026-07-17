from __future__ import annotations

import json
import os
import pathlib
import pwd
import shutil
from dataclasses import dataclass
from typing import Any, Dict, Optional


LEGACY_API_KEY_COMMAND = (
    "sudo -n awk '/^api-keys:/{getline; "
    "gsub(/^[[:space:]]*-[[:space:]]*/, \"\"); "
    "gsub(/^\"|\"$/, \"\"); print; exit}' /etc/cliproxy/config.yaml"
)


def user_home() -> pathlib.Path:
    value = os.environ.get("CLOUDX_USER_HOME") or os.environ.get("CODEXX_USER_HOME")
    if not value:
        try:
            value = pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            value = os.environ.get("HOME")
    if not value:
        raise RuntimeError("HOME is not set")
    return pathlib.Path(value).expanduser()


def _load_json(path: pathlib.Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid Cloudx config: %s" % path) from exc
    if not isinstance(value, dict):
        raise RuntimeError("Cloudx config root must be an object")
    return value


@dataclass(frozen=True)
class LocalConfig:
    home: pathlib.Path
    config_path: pathlib.Path
    state_dir: pathlib.Path
    data_dir: pathlib.Path
    cache_dir: pathlib.Path
    accounts_dir: pathlib.Path
    codex_binary: str
    ssh_binary: str
    ssh_host: str
    remote_helper: str
    legacy_forward_host: str
    legacy_forward_port: int
    legacy_api_key_command: str
    broker_idle_seconds: int
    endpoint_timeout_seconds: float
    endpoint_attempts: int
    release_repository: str
    local_cpa_auth_dir: Optional[pathlib.Path] = None

    @classmethod
    def load(cls) -> "LocalConfig":
        home = user_home()
        config_path = pathlib.Path(
            os.environ.get("CLOUDX_CONFIG", str(home / ".config/cloudx/config.json"))
        ).expanduser()
        data = _load_json(config_path)
        broker = data.get("broker") if isinstance(data.get("broker"), dict) else {}
        legacy = data.get("legacy") if isinstance(data.get("legacy"), dict) else {}
        local_cpa = data.get("localCpa") if isinstance(data.get("localCpa"), dict) else {}
        codex_binary = str(
            os.environ.get("CLOUDX_CODEX_BINARY")
            or data.get("codexBinary")
            or ("/opt/homebrew/bin/codex" if pathlib.Path("/opt/homebrew/bin/codex").is_file() else shutil.which("codex") or "codex")
        )
        return cls(
            home=home,
            config_path=config_path,
            state_dir=pathlib.Path(os.environ.get("CLOUDX_STATE_DIR", str(home / ".local/state/cloudx"))).expanduser(),
            data_dir=pathlib.Path(os.environ.get("CLOUDX_DATA_DIR", str(home / ".local/share/cloudx"))).expanduser(),
            cache_dir=pathlib.Path(os.environ.get("CLOUDX_CACHE_DIR", str(home / ".cache/cloudx"))).expanduser(),
            accounts_dir=pathlib.Path(data.get("accountsDir", home / ".codex-accounts")).expanduser(),
            codex_binary=codex_binary,
            ssh_binary=str(os.environ.get("CLOUDX_SSH_BINARY") or data.get("sshBinary") or shutil.which("ssh") or "ssh"),
            ssh_host=str(os.environ.get("CLOUDX_SSH_HOST") or data.get("sshHost") or "cloud"),
            remote_helper=str(os.environ.get("CLOUDX_REMOTE_HELPER") or data.get("remoteHelper") or "cloudx-remote"),
            legacy_forward_host=str(legacy.get("forwardHost") or "100.90.97.113"),
            legacy_forward_port=int(legacy.get("forwardPort") or 8317),
            legacy_api_key_command=str(legacy.get("apiKeyCommand") or LEGACY_API_KEY_COMMAND),
            broker_idle_seconds=max(60, int(broker.get("idleSeconds") or 900)),
            endpoint_timeout_seconds=max(2.0, float(broker.get("healthTimeoutSeconds") or 5.0)),
            endpoint_attempts=max(1, int(broker.get("healthAttempts") or 3)),
            release_repository=str(data.get("releaseRepository") or "git@github.com:N0RMANCHEN/cloudx.git"),
            local_cpa_auth_dir=pathlib.Path(str(
                os.environ.get("CLOUDX_LOCAL_CPA_AUTH_DIR")
                or local_cpa.get("authDir")
                or home / ".cli-proxy-api"
            )).expanduser(),
        )

    @property
    def broker_dir(self) -> pathlib.Path:
        return self.state_dir / "tunnel"

    @property
    def cloud_codex_home(self) -> pathlib.Path:
        return self.data_dir / "codex-home"
