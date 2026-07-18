from __future__ import annotations

import json
import pathlib
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from install import (  # noqa: E402
    confirmation,
    install_local,
    main,
    maybe_backup_legacy,
    native_profile_seed_account,
    stage_cloud,
    stage_local,
)


class InstallTests(unittest.TestCase):
    def test_repository_install_entrypoint_is_executable(self) -> None:
        self.assertTrue(os.access(ROOT / "install", os.X_OK))

    @mock.patch("install.detected_endpoint", return_value="local")
    def test_default_plan_includes_shell_install(self, unused_detect: mock.Mock) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["endpoint"], "local")
        self.assertIn("install shell source", document["localActions"])
        self.assertIn("preserve a complete native profile or seed an absent profile", document["localActions"])
        self.assertEqual(document["confirmation"], confirmation("local", document["version"]))

    def test_complete_native_profile_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            native = home / ".codex"
            native.mkdir(parents=True)
            (native / "auth.json").write_text("{}\n", encoding="utf-8")
            (native / "config.toml").write_text("model = \"test\"\n", encoding="utf-8")
            config = SimpleNamespace(home=home)

            self.assertIsNone(native_profile_seed_account(config, "soul0"))

    def test_absent_native_profile_uses_requested_seed(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            accounts = home / ".codex-accounts"
            seed = accounts / "soul0/.codex"
            seed.mkdir(parents=True)
            (seed / "auth.json").write_text("{}\n", encoding="utf-8")
            (seed / "config.toml").write_text("model = \"test\"\n", encoding="utf-8")
            config = SimpleNamespace(home=home, accounts_dir=accounts)
            self.assertEqual(native_profile_seed_account(config, "soul0"), "soul0")

    def test_absent_native_profile_rejects_an_invalid_seed_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            config = SimpleNamespace(home=home, accounts_dir=home / ".codex-accounts")
            with self.assertRaisesRegex(RuntimeError, "seed account"):
                native_profile_seed_account(config, "soul0")

    def test_partial_or_symlinked_native_profile_fails_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            native = home / ".codex"
            native.mkdir(parents=True)
            (native / "auth.json").write_text("{}\n", encoding="utf-8")
            config = SimpleNamespace(home=home)
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                native_profile_seed_account(config, "soul0")
            (native / "config.toml").symlink_to(native / "auth.json")
            with self.assertRaisesRegex(RuntimeError, "symlinks"):
                native_profile_seed_account(config, "soul0")

    def test_non_regular_complete_native_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            native = home / ".codex"
            (native / "auth.json").mkdir(parents=True)
            (native / "config.toml").mkdir()
            config = SimpleNamespace(home=home)
            with self.assertRaisesRegex(RuntimeError, "regular files"):
                native_profile_seed_account(config, "soul0")

    @mock.patch("install.updater.apply", return_value={"status": "active"})
    @mock.patch("install.updater.stage", return_value={"local": "staged"})
    @mock.patch("install.fetch_release")
    @mock.patch("install.maybe_backup_legacy", return_value=None)
    @mock.patch("install.LocalConfig.load")
    def test_local_upgrade_does_not_reseed_complete_native_profile(
        self,
        load_config: mock.Mock,
        unused_backup: mock.Mock,
        fetch_release: mock.Mock,
        unused_stage: mock.Mock,
        apply_release: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            native = home / ".codex"
            native.mkdir(parents=True)
            (native / "auth.json").write_text("{}\n", encoding="utf-8")
            (native / "config.toml").write_text("model = \"preserve\"\n", encoding="utf-8")
            load_config.return_value = SimpleNamespace(home=home)
            fetch_release.side_effect = lambda repository, version, destination: destination

            result = install_local("0.1.18", "soul0", "git@example.invalid/cloudx.git")

        self.assertFalse(result["nativeProfileChanged"])
        self.assertIsNone(apply_release.call_args.kwargs["seed_account"])

    @mock.patch("install.updater.apply", return_value={"status": "active"})
    @mock.patch("install.updater.stage", return_value={"local": "staged"})
    @mock.patch("install.fetch_release")
    @mock.patch("install.maybe_backup_legacy", return_value=None)
    @mock.patch("install.LocalConfig.load")
    def test_local_first_install_seeds_a_valid_absent_native_profile(
        self,
        load_config: mock.Mock,
        unused_backup: mock.Mock,
        fetch_release: mock.Mock,
        unused_stage: mock.Mock,
        apply_release: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            accounts = home / ".codex-accounts"
            seed = accounts / "soul0/.codex"
            seed.mkdir(parents=True)
            (seed / "auth.json").write_text("{}\n", encoding="utf-8")
            (seed / "config.toml").write_text("model = \"seed\"\n", encoding="utf-8")
            load_config.return_value = SimpleNamespace(home=home, accounts_dir=accounts)
            fetch_release.side_effect = lambda repository, version, destination: destination

            result = install_local("0.1.18", "soul0", "git@example.invalid/cloudx.git")

        self.assertTrue(result["nativeProfileChanged"])
        self.assertEqual(apply_release.call_args.kwargs["seed_account"], "soul0")

    @mock.patch("install.updater.apply")
    @mock.patch("install.updater.stage")
    @mock.patch("install.fetch_release")
    @mock.patch("install.maybe_backup_legacy")
    @mock.patch("install.LocalConfig.load")
    def test_partial_native_profile_rejects_before_any_install_mutation(
        self,
        load_config: mock.Mock,
        backup_legacy: mock.Mock,
        fetch_release: mock.Mock,
        stage_release: mock.Mock,
        apply_release: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            native = home / ".codex"
            native.mkdir(parents=True)
            (native / "auth.json").write_text("{}\n", encoding="utf-8")
            load_config.return_value = SimpleNamespace(home=home)

            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                install_local("0.1.18", "soul0", "git@example.invalid/cloudx.git")

        backup_legacy.assert_not_called()
        fetch_release.assert_not_called()
        stage_release.assert_not_called()
        apply_release.assert_not_called()

    def test_cloud_plan_does_not_restart_services(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["cloud", "--version", "0.1.6"]), 0)
        document = json.loads(output.getvalue())
        self.assertIn("no service restart", document["cloudActions"])

    def test_stage_only_plan_is_explicitly_non_activating(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(["local", "--version", "0.1.13", "--stage-only"]),
                0,
            )
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.install-stage-plan.v1")
        self.assertEqual(
            document["confirmation"],
            confirmation("local", "0.1.13", stage_only=True),
        )
        self.assertIn("no activation", document["localActions"])
        self.assertIn("no shell, profile, backup, or process change", document["localActions"])

    def test_cloud_stage_only_plan_has_no_activation_or_restart(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(["cloud", "--version", "0.1.13", "--stage-only"]),
                0,
            )
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.install-stage-plan.v1")
        self.assertEqual(document["confirmation"], "STAGE CLOUDX CLOUD 0.1.13")
        self.assertIn("no activation", document["cloudActions"])
        self.assertIn("no service restart", document["cloudActions"])

    @mock.patch("install.install_local", return_value={"status": "installed"})
    def test_apply_requires_exact_confirmation(self, install_local: mock.Mock) -> None:
        with self.assertRaisesRegex(RuntimeError, "confirmation"):
            main(["local", "--version", "0.1.6", "--apply", "--confirm", "wrong"])
        with redirect_stdout(StringIO()):
            self.assertEqual(
                main([
                    "local",
                    "--version",
                    "0.1.6",
                    "--apply",
                    "--confirm",
                    "INSTALL CLOUDX LOCAL 0.1.6",
                ]),
                0,
            )
        install_local.assert_called_once()

    @mock.patch("install.stage_local", return_value={"status": "staged"})
    @mock.patch("install.install_local")
    def test_stage_only_apply_uses_distinct_confirmation_and_never_installs(
        self,
        install_local: mock.Mock,
        stage_local_call: mock.Mock,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "confirmation"):
            main([
                "local",
                "--version",
                "0.1.13",
                "--stage-only",
                "--apply",
                "--confirm",
                "INSTALL CLOUDX LOCAL 0.1.13",
            ])
        with redirect_stdout(StringIO()):
            self.assertEqual(
                main([
                    "local",
                    "--version",
                    "0.1.13",
                    "--stage-only",
                    "--apply",
                    "--confirm",
                    "STAGE CLOUDX LOCAL 0.1.13",
                ]),
                0,
            )
        stage_local_call.assert_called_once()
        install_local.assert_not_called()

    @mock.patch("install.updater.stage", return_value={"activated": False, "local": "staged"})
    @mock.patch("install.fetch_release")
    @mock.patch("install.LocalConfig.load", return_value=SimpleNamespace())
    def test_stage_local_does_not_touch_legacy_shell_or_profiles(
        self,
        unused_config: mock.Mock,
        fetch_release: mock.Mock,
        updater_stage: mock.Mock,
    ) -> None:
        fetch_release.side_effect = lambda repository, version, destination: destination
        result = stage_local("0.1.13", "git@example.invalid/cloudx.git")
        self.assertFalse(result["activated"])
        self.assertFalse(result["shellSourceInstalled"])
        self.assertFalse(result["nativeProfileChanged"])
        self.assertFalse(result["legacyBackupChanged"])
        updater_stage.assert_called_once()
        self.assertTrue(updater_stage.call_args.kwargs["local_only"])

    @mock.patch("install.cloud_release.stage", return_value={"status": "staged"})
    @mock.patch("install.release_bundle", return_value=b"bundle")
    @mock.patch("install.fetch_release")
    @mock.patch("install.os.geteuid", return_value=0)
    def test_stage_cloud_skips_activation_and_service_prerequisites(
        self,
        unused_euid: mock.Mock,
        fetch_release: mock.Mock,
        unused_bundle: mock.Mock,
        cloud_stage: mock.Mock,
    ) -> None:
        fetch_release.side_effect = lambda repository, version, destination: destination
        result = stage_cloud("0.1.13", "git@example.invalid/cloudx.git")
        self.assertFalse(result["activated"])
        self.assertFalse(result["serviceRestarted"])
        cloud_stage.assert_called_once_with(b"bundle")

    @mock.patch("install.activate_recovery_paths")
    @mock.patch("install.create_backup")
    def test_legacy_backup_activates_recovery_paths(
        self,
        create_backup: mock.Mock,
        activate_recovery_paths: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            state = home / ".local/state/cloudx"
            entrypoint = home / ".local/bin/codexx"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("legacy", encoding="utf-8")
            config = SimpleNamespace(home=home, state_dir=state)

            backup = maybe_backup_legacy(config)

        self.assertIsNotNone(backup)
        destination = pathlib.Path(str(backup))
        create_backup.assert_called_once_with(home, destination)
        activate_recovery_paths.assert_called_once_with(home, destination)


if __name__ == "__main__":
    unittest.main()
