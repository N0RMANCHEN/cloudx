from __future__ import annotations

import os
import shlex
from typing import List

from . import accounts
from .broker import BrokerClient
from .cloud_cli import probe_endpoint
from .config import LocalConfig
from .profile import prepare_cloud_mode
from .remote import RemoteClient


MODE_VARIABLES = (
    "CLOUDX_MODE",
    "CLOUDX_MODE_LEASE_ID",
    "CLOUDX_MODE_BROKER_PORT",
)


def _release_cloud_lease(config: LocalConfig) -> None:
    lease_id = os.environ.get("CLOUDX_MODE_LEASE_ID", "").strip()
    if not lease_id:
        return
    try:
        BrokerClient(config).release(lease_id)
    except (OSError, ValueError, RuntimeError):
        pass


def _clear_mode_lines() -> List[str]:
    return ["unset %s" % name for name in MODE_VARIABLES]


def select_account(config: LocalConfig, name: str) -> str:
    _release_cloud_lease(config)
    lines = accounts.shell_select(config, name).splitlines()
    lines.extend(_clear_mode_lines())
    lines.append("export CLOUDX_MODE=%s" % shlex.quote("api" if name == "api" else "account"))
    return "\n".join(lines)


def select_cloud(config: LocalConfig, shell_pid: int) -> str:
    if shell_pid <= 1:
        raise RuntimeError("cloud mode requires a live shell PID")
    _release_cloud_lease(config)
    endpoint = RemoteClient(config).resolve_endpoint()
    broker = BrokerClient(config)
    response = broker.acquire_for_owner(
        config.ssh_host,
        endpoint.forward_host,
        endpoint.forward_port,
        shell_pid,
    )
    lease_id = str(response.get("leaseId") or "")
    port = int(response.get("publicPort") or 0)
    try:
        status = probe_endpoint(config, port, endpoint.api_key)
        if status is None or not 200 <= status < 300:
            raise RuntimeError("cloud mode gateway check failed")
        home = prepare_cloud_mode(config, endpoint.api_key, port)
    except Exception:
        broker.release(lease_id)
        raise
    values = {
        "HOME": str(config.home),
        "CODEX_HOME": str(home),
        "CODEXX_ACTIVE_ACCOUNT": "cloud",
        "CODEXX_ACTIVE_HOME": str(home),
        "CODEXX_ACTIVE_PINNED": "1",
        "CLOUDX_MODE": "cloud",
        "CLOUDX_MODE_LEASE_ID": lease_id,
        "CLOUDX_MODE_BROKER_PORT": str(port),
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    lines = ["export %s=%s" % (key, shlex.quote(value)) for key, value in values.items()]
    lines.extend("unset %s" % name for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"))
    return "\n".join(lines)


def exit_mode(config: LocalConfig) -> str:
    _release_cloud_lease(config)
    lines = accounts.shell_exit(config).splitlines()
    lines.extend(_clear_mode_lines())
    return "\n".join(lines)
