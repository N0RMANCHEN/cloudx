from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from .config import LocalConfig
from .version import PROTOCOL_MAX, PROTOCOL_MIN


class HelperUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteEndpoint:
    mode: str
    api_key: str
    forward_host: str
    forward_port: int
    handshake: Dict[str, Any]


class RemoteClient:
    def __init__(self, config: LocalConfig) -> None:
        self.config = config

    def _ssh(self, remote_command: Sequence[str] | str, input_bytes: Optional[bytes] = None, timeout: float = 20.0) -> subprocess.CompletedProcess:
        command_text = remote_command if isinstance(remote_command, str) else shlex.join(list(remote_command))
        command = [
            self.config.ssh_binary,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            self.config.ssh_host,
            command_text,
        ]
        try:
            run_options: Dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "timeout": timeout,
                "check": False,
            }
            if input_bytes is None:
                run_options["stdin"] = subprocess.DEVNULL
            else:
                run_options["input"] = input_bytes
            return subprocess.run(
                command,
                **run_options,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("ssh executable was not found: %s" % self.config.ssh_binary) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("SSH command timed out") from exc

    def _helper(self, args: Sequence[str], input_bytes: Optional[bytes] = None, timeout: float = 20.0) -> subprocess.CompletedProcess:
        return self._ssh([*shlex.split(self.config.remote_helper), *args], input_bytes=input_bytes, timeout=timeout)

    @staticmethod
    def _document(completed: subprocess.CompletedProcess, label: str) -> Dict[str, Any]:
        if completed.returncode != 0:
            raise RuntimeError("%s failed with exit %d" % (label, completed.returncode))
        try:
            value = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("%s returned invalid JSON" % label) from exc
        if not isinstance(value, dict):
            raise RuntimeError("%s returned a non-object response" % label)
        return value

    def handshake(self) -> Dict[str, Any]:
        completed = self._helper(["handshake", "--json"])
        if completed.returncode != 0:
            raise HelperUnavailable("remote Cloudx helper is unavailable")
        document = self._document(completed, "remote handshake")
        if document.get("schema") != "cloudx.handshake.v1":
            raise RuntimeError("remote handshake schema is unsupported")
        protocol = document.get("protocol")
        if not isinstance(protocol, dict):
            raise RuntimeError("remote handshake has no protocol range")
        remote_min = int(protocol.get("min", 0))
        remote_max = int(protocol.get("max", 0))
        if max(PROTOCOL_MIN, remote_min) > min(PROTOCOL_MAX, remote_max):
            raise RuntimeError("local and remote Cloudx protocols are incompatible")
        return document

    def resolve_endpoint(self) -> RemoteEndpoint:
        try:
            handshake = self.handshake()
        except HelperUnavailable:
            return self.resolve_legacy_endpoint()
        completed = self._helper(["client-config", "--json"])
        client = self._document(completed, "remote client config")
        if client.get("schema") != "cloudx.client-config.v1":
            raise RuntimeError("remote client config schema is unsupported")
        api_key = str(client.get("apiKey") or "").strip()
        host = str(client.get("forwardHost") or "").strip()
        port = int(client.get("forwardPort") or 0)
        if not api_key or not host or port < 1 or port > 65535:
            raise RuntimeError("remote client config is incomplete")
        return RemoteEndpoint("cloudx", api_key, host, port, handshake)

    def resolve_legacy_endpoint(self) -> RemoteEndpoint:
        completed = self._ssh(self.config.legacy_api_key_command)
        key = completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or not key:
            raise RuntimeError("legacy bridge could not obtain the scoped gateway credential")
        return RemoteEndpoint(
            mode="legacy_bridge",
            api_key=key,
            forward_host=self.config.legacy_forward_host,
            forward_port=self.config.legacy_forward_port,
            handshake={
                "schema": "cloudx.handshake.v1",
                "productVersion": "legacy",
                "buildCommit": "legacy",
                "protocol": {"min": 1, "max": 1},
                "capabilities": ["legacy-gateway.v1"],
                "deploymentId": "legacy-bridge",
                "gateway": {"version": "external", "status": "unknown"},
                "importerContractVersion": 0,
            },
        )

    def health(self) -> Dict[str, Any]:
        completed = self._helper(["health", "--json"])
        document = self._document(completed, "remote health")
        if document.get("schema") != "cloudx.health.v1":
            raise RuntimeError("remote health schema is unsupported")
        return document

    def import_payload(self, raw: bytes, dry_run: bool, force: bool) -> Dict[str, Any]:
        args = ["import"]
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force")
        completed = self._helper(args, input_bytes=raw, timeout=60.0)
        document = self._document(completed, "remote import") if completed.returncode == 0 else None
        if document is None:
            try:
                value = json.loads(completed.stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise RuntimeError(self._import_failure_reason(completed))
            if not isinstance(value, dict):
                raise RuntimeError(self._import_failure_reason(completed))
            document = value
        if document.get("schema") != "cloudx.import.v1":
            raise RuntimeError("remote import schema is unsupported")
        return document

    @staticmethod
    def _import_failure_reason(completed: subprocess.CompletedProcess) -> str:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace").casefold()
        if "could not resolve hostname" in stderr or "name or service not known" in stderr:
            return "cloud importer SSH host could not be resolved; check the configured SSH host"
        if "permission denied" in stderr:
            return "cloud importer SSH authentication was rejected"
        if "connection refused" in stderr:
            return "cloud importer SSH connection was refused"
        if "connection timed out" in stderr or "operation timed out" in stderr:
            return "cloud importer SSH connection timed out"
        if "no route to host" in stderr or "network is unreachable" in stderr:
            return "cloud importer SSH host is unreachable"
        if "cloudx-remote" in stderr and ("not found" in stderr or "command not found" in stderr):
            return "remote Cloudx importer is unavailable"
        if completed.returncode == 255:
            return "cloud importer could not be reached over SSH; check network and SSH configuration"
        return "cloud importer failed before returning a structured result (exit %d)" % completed.returncode

    def stage_release(self, bundle: bytes) -> Dict[str, Any]:
        completed = self._helper(["release-stage"], input_bytes=bundle, timeout=120.0)
        return self._document(completed, "remote release stage")

    def release_status(self) -> Dict[str, Any]:
        completed = self._helper(["release-status"])
        document = self._document(completed, "remote release status")
        if document.get("schema") != "cloudx.release-status.v1":
            raise RuntimeError("remote release status schema is unsupported")
        return document

    def activate_release(self, version: str) -> Dict[str, Any]:
        completed = self._helper(["release-activate", "--version", version, "--confirm", version], timeout=30.0)
        document = self._document(completed, "remote release activation")
        if document.get("schema") != "cloudx.release-activate.v1":
            raise RuntimeError("remote release activation schema is unsupported")
        return document

    def rollback_release(self, version: str) -> Dict[str, Any]:
        completed = self._helper(["release-rollback", "--confirm", version], timeout=30.0)
        document = self._document(completed, "remote release rollback")
        if document.get("schema") != "cloudx.release-rollback.v1":
            raise RuntimeError("remote release rollback schema is unsupported")
        return document
