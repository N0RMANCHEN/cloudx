from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import codexx_cli, modes  # noqa: E402
from cloudx_local import local_cpa  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402
from cloudx_local.remote import RemoteEndpoint  # noqa: E402


class ModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
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
        )
        for name in ("api", "soul0"):
            (self.config.accounts_dir / name / ".codex").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @mock.patch("cloudx_local.modes.prepare_cloud_mode")
    @mock.patch("cloudx_local.modes.probe_endpoint", return_value=200)
    @mock.patch("cloudx_local.modes.BrokerClient")
    @mock.patch("cloudx_local.modes.RemoteClient")
    def test_cloud_mode_returns_shell_owned_profile(
        self,
        remote_class: mock.Mock,
        broker_class: mock.Mock,
        unused_probe: mock.Mock,
        prepare: mock.Mock,
    ) -> None:
        remote_class.return_value.resolve_endpoint.return_value = RemoteEndpoint(
            "cloudx", "scoped", "gateway", 8317, {}
        )
        broker_class.return_value.acquire_for_owner.return_value = {
            "leaseId": "11111111-1111-1111-1111-111111111111",
            "publicPort": 24567,
            "generation": 1,
        }
        prepare.return_value = self.home / "cloud-home"
        output = modes.select_cloud(self.config, 4321)
        self.assertIn("CODEXX_ACTIVE_ACCOUNT=cloud", output)
        self.assertIn("CLOUDX_MODE=cloud", output)
        self.assertIn("CLOUDX_MODE_BROKER_PORT=24567", output)
        broker_class.return_value.acquire_for_owner.assert_called_once_with("cloud", "gateway", 8317, 4321)

    @mock.patch("cloudx_local.modes.BrokerClient")
    def test_account_mode_releases_existing_cloud_lease(self, broker_class: mock.Mock) -> None:
        with mock.patch.dict(os.environ, {"CLOUDX_MODE_LEASE_ID": "lease"}, clear=False):
            output = modes.select_account(self.config, "api")
        broker_class.return_value.release.assert_called_once_with("lease")
        self.assertIn("CODEXX_ACTIVE_ACCOUNT=api", output)
        self.assertIn("CLOUDX_MODE=api", output)

    @mock.patch("cloudx_local.codexx_cli.cloud_cli.main", return_value=0)
    def test_cloud_import_routes_to_remote_importer(self, remote_import: mock.Mock) -> None:
        self.assertEqual(codexx_cli.main(["cloud", "import", "fixture.json", "--dry-run"]), 0)
        remote_import.assert_called_once_with(["import", "fixture.json", "--dry-run"])

    @mock.patch("cloudx_local.codexx_cli.local_cpa.import_local", return_value=0)
    @mock.patch("cloudx_local.codexx_cli.LocalConfig.load")
    def test_plain_import_routes_to_local_cpa(self, load: mock.Mock, local_import: mock.Mock) -> None:
        load.return_value = self.config
        self.assertEqual(codexx_cli.main(["import", "fixture.json"]), 0)
        local_import.assert_called_once_with(self.config, "fixture.json", [])

    @mock.patch("cloudx_local.local_cpa.subprocess.run")
    def test_local_cpa_adapter_is_explicitly_legacy(self, run: mock.Mock) -> None:
        command = self.home / ".local/bin/codexx-legacy"
        command.parent.mkdir(parents=True)
        command.write_text("fixture", encoding="utf-8")
        run.return_value.returncode = 0
        self.assertEqual(local_cpa.import_local(self.config, "fixture.json", []), 0)
        run.assert_called_once_with([str(command), "import", "fixture.json"], check=False)


if __name__ == "__main__":
    unittest.main()
