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
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_capabilities  # noqa: E402
from cloudx_cloud.config import Config  # noqa: E402


class _Response:
    status = 200

    def __init__(self, capabilities: str):
        self.headers = {cpa_capabilities.CAPABILITY_HEADER: capabilities}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, unused_type: object, unused_value: object, unused_traceback: object) -> None:
        return None


class CloudCpaCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.binary = self.root / "bin/cli-proxy-api"
        self.binary.parent.mkdir()
        self.manifest = self.root / "cloud-cpa-capabilities.json"
        self.config = Config(
            auth_dir=self.root / "auth",
            import_lock_path=self.root / "run/import.lock",
            health_path=self.root / "run/health.json",
            account_state_path=self.root / "run/accounts.json",
            account_state_source_path=self.root / "legacy/state.json",
            gateway_url="http://127.0.0.1:8317",
            gateway_version="7.2.71",
            gateway_forward_host="127.0.0.1",
            gateway_forward_port=8317,
            client_credential_file=self.root / "credential",
            deployment_id="test",
            build_commit="abcdef0",
            cpa_binary=self.binary,
            cpa_capability_manifest=self.manifest,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _runtime(self, payload: bytes, version: str = "7.2.71-agent-identity") -> None:
        self.binary.write_bytes(payload)
        self.binary.chmod(0o700)
        self.manifest.write_text(
            json.dumps({
                "schema": cpa_capabilities.SCHEMA,
                "binary": str(self.binary),
                "binarySha256": hashlib.sha256(payload).hexdigest(),
                "runtimeVersion": version,
                "capabilities": ["codex-agent-identity-v1"],
            }),
            encoding="utf-8",
        )

    @staticmethod
    def _opener(capabilities: str = "codex-agent-identity-v1") -> mock.Mock:
        return mock.Mock(return_value=_Response(capabilities))

    def test_hash_bound_live_cloud_capability_is_accepted(self) -> None:
        self._runtime(b"patched-cloud-runtime-v1")
        opener = self._opener()

        result = cpa_capabilities.attest(
            self.config,
            "codex-agent-identity-v1",
            opener=opener,
        )

        self.assertEqual(result.runtime_version, "7.2.71-agent-identity")
        self.assertEqual(
            result.binary_sha256,
            hashlib.sha256(b"patched-cloud-runtime-v1").hexdigest(),
        )
        self.assertEqual(opener.call_args.args[0].full_url, "http://127.0.0.1:8317/healthz")

    def test_binary_replacement_invalidates_stale_cloud_manifest(self) -> None:
        self._runtime(b"patched-cloud-runtime-v1")
        self.binary.write_bytes(b"unattested-cloud-update")
        self.binary.chmod(0o700)
        opener = self._opener()

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(self.config, "codex-agent-identity-v1", opener=opener)

        self.assertEqual(caught.exception.reason, "binary_digest_mismatch")
        opener.assert_not_called()

    def test_missing_live_cloud_capability_is_rejected(self) -> None:
        self._runtime(b"patched-cloud-runtime-v1")

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(
                self.config,
                "codex-agent-identity-v1",
                opener=self._opener("another-capability-v1"),
            )

        self.assertEqual(caught.exception.reason, "live_capability_missing")

    def test_probe_uses_only_the_configured_plain_http_gateway(self) -> None:
        self._runtime(b"patched-cloud-runtime-v1")
        invalid = replace(self.config, gateway_url="https://127.0.0.1:8317")
        opener = self._opener()

        with self.assertRaises(cpa_capabilities.CpaCapabilityError) as caught:
            cpa_capabilities.attest(invalid, "codex-agent-identity-v1", opener=opener)

        self.assertEqual(caught.exception.reason, "probe_invalid")
        opener.assert_not_called()

    def test_symlink_manifest_is_rejected(self) -> None:
        self._runtime(b"patched-cloud-runtime-v1")
        real = self.root / "real-manifest.json"
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
