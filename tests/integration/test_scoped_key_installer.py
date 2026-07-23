from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from install_scoped_gateway_key import (  # noqa: E402
    CONFIRMATION,
    api_keys,
    append_api_key,
    environment_document,
    main,
    top_level_value,
    scoped_key_lock,
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
        self.assertEqual(api_keys(updated), ["one", "two", "cloudx-fixture"])

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

    def test_custom_contract_path_is_rejected_before_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            main([
                "--release-version", "0.1.30",
                "--build-commit", "abcdef0",
                "--gateway-version", "7.2.71",
                "--credential", "/tmp/other-credential",
            ])

    def test_transaction_lock_rejects_an_active_peer_and_closes_descriptor(self) -> None:
        metadata = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        closed = mock.Mock()
        with mock.patch("install_scoped_gateway_key.os.open", return_value=9), mock.patch(
            "install_scoped_gateway_key.os.fstat", return_value=metadata
        ), mock.patch(
            "install_scoped_gateway_key.fcntl.flock", side_effect=OSError("busy")
        ), mock.patch("install_scoped_gateway_key.os.close", closed):
            with self.assertRaisesRegex(RuntimeError, "another scoped key transaction"):
                with scoped_key_lock():
                    self.fail("lock unexpectedly acquired")
        closed.assert_called_once_with(9)

    def test_success_writes_secret_free_rotation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            config = root / "config.yaml"
            credential = root / "client-credential"
            environment = root / "cloudx-shadow.env"
            transaction = root / "rotation"
            transaction.mkdir()
            config.write_bytes(CONFIG)
            credential.write_text("one\n", encoding="utf-8")
            credential.chmod(0o600)
            environment.write_text("OLD=1\n", encoding="utf-8")
            environment.chmod(0o640)

            def atomic(path: pathlib.Path, data: bytes, mode: int, uid: int, gid: int) -> None:
                del uid, gid
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(mode)

            def atomic_document(path: pathlib.Path, document: dict) -> None:
                atomic(path, (json.dumps(document) + "\n").encode(), 0o600, 0, 0)

            output = StringIO()
            patches = [
                mock.patch("install_scoped_gateway_key.DEFAULT_CONFIG", config),
                mock.patch("install_scoped_gateway_key.DEFAULT_CREDENTIAL", credential),
                mock.patch("install_scoped_gateway_key.DEFAULT_ENVIRONMENT", environment),
                mock.patch("install_scoped_gateway_key.os.geteuid", return_value=0),
                mock.patch("install_scoped_gateway_key.verify_artifact"),
                mock.patch("install_scoped_gateway_key.scoped_key_lock", return_value=nullcontext()),
                mock.patch("install_scoped_gateway_key.pwd.getpwnam", return_value=SimpleNamespace(pw_uid=os.getuid())),
                mock.patch("install_scoped_gateway_key.grp.getgrnam", return_value=SimpleNamespace(gr_gid=os.getgid())),
                mock.patch("install_scoped_gateway_key.systemctl", side_effect=lambda *a, **k: "100"),
                mock.patch("install_scoped_gateway_key.wait_active", return_value=200),
                mock.patch("install_scoped_gateway_key.probe", return_value=200),
                mock.patch("install_scoped_gateway_key.inotify_watch_count", return_value=2),
                mock.patch("install_scoped_gateway_key.secrets.token_urlsafe", return_value="fixture-new"),
                mock.patch("install_scoped_gateway_key._prepare_rotation_directory", return_value=("20260723T120000Z-1234abcd", transaction)),
                mock.patch("install_scoped_gateway_key._private_root_directory"),
                mock.patch("install_scoped_gateway_key.atomic_write", side_effect=atomic),
                mock.patch("install_scoped_gateway_key.atomic_json", side_effect=atomic_document),
                mock.patch("install_scoped_gateway_key.time.time", return_value=123456789),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(redirect_stdout(output))
                self.assertEqual(main([
                    "--apply", "--confirm", CONFIRMATION,
                    "--release-version", "0.1.30",
                    "--build-commit", "abcdef0",
                    "--gateway-version", "7.2.71",
                ]), 0)
            receipt = json.loads(output.getvalue())
            document = json.loads((transaction / "manifest.json").read_text())
            self.assertEqual(document["status"], "rotated")
            self.assertTrue(document["previousCredentialRetained"])
            self.assertFalse(document["previousCredentialRevoked"])
            self.assertEqual(document["gatewayKeyCountBefore"], 2)
            self.assertEqual(document["gatewayKeyCountAfter"], 3)
            self.assertEqual(receipt["transactionId"], "20260723T120000Z-1234abcd")
            for secret in ("one", "cloudx-fixture-new"):
                self.assertNotIn(secret, output.getvalue())
                self.assertNotIn(secret, (transaction / "manifest.json").read_text())

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
