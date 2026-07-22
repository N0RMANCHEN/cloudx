from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import codexx_cli, modes  # noqa: E402
from cloudx_local import local_cpa, local_cpa_import  # noqa: E402
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

    def test_top_level_help_exposes_modes_import_and_diagnosis(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(codexx_cli.main(["--help"]), 0)
        rendered = output.getvalue()
        self.assertIn("codexx cloud", rendered)
        self.assertIn("codexx import <source>", rendered)
        self.assertIn("codexx upgrade [--check]", rendered)
        self.assertIn("codexx cloud upgrade [--check]", rendered)
        self.assertIn("codexx diagnose [api|cpa|cloud] [--json]", rendered)
        self.assertIn("official executable", rendered)

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

    @mock.patch("cloudx_local.codexx_cli.cloud_cli.main", return_value=0)
    def test_cloud_upgrade_routes_without_selecting_cloud_mode(self, cloud_command: mock.Mock) -> None:
        self.assertEqual(codexx_cli.main(["cloud", "upgrade", "--check"]), 0)
        cloud_command.assert_called_once_with(["upgrade", "--check"])

    @mock.patch("cloudx_local.codexx_cli.upgrade.run", return_value=0)
    @mock.patch("cloudx_local.codexx_cli.LocalConfig.load")
    def test_local_upgrade_routes_to_local_endpoint(self, load: mock.Mock, run: mock.Mock) -> None:
        load.return_value = self.config
        self.assertEqual(codexx_cli.main(["upgrade", "--json"]), 0)
        run.assert_called_once_with(self.config, "local", ["--json"])

    @mock.patch("cloudx_local.codexx_cli.api_diagnosis.run", return_value=0)
    @mock.patch("cloudx_local.codexx_cli.LocalConfig.load")
    def test_api_and_cloud_diagnosis_route_without_changing_mode(
        self,
        load: mock.Mock,
        diagnose: mock.Mock,
    ) -> None:
        load.return_value = self.config
        self.assertEqual(codexx_cli.main(["api", "diagnose", "--json"]), 0)
        diagnose.assert_called_once_with(self.config, ["--json"], forced_target="api")
        diagnose.reset_mock()
        self.assertEqual(codexx_cli.main(["cloud", "diagnose"]), 0)
        diagnose.assert_called_once_with(self.config, [], forced_target="cloud")

    @mock.patch("cloudx_local.codexx_cli.local_cpa.import_local", return_value=0)
    @mock.patch("cloudx_local.codexx_cli.LocalConfig.load")
    def test_plain_import_routes_to_local_cpa(self, load: mock.Mock, local_import: mock.Mock) -> None:
        load.return_value = self.config
        self.assertEqual(codexx_cli.main(["import", "fixture.json"]), 0)
        local_import.assert_called_once_with(self.config, "fixture.json", [])

    @mock.patch("cloudx_local.local_cpa.local_cpa_import.import_path")
    def test_local_cpa_adapter_is_native_and_preserves_raw_counts(self, import_path: mock.Mock) -> None:
        import_path.return_value = local_cpa_import.LocalImportResult(False, 1, 0, 1, 0, 1, 0, 1)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(local_cpa.import_local(self.config, "fixture.json", []), 0)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "discovered: 1",
                "skipped: 0",
                "parsed: 1",
                "duplicates: 0",
                "unchanged: 0",
                "imported: 1",
                "verified: 1",
            ],
        )
        import_path.assert_called_once_with(
            self.config,
            pathlib.Path("fixture.json"),
            force=True,
            dry_run=False,
            name_prefix="codexx-import",
        )

    @mock.patch("cloudx_local.local_cpa.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.local_cpa.local_cpa_import.import_path")
    def test_interactive_local_import_matches_cloud_summary_shape(
        self,
        import_path: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        import_path.return_value = local_cpa_import.LocalImportResult(False, 1, 0, 1, 0, 1, 0, 1)
        output = StringIO()

        with redirect_stdout(output):
            result = local_cpa.import_local(self.config, "fixture.json", [])

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Credential import",
                "  Status: succeeded",
                "  Destination: local CPA",
                "  Imported: 1",
                "  Skipped: 0",
                "  Verification: complete (1 verified)",
                "  Source files: 1 discovered, 0 ignored",
                "  Credentials: 1 parsed, 0 duplicates",
                "  Adapter: Cloudx native compatibility (external local CPA)",
            ],
        )

    @mock.patch("cloudx_local.local_cpa.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.local_cpa.local_cpa_import.import_path")
    def test_interactive_local_failure_is_clear_and_redacts_input_snippet(
        self,
        import_path: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        import_path.side_effect = local_cpa_import.LocalImportError(
            "invalid_json",
            "unable to parse JSON near `"
            '{"access_token":"sk-sensitive-token-value"}`',
        )
        errors = StringIO()

        with redirect_stderr(errors):
            result = local_cpa.import_local(self.config, "fixture.json", [])

        self.assertEqual(result, 1)
        self.assertIn("Status: failed", errors.getvalue())
        self.assertIn("Reason (invalid_json): unable to parse JSON near <redacted input>", errors.getvalue())
        self.assertNotIn("sk-sensitive-token-value", errors.getvalue())

    def test_local_import_reason_redacts_agent_private_key(self) -> None:
        secret = "private-agent-key-material"
        rendered = local_cpa.import_ui.sanitize_reason("agent_private_key=%s" % secret)
        self.assertIn("agent_private_key=<redacted>", rendered)
        self.assertNotIn(secret, rendered)

    @mock.patch("cloudx_local.local_cpa.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.local_cpa.local_cpa_import.import_path")
    def test_interactive_local_no_change_explains_ignored_and_duplicate_items(
        self,
        import_path: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        import_path.return_value = local_cpa_import.LocalImportResult(False, 2, 1, 3, 1, 0, 1, 0)
        output = StringIO()

        with redirect_stdout(output):
            result = local_cpa.import_local(self.config, "fixtures", [])

        self.assertEqual(result, 0)
        self.assertIn("Status: succeeded (no changes)", output.getvalue())
        self.assertIn("Skipped: 3", output.getvalue())
        self.assertIn(
            "Skip reason: 1 ignored source file, 1 duplicate credential, 1 unchanged credential",
            output.getvalue(),
        )
        self.assertIn("Verification: complete (no new credentials to verify)", output.getvalue())

    @mock.patch("cloudx_local.local_cpa.local_cpa_import.import_path")
    def test_local_import_json_preview_is_structured_and_nonzero_failure_is_structured(
        self,
        import_path: mock.Mock,
    ) -> None:
        import_path.return_value = local_cpa_import.LocalImportResult(True, 1, 0, 1, 0, 1, 0, 0)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(local_cpa.import_local(self.config, "fixture.json", ["--dry-run", "--json"]), 0)
        document = __import__("json").loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.local-cpa-import.v1")
        self.assertEqual(document["status"], "preview")
        self.assertFalse(document["externalService"]["managed"])
        import_path.side_effect = local_cpa_import.LocalImportError("source_missing", "source is missing")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(local_cpa.import_local(self.config, "missing.json", ["--json"]), 1)
        failure = __import__("json").loads(output.getvalue())
        self.assertEqual(failure["status"], "rejected")
        self.assertEqual(failure["errors"][0]["code"], "source_missing")

    def test_local_import_reads_redirected_stdin_without_writing_on_preview(self) -> None:
        raw = __import__("json").dumps({
            "type": "codex",
            "email": "stdin@example.com",
            "access_token": "header.stdin.signature",
        })
        output = StringIO()
        with mock.patch("cloudx_local.local_cpa.sys.stdin", StringIO(raw)), redirect_stdout(output):
            self.assertEqual(local_cpa.import_local(self.config, "-", ["--dry-run", "--json"]), 0)
        document = __import__("json").loads(output.getvalue())
        self.assertEqual(document["status"], "preview")
        self.assertEqual(document["counts"]["parsed"], 1)
        self.assertFalse((self.home / ".cli-proxy-api").exists())


if __name__ == "__main__":
    unittest.main()
