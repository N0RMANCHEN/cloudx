from __future__ import annotations

import os
import pathlib
from typing import Dict

from .config import LocalConfig
from .files import atomic_json, ensure_private_directory


SHARED_ENTRIES = ("sessions", "session_index.jsonl", "skills")


def prepare_cloud_codex_home(config: LocalConfig) -> pathlib.Path:
    target_root = config.cloud_codex_home
    shared_root = config.home / ".codex"
    ensure_private_directory(target_root)
    for name in SHARED_ENTRIES:
        target = target_root / name
        source = shared_root / name
        if target.is_symlink():
            if pathlib.Path(os.readlink(target)) == source:
                continue
            raise RuntimeError("Cloudx Codex home has an unexpected symlink: %s" % target)
        if target.exists():
            continue
        target.symlink_to(source, target_is_directory=name in ("sessions", "skills"))
    return target_root


def cloud_codex_environment(config: LocalConfig, api_key: str, port: int) -> Dict[str, str]:
    home = prepare_cloud_codex_home(config)
    atomic_json(
        home / "auth.json",
        {
            "auth_mode": "apikey",
            "OPENAI_API_KEY": api_key,
            "api_key": api_key,
            "cloudx_auth_source": "scoped-gateway",
        },
        mode=0o600,
    )
    base_url = "http://127.0.0.1:%d/v1" % port
    environment = dict(os.environ)
    environment.update(
        {
            "CODEX_HOME": str(home),
            "OPENAI_API_KEY": api_key,
            "OPENAI_BASE_URL": base_url,
            "OPENAI_API_BASE": base_url,
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        environment.pop(name, None)
    for name in ("CODEXX_ACTIVE_ACCOUNT", "CODEXX_ACTIVE_HOME", "CODEXX_ACTIVE_PINNED", "CODEXX_SHARED_CODEX_ROOT"):
        environment.pop(name, None)
    return environment
