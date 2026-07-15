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

from install import confirmation, main, maybe_backup_legacy  # noqa: E402


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
        self.assertEqual(document["confirmation"], confirmation("local", document["version"]))

    def test_cloud_plan_does_not_restart_services(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["cloud", "--version", "0.1.6"]), 0)
        document = json.loads(output.getvalue())
        self.assertIn("no service restart", document["cloudActions"])

    @mock.patch("install.install_local", return_value={"status": "installed"})
    def test_apply_requires_exact_confirmation(self, install_local: mock.Mock) -> None:
        with self.assertRaisesRegex(RuntimeError, "confirmation"):
            main(["local", "--version", "0.1.6", "--apply", "--confirm", "wrong"])
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
