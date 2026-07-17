from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local.config import LocalConfig  # noqa: E402
from cloudx_local.remote import RemoteClient  # noqa: E402


def completed(code: int, document: object = None, text: bytes = b"") -> subprocess.CompletedProcess:
    stdout = json.dumps(document).encode() if document is not None else text
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=b"")


class FakeRemote(RemoteClient):
    def __init__(self, config: LocalConfig, helper: dict, legacy: subprocess.CompletedProcess) -> None:
        super().__init__(config)
        self.responses = helper
        self.legacy = legacy

    def _helper(self, args, input_bytes=None, timeout=20.0):
        return self.responses[args[0]]

    def _ssh(self, remote_command, input_bytes=None, timeout=20.0):
        return self.legacy


class RemoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        home = pathlib.Path(self.temp.name)
        self.config = LocalConfig(
            home=home,
            config_path=home / "config.json",
            state_dir=home / "state",
            data_dir=home / "data",
            cache_dir=home / "cache",
            accounts_dir=home / "accounts",
            codex_binary="codex",
            ssh_binary="ssh",
            ssh_host="cloud",
            remote_helper="cloudx-remote",
            legacy_forward_host="legacy-host",
            legacy_forward_port=8317,
            legacy_api_key_command="legacy-key",
            broker_idle_seconds=900,
            endpoint_timeout_seconds=5.0,
            endpoint_attempts=3,
            release_repository="repo",
        )
        self.handshake = {
            "schema": "cloudx.handshake.v1",
            "productVersion": "0.1.0",
            "protocol": {"min": 1, "max": 1},
        }
        self.client = {
            "schema": "cloudx.client-config.v1",
            "apiKey": "scoped-key",
            "forwardHost": "gateway",
            "forwardPort": 8317,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_helper_endpoint(self) -> None:
        remote = FakeRemote(
            self.config,
            {"handshake": completed(0, self.handshake), "client-config": completed(0, self.client)},
            completed(0, text=b"legacy"),
        )
        endpoint = remote.resolve_endpoint()
        self.assertEqual(endpoint.mode, "cloudx")
        self.assertEqual(endpoint.api_key, "scoped-key")

    def test_missing_helper_uses_explicit_legacy_bridge(self) -> None:
        remote = FakeRemote(
            self.config,
            {"handshake": completed(127), "client-config": completed(127)},
            completed(0, text=b"legacy-key\n"),
        )
        endpoint = remote.resolve_endpoint()
        self.assertEqual(endpoint.mode, "legacy_bridge")
        self.assertEqual(endpoint.forward_host, "legacy-host")

    def test_incompatible_helper_does_not_silently_fallback(self) -> None:
        incompatible = dict(self.handshake)
        incompatible["protocol"] = {"min": 3, "max": 4}
        remote = FakeRemote(
            self.config,
            {"handshake": completed(0, incompatible), "client-config": completed(0, self.client)},
            completed(0, text=b"legacy-key\n"),
        )
        with self.assertRaises(RuntimeError):
            remote.resolve_endpoint()

    @mock.patch("cloudx_local.remote.subprocess.run")
    def test_read_only_ssh_detaches_stdin_but_payload_commands_pipe_bytes(self, run: mock.Mock) -> None:
        run.return_value = completed(0, {})
        remote = RemoteClient(self.config)

        remote._ssh(["handshake"])
        read_only = run.call_args.kwargs
        self.assertEqual(read_only["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", read_only)

        remote._ssh(["import"], input_bytes=b"payload")
        payload = run.call_args.kwargs
        self.assertEqual(payload["input"], b"payload")
        self.assertNotIn("stdin", payload)

    def test_import_attributes_ssh_authentication_failure(self) -> None:
        remote = RemoteClient(self.config)
        response = subprocess.CompletedProcess(
            [],
            255,
            stdout=b"",
            stderr=b"cloud: Permission denied (publickey).\n",
        )

        with mock.patch.object(remote, "_helper", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "SSH authentication was rejected"):
                remote.import_payload(b"payload", dry_run=False, force=False)

    def test_import_preserves_structured_remote_rejection(self) -> None:
        remote = RemoteClient(self.config)
        document = {
            "schema": "cloudx.import.v1",
            "requestId": "deadbeefdeadbeef",
            "requestHash": "0" * 64,
            "status": "rejected",
            "dryRun": False,
            "written": 0,
            "skipped": 0,
            "errors": [{"code": "invalid_json", "message": "import source contains invalid JSON"}],
        }
        response = completed(2, document)

        with mock.patch.object(remote, "_helper", return_value=response):
            self.assertEqual(remote.import_payload(b"payload", dry_run=False, force=False), document)


if __name__ == "__main__":
    unittest.main()
