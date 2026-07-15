from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from install_scoped_gateway_key import (  # noqa: E402
    CONFIRMATION,
    append_api_key,
    environment_document,
    main,
    top_level_value,
    verify_artifact,
)


CONFIG = b"""# gateway\nhost: 100.90.97.113\nport: 8317\napi-keys:\n  - \"one\"\n  # retained comment\n  - \"two\"\nauth-dir: /var/lib/example\n"""


class ScopedKeyInstallerTests(unittest.TestCase):
    def test_append_preserves_document_and_counts_existing_keys(self) -> None:
        updated, count = append_api_key(CONFIG, "cloudx-fixture")
        self.assertEqual(count, 2)
        self.assertIn(b'  - "cloudx-fixture"\n', updated)
        self.assertIn(b"  # retained comment\n", updated)
        self.assertTrue(updated.endswith(b"auth-dir: /var/lib/example\n"))

    def test_inline_api_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "block list"):
            append_api_key(b"api-keys: [one, two]\n", "cloudx-fixture")

    def test_top_level_host_and_port_are_read_without_other_values(self) -> None:
        self.assertEqual(top_level_value(CONFIG, "host"), "100.90.97.113")
        self.assertEqual(top_level_value(CONFIG, "port"), "8317")

    def test_default_invocation_is_a_read_only_confirmation_plan(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--release-version",
                "0.1.2",
                "--build-commit",
                "abcdef0",
                "--gateway-version",
                "7.2.71",
            ])
        self.assertEqual(code, 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], CONFIRMATION)
        self.assertEqual(document["releaseVersion"], "0.1.2")
        self.assertEqual(document["artifact"], "/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz")

    def test_environment_is_bound_to_the_requested_release(self) -> None:
        document = environment_document(
            "/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz",
            "0.1.2",
            "abcdef0",
            "7.2.71",
            "127.0.0.1",
            8317,
        ).decode("utf-8")
        self.assertIn("CLOUDX_CLOUD_ARTIFACT=/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz", document)
        self.assertIn("CLOUDX_DEPLOYMENT_ID=shadow-0.1.2", document)
        self.assertNotIn("shadow-0.1.1", document)

    def test_invalid_release_version_is_rejected_before_confirmation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exact semantic version"):
            main([
                "--release-version",
                "latest",
                "--build-commit",
                "abcdef0",
                "--gateway-version",
                "7.2.71",
            ])

    @mock.patch("install_scoped_gateway_key.subprocess.run")
    def test_artifact_version_mismatch_is_rejected(self, run: mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({
                "schema": "cloudx.self-check.v1",
                "component": "cloud",
                "version": "0.1.1",
                "status": "ok",
            }),
            stderr="",
        )
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            verify_artifact(pathlib.Path("/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz"), "0.1.2")

    @mock.patch("install_scoped_gateway_key.subprocess.run", side_effect=subprocess.TimeoutExpired("self-check", 20))
    def test_artifact_self_check_timeout_is_safe(self, unused_run: mock.Mock) -> None:
        with self.assertRaisesRegex(RuntimeError, "could not run"):
            verify_artifact(pathlib.Path("/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz"), "0.1.2")


if __name__ == "__main__":
    unittest.main()
