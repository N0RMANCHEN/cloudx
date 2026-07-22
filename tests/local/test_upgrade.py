from __future__ import annotations

import contextlib
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import cli, upgrade, updater  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


class UpgradeTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _selector(self, version: str) -> pathlib.Path:
        root = self.home / ".local/lib/cloudx"
        release = root / "releases" / version
        release.mkdir(parents=True, exist_ok=True)
        (release / "cloudx-local.pyz").write_bytes(version.encode("ascii"))
        current = root / "current"
        current.unlink(missing_ok=True)
        current.symlink_to(release)
        return current

    @staticmethod
    def _index(version: str = "0.1.26") -> dict:
        return {
            "schema": "cloudx.release-index.v1",
            "version": version,
            "manifestSha256": "a" * 64,
            "artifactRef": "refs/heads/release-artifacts/v%s" % version,
        }

    def test_local_upgrade_stages_and_activates_only_local(self) -> None:
        current = self._selector("0.1.25")

        def activate(*unused_args: object, **unused_kwargs: object) -> dict:
            self._selector("0.1.26")
            return {"schema": "cloudx.release-activate.v1", "status": "active"}

        with mock.patch.object(upgrade, "VERSION", "0.1.25"), mock.patch.object(
            updater, "stable_index", return_value=self._index()
        ), mock.patch.object(
            updater, "resolved_stage_source", return_value=contextlib.nullcontext(pathlib.Path("/release"))
        ), mock.patch.object(
            updater, "stage", return_value={"local": "staged", "cloud": "not-requested"}
        ) as stage, mock.patch.object(
            updater, "stage_cloud"
        ) as cloud_stage, mock.patch.object(
            updater, "apply", side_effect=activate
        ) as apply:
            document = upgrade.upgrade_endpoint(self.config, "local")

        self.assertEqual(current.resolve().name, "0.1.26")
        self.assertEqual(document["status"], "upgraded")
        self.assertEqual(document["verificationScope"], "complete-release-chain")
        self.assertFalse(document["serviceRestarted"])
        self.assertFalse(document["officialCodexReplaced"])
        self.assertTrue(document["shellReloadRecommended"])
        self.assertTrue(stage.call_args.kwargs["local_only"])
        self.assertEqual(stage.call_args.kwargs["expected_manifest_sha256"], "a" * 64)
        self.assertEqual(stage.call_args.kwargs["expected_version"], "0.1.26")
        cloud_stage.assert_not_called()
        self.assertTrue(apply.call_args.args[3])
        self.assertFalse(apply.call_args.kwargs.get("cloud_only", False))

    def test_cloud_upgrade_stages_and_activates_only_cloud(self) -> None:
        with mock.patch.object(updater, "stable_index", return_value=self._index()), mock.patch.object(
            upgrade, "_cloud_current", side_effect=["0.1.25", "0.1.26"]
        ), mock.patch.object(
            updater, "resolved_stage_source", return_value=contextlib.nullcontext(pathlib.Path("/release"))
        ), mock.patch.object(
            updater, "stage_cloud", return_value={"local": "not-requested", "cloud": "staged"}
        ) as cloud_stage, mock.patch.object(updater, "stage") as local_stage, mock.patch.object(
            updater, "apply", return_value={"schema": "cloudx.release-activate.v1", "status": "active"}
        ) as apply:
            document = upgrade.upgrade_endpoint(self.config, "cloud")

        self.assertEqual(document["status"], "upgraded")
        self.assertFalse(document["shellReloadRecommended"])
        cloud_stage.assert_called_once()
        self.assertEqual(cloud_stage.call_args.kwargs["expected_version"], "0.1.26")
        local_stage.assert_not_called()
        self.assertTrue(apply.call_args.kwargs["cloud_only"])

    def test_check_only_reports_update_without_staging(self) -> None:
        with mock.patch.object(updater, "stable_index", return_value=self._index()), mock.patch.object(
            upgrade, "_local_current", return_value="0.1.25"
        ), mock.patch.object(updater, "resolved_stage_source") as source, mock.patch.object(
            updater, "apply"
        ) as apply:
            document = upgrade.upgrade_endpoint(self.config, "local", check_only=True)
        self.assertEqual(document["status"], "update-available")
        self.assertEqual(document["verificationScope"], "signed-index-only")
        self.assertEqual(document["currentAfter"], "0.1.25")
        source.assert_not_called()
        apply.assert_not_called()

    def test_local_activation_failure_restores_prior_selector(self) -> None:
        self._selector("0.1.25")

        def fail_after_switch(*unused_args: object, **unused_kwargs: object) -> dict:
            self._selector("0.1.26")
            raise OSError("fixture")

        def restore(*unused_args: object, **unused_kwargs: object) -> dict:
            self._selector("0.1.25")
            return {"status": "active"}

        with mock.patch.object(upgrade, "VERSION", "0.1.25"), mock.patch.object(
            updater, "stable_index", return_value=self._index()
        ), mock.patch.object(
            updater, "resolved_stage_source", return_value=contextlib.nullcontext(pathlib.Path("/release"))
        ), mock.patch.object(updater, "stage", return_value={"local": "staged"}), mock.patch.object(
            updater, "apply", side_effect=fail_after_switch
        ), mock.patch.object(updater, "rollback", side_effect=restore) as rollback:
            with self.assertRaisesRegex(RuntimeError, "restored the prior release"):
                upgrade.upgrade_endpoint(self.config, "local")
        self.assertEqual((self.home / ".local/lib/cloudx/current").resolve().name, "0.1.25")
        rollback.assert_called_once_with(self.config, "0.1.25", local_only=True)

    def test_json_output_uses_secret_free_upgrade_contract(self) -> None:
        document = upgrade._result(
            "local",
            "up-to-date",
            "0.1.26",
            "0.1.26",
            "0.1.26",
            "refs/heads/release-artifacts/v0.1.26",
            "a" * 64,
        )
        output = StringIO()
        with mock.patch.object(upgrade, "upgrade_endpoint", return_value=document), redirect_stdout(output):
            self.assertEqual(upgrade.run(self.config, "local", ["--json"]), 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["schema"], "cloudx.upgrade.v1")
        self.assertTrue(parsed["signedIndexVerified"])
        self.assertEqual(parsed["verificationScope"], "signed-index-only")
        self.assertFalse(parsed["backgroundActivation"])
        self.assertFalse(parsed["externalCpaManaged"])
        self.assertEqual(parsed["manifestSha256"], "a" * 64)
        serialized = json.dumps(parsed).casefold()
        for forbidden in ("api_key", "token", "credential", "private_key"):
            self.assertNotIn(forbidden, serialized)

    def test_manifest_binding_rejects_a_different_release(self) -> None:
        manifest = self.home / "manifest.json"
        manifest.write_bytes(b"manifest")
        with self.assertRaisesRegex(RuntimeError, "signed stable index"):
            updater._verify_manifest_binding(manifest, "0" * 64)

    def test_downgrade_is_rejected_before_staging(self) -> None:
        with mock.patch.object(updater, "stable_index", return_value=self._index("0.1.25")), mock.patch.object(
            upgrade, "_local_current", return_value="0.1.26"
        ), mock.patch.object(updater, "resolved_stage_source") as source:
            with self.assertRaisesRegex(RuntimeError, "downgrade"):
                upgrade.upgrade_endpoint(self.config, "local")
        source.assert_not_called()

    def test_direct_upgrade_does_not_start_a_competing_background_check(self) -> None:
        with mock.patch.object(sys, "argv", ["codexx"]), mock.patch.object(
            cli, "_schedule_update_check"
        ) as scheduled, mock.patch.object(cli.codexx_cli, "main", return_value=0):
            self.assertEqual(cli.main(["upgrade", "--check"]), 0)
            self.assertEqual(cli.main(["cloud", "upgrade", "--check"]), 0)
        scheduled.assert_not_called()


if __name__ == "__main__":
    unittest.main()
