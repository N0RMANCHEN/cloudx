from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import cpa_capabilities  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


class _Response:
    status = 200

    def __init__(self, capabilities: str):
        self.headers = {cpa_capabilities.CAPABILITY_HEADER: capabilities}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, unused_type: object, unused_value: object, unused_traceback: object) -> None:
        return None


class CpaCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.binary = self.home / "bin/cli-proxy-api"
        self.binary.parent.mkdir()
        self.manifest = self.home / "bin/cli-proxy-api.capabilities.json"
        self.config = LocalConfig(
            home=self.home,
            config_path=self.home / "config.json",
            state_dir=self.home / "state",
            data_dir=self.home / "data",
            cache_dir=self.home / "cache",
            accounts_dir=self.home / "accounts",
            codex_binary="codex",
            ssh_binary="ssh",
            ssh_host="cloud",
            remote_helper="cloudx-remote",
            legacy_forward_host="gateway",
            legacy_forward_port=8317,
            legacy_api_key_command="legacy",
            broker_idle_seconds=900,
            endpoint_timeout_seconds=5.0,
            endpoint_attempts=3,
            release_repository="repo",
            local_cpa_binary=self.binary,
            local_cpa_capability_manifest=self.manifest,
            local_cpa_capability_probe_url="http://127.0.0.1:8317/healthz",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _runtime(self, payload: bytes, version: str = "7.0.2-agent-identity") -> None:
        self.binary.write_bytes(payload)
        self.binary.chmod(0o700)
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": cpa_capabilities.SCHEMA,
                    "binary": str(self.binary),
                    "binarySha256": hashlib.sha256(payload).hexdigest(),
                    "runtimeVersion": version,
                    "capabilities": ["codex-agent-identity-v1"],
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _opener(capabilities: str = "codex-agent-identity-v1") -> mock.Mock:
        return mock.Mock(return_value=_Response(capabilities))

    def test_hash_bound_live_capability_is_accepted(self) -> None:
        self._runtime(b"patched-runtime-v1")
        opener = self._opener()

        result = cpa_capabilities.attest(
            self.config,
            "codex-agent-identity-v1",
            opener=opener,
        )

        self.assertEqual(result.runtime_version, "7.0.2-agent-identity")
        self.assertEqual(result.binary_sha256, hashlib.sha256(b"patched-runtime-v1").hexdigest())
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8317/healthz")

    def test_binary_only_upstream_update_invalidates_stale_capability(self) -> None:
        self._runtime(b"patched-runtime-v1")
        self.binary.write_bytes(b"unattested-upstream-update")
        self.binary.chmod(0o700)
        opener = self._opener()

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(self.config, "codex-agent-identity-v1", opener=opener)

        self.assertEqual(caught.exception.reason, "binary_digest_mismatch")
        opener.assert_not_called()

    def test_matching_runtime_update_is_automatically_reattested(self) -> None:
        opener = self._opener()
        self._runtime(b"patched-runtime-v1")
        first = cpa_capabilities.attest(self.config, "codex-agent-identity-v1", opener=opener)
        self._runtime(b"patched-runtime-v2", "7.1.0-agent-identity")
        second = cpa_capabilities.attest(self.config, "codex-agent-identity-v1", opener=opener)

        self.assertNotEqual(first.binary_sha256, second.binary_sha256)
        self.assertEqual(second.runtime_version, "7.1.0-agent-identity")

    def test_manifest_without_matching_live_header_is_rejected(self) -> None:
        self._runtime(b"patched-runtime-v1")

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(
                self.config,
                "codex-agent-identity-v1",
                opener=self._opener("another-capability-v1"),
            )

        self.assertEqual(caught.exception.reason, "live_capability_missing")

    def test_probe_is_restricted_to_literal_loopback_health_endpoint(self) -> None:
        self._runtime(b"patched-runtime-v1")
        unsafe = replace(
            self.config,
            local_cpa_capability_probe_url="https://example.com/healthz",
        )
        opener = self._opener()

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(unsafe, "codex-agent-identity-v1", opener=opener)

        self.assertEqual(caught.exception.reason, "probe_invalid")
        opener.assert_not_called()

    def test_symlink_manifest_is_rejected(self) -> None:
        self._runtime(b"patched-runtime-v1")
        real = self.home / "real-manifest.json"
        self.manifest.replace(real)
        self.manifest.symlink_to(real)

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(
                self.config,
                "codex-agent-identity-v1",
                opener=self._opener(),
            )

        self.assertEqual(caught.exception.reason, "manifest_unavailable")


if __name__ == "__main__":
    unittest.main()
