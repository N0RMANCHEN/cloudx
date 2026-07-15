from __future__ import annotations

import json
import pathlib
import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from install import confirmation, main  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
