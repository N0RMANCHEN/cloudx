from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.cli import client_config, handshake  # noqa: E402
from cloudx_cloud.config import Config  # noqa: E402
from cloudx_cloud.gateway import GatewayProbe  # noqa: E402
from cloudx_cloud.health import build_health, publish  # noqa: E402


class CloudHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.credential = self.root / "credential"
        self.credential.write_text("secret-key\n", encoding="utf-8")
        self.credential.chmod(0o600)
        self.config = Config(
            auth_dir=self.root / "auth",
            import_lock_path=self.root / "run/import.lock",
            health_path=self.root / "run/health.json",
            account_state_path=self.root / "run/accounts.json",
            gateway_url="http://127.0.0.1:1",
            gateway_version="7.2.71",
            gateway_forward_host="127.0.0.1",
            gateway_forward_port=8317,
            client_credential_file=self.credential,
            deployment_id="test",
            build_commit="abcdef0",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @mock.patch("cloudx_cloud.cli.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_handshake_has_no_secret(self, unused_probe: mock.Mock) -> None:
        document = handshake(self.config)
        serialized = json.dumps(document)
        self.assertEqual(document["schema"], "cloudx.handshake.v1")
        self.assertNotIn("secret-key", serialized)
        self.assertIn("client-config.v1", document["capabilities"])

    def test_client_config_requires_private_file(self) -> None:
        document = client_config(self.config)
        self.assertEqual(document["apiKey"], "secret-key")
        self.credential.chmod(0o644)
        with self.assertRaises(RuntimeError):
            client_config(self.config)

    @mock.patch("cloudx_cloud.health.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_health_is_secret_free_and_publish_is_readable(self, unused_probe: mock.Mock) -> None:
        self.config.auth_dir.mkdir()
        (self.config.auth_dir / "account.json").write_text("{}", encoding="utf-8")
        document = build_health(self.config)
        self.assertEqual(document["accountCounts"]["total"], 0)
        self.assertEqual(document["freshness"]["state"], "unknown")
        self.assertNotIn("secret-key", json.dumps(document))
        publish(self.config.health_path, document)
        self.assertEqual(stat.S_IMODE(self.config.health_path.stat().st_mode), 0o644)
        self.assertEqual(json.loads(self.config.health_path.read_text())["schema"], "cloudx.health.v1")


if __name__ == "__main__":
    unittest.main()
