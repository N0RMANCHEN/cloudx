from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from bootstrap_cloud_helper import confirmation_for, launcher_documents, main, previous_release, verify_artifact  # noqa: E402


class CloudHelperBootstrapTests(unittest.TestCase):
    def test_default_invocation_is_a_read_only_versioned_plan(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--release-version", "0.1.2", "--operator", "hirohi"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], confirmation_for("0.1.2"))
        self.assertEqual(document["artifact"], "/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz")
        self.assertEqual(document["helper"], "/usr/local/bin/cloudx-remote")
        self.assertEqual(document["runner"], "/usr/local/libexec/cloudx-remote-runner")
        self.assertEqual(document["sudoers"], "/etc/sudoers.d/cloudx-remote")
        self.assertEqual(document["normalIdentity"], "cloudx")
        self.assertEqual(document["releaseIdentity"], "root")
        self.assertFalse(document["serviceRestartRequired"])

    def test_invalid_release_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exact semantic version"):
            main(["--release-version", "latest", "--operator", "hirohi"])

    def test_launcher_keeps_runtime_and_release_identities_separate(self) -> None:
        runner, helper, sudoers = launcher_documents("hirohi")
        self.assertIn(b"/opt/cloudx/current/cloudx-cloud.pyz", runner)
        self.assertIn(b"release-stage|release-activate|release-rollback) user=root", helper)
        self.assertIn(b"*) user=cloudx", helper)
        self.assertIn(b"hirohi ALL=(cloudx)", sudoers)
        self.assertIn(b"hirohi ALL=(root)", sudoers)
        self.assertNotIn(b"cloudx-remote-runner import", sudoers.splitlines()[1])

    def test_invalid_operator_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exact local user"):
            main(["--release-version", "0.1.2", "--operator", "hirohi ALL=(root)"])

    @mock.patch("bootstrap_cloud_helper.run_document")
    def test_installed_shell_helper_is_executed_directly(self, run: mock.Mock) -> None:
        run.return_value = {
            "schema": "cloudx.self-check.v1",
            "component": "cloud",
            "version": "0.1.2",
            "status": "ok",
        }
        verify_artifact(pathlib.Path("/usr/local/bin/cloudx-remote"), "0.1.2", direct=True)
        run.assert_called_once_with(
            ["/usr/local/bin/cloudx-remote", "self-check"],
            "cloud artifact self-check",
        )

    def test_previous_release_selects_highest_staged_n_minus_one(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            for version in ("0.1.0", "0.1.1", "0.1.2"):
                release = root / "releases" / version
                release.mkdir(parents=True)
                (release / "cloudx-cloud.pyz").write_bytes(b"fixture")
            self.assertEqual(previous_release(root, "0.1.2").name, "0.1.1")


if __name__ == "__main__":
    unittest.main()
