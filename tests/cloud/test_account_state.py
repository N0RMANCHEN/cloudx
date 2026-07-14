from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.account_state import AccountStateRejected, adapt_file, adapt_legacy_quota_state  # noqa: E402
from cloudx_cloud.cli import main  # noqa: E402
from cloudx_cloud.config import Config  # noqa: E402
from cloudx_cloud.gateway import GatewayProbe  # noqa: E402
from cloudx_cloud.health import build_health  # noqa: E402


def legacy_state(**changes: object) -> dict:
    document = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total": 5,
        "ready": 2,
        "warning": 1,
        "limited": 1,
        "failed": 1,
        "account_names": ["must-not-be-copied"],
    }
    document.update(changes)
    return document


class AccountStateAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "legacy.json"
        self.destination = self.root / "run/accounts.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_adapter_emits_only_observed_classifications(self) -> None:
        document = adapt_legacy_quota_state(json.dumps(legacy_state()).encode("utf-8"))
        self.assertEqual(document["accountCounts"], {
            "total": 5,
            "available": 3,
            "limited": 1,
            "unavailable": 0,
        })
        self.assertEqual(document["unobservedAccounts"], 1)
        self.assertNotIn("must-not-be-copied", json.dumps(document))

    def test_adapter_rejects_inconsistent_counts_without_source_values(self) -> None:
        secret = "private-account-name"
        raw = json.dumps(legacy_state(total=99, account_names=[secret])).encode("utf-8")
        with self.assertRaises(AccountStateRejected) as captured:
            adapt_legacy_quota_state(raw)
        self.assertNotIn(secret, str(captured.exception))

    def test_file_adapter_publishes_atomic_readable_state(self) -> None:
        self.source.write_text(json.dumps(legacy_state()), encoding="utf-8")
        document = adapt_file(self.source, self.destination)
        self.assertEqual(json.loads(self.destination.read_text(encoding="utf-8")), document)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o644)

    def test_cli_adapts_configured_source(self) -> None:
        self.source.write_text(json.dumps(legacy_state()), encoding="utf-8")
        config = mock.Mock(account_state_source_path=self.source, account_state_path=self.destination)
        output = StringIO()
        with mock.patch("cloudx_cloud.cli.Config.from_environment", return_value=config), redirect_stdout(output):
            self.assertEqual(main(["adapt-account-state", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["schema"], "cloudx.account-state.v1")
        self.assertTrue(self.destination.is_file())

    @mock.patch("cloudx_cloud.health.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_health_freshness_uses_observation_time(self, unused_probe: mock.Mock) -> None:
        observed = datetime.now(timezone.utc) - timedelta(hours=2)
        self.source.write_text(json.dumps(legacy_state(checked_at=observed.isoformat())), encoding="utf-8")
        adapt_file(self.source, self.destination)
        credential = self.root / "credential"
        credential.write_text("secret\n", encoding="utf-8")
        credential.chmod(0o600)
        config = Config(
            auth_dir=self.root / "auth",
            import_lock_path=self.root / "run/import.lock",
            health_path=self.root / "run/health.json",
            account_state_path=self.destination,
            account_state_source_path=self.source,
            gateway_url="http://127.0.0.1:1",
            gateway_version="external",
            gateway_forward_host="127.0.0.1",
            gateway_forward_port=8317,
            client_credential_file=credential,
            deployment_id="test",
            build_commit="abcdef0",
        )
        health = build_health(config)
        self.assertEqual(health["freshness"]["state"], "stale")
        self.assertGreaterEqual(health["freshness"]["ageSeconds"], 7100)


if __name__ == "__main__":
    unittest.main()
