from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import install_phi_consumer_gateway_key as installer  # noqa: E402
from install_scoped_gateway_key import Snapshot  # noqa: E402


CONFIG = b"""# gateway
host: 127.0.0.1
port: 8317
api-keys:
  - "cloudx-existing"
auth-dir: /var/lib/example
"""


class PhiConsumerKeyInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.config = self.root / "config.yaml"
        self.credential = self.root / "consumers/phi-cloud/credential"
        self.client = self.root / "client-credential"
        self.config.write_bytes(CONFIG)
        self.client.write_text("cloudx-client\n", encoding="utf-8")
        self.client.chmod(0o600)
        self.credential.parent.mkdir(parents=True, mode=0o750)
        self.constants = mock.patch.multiple(
            installer,
            DEFAULT_CONFIG=self.config,
            DEFAULT_CREDENTIAL=self.credential,
            DEFAULT_CLOUDX_CLIENT_CREDENTIAL=self.client,
            DEFAULT_GROUP="phi-cloudx-consumer",
            DEFAULT_UNIT="cliproxy.service",
        )
        self.constants.start()

    def tearDown(self) -> None:
        self.constants.stop()
        self.temp.cleanup()

    @staticmethod
    def _atomic_write(path: pathlib.Path, data: bytes, mode: int, uid: int, gid: int) -> None:
        del uid, gid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)

    @staticmethod
    def _systemctl(*arguments: str, capture: bool = False) -> str:
        del capture
        return "100" if arguments[:1] == ("show",) else ""

    def _apply_patches(self, *, probe_side_effect: object = None):
        patches = [
            mock.patch.object(installer.os, "geteuid", return_value=0),
            mock.patch.object(installer, "verify_artifact"),
            mock.patch.object(installer, "scoped_key_lock", return_value=nullcontext()),
            mock.patch.object(installer.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=os.getgid())),
            mock.patch.object(installer, "_validate_credential_directory"),
            mock.patch.object(installer, "atomic_write", side_effect=self._atomic_write),
            mock.patch.object(installer, "systemctl", side_effect=self._systemctl),
            mock.patch.object(installer, "wait_active", return_value=200),
            mock.patch.object(installer, "inotify_watch_count", return_value=2),
            mock.patch.object(installer.secrets, "token_urlsafe", return_value="fixture-new-key"),
            mock.patch.object(installer.time, "time_ns", return_value=123456789),
        ]
        if probe_side_effect is None:
            patches.append(mock.patch.object(installer, "probe", return_value=200))
        else:
            patches.append(mock.patch.object(installer, "probe", side_effect=probe_side_effect))
        return patches

    def test_default_invocation_is_non_authorizing_and_does_not_read_files(self) -> None:
        self.config.unlink()
        self.client.unlink()
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(installer.main(["--release-version", "0.1.15"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], installer.CONFIRMATION)
        self.assertEqual(document["credentialClass"], "scoped_phi_consumer")
        self.assertEqual(
            document["releaseArtifact"],
            "/opt/cloudx/releases/0.1.15/cloudx-cloud.pyz",
        )
        self.assertTrue(document["gatewayRestartRequired"])
        self.assertFalse(document["phiServiceRestartRequired"])
        self.assertIn("phi_consumer_group_exists", document["preconditions"])
        self.assertIn("credential_directory_root_group_0750", document["preconditions"])
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_custom_contract_paths_are_rejected_even_for_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            installer.main([
                "--release-version",
                "0.1.15",
                "--credential",
                str(self.root / "other"),
            ])
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            installer.main([
                "--release-version",
                "0.1.15",
                "--artifact",
                str(self.root / "candidate.pyz"),
            ])

    def test_apply_requires_exact_confirmation_before_root_or_artifact_checks(self) -> None:
        with mock.patch.object(installer, "verify_artifact") as verify:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                installer.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--release-version",
                    "0.1.15",
                ])
        verify.assert_not_called()

    def test_apply_requires_the_preprovisioned_consumer_group(self) -> None:
        with mock.patch.object(installer.os, "geteuid", return_value=0), mock.patch.object(
            installer, "verify_artifact"
        ), mock.patch.object(installer.grp, "getgrnam", side_effect=KeyError("missing")):
            with self.assertRaisesRegex(RuntimeError, "group is missing"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])

    def test_apply_rejects_a_broad_cloudx_client_credential(self) -> None:
        self.client.chmod(0o644)
        patches = self._apply_patches()
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "permissions are too broad"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])

    def test_success_adds_only_phi_key_and_preserves_cloudx_client(self) -> None:
        before_client = self.client.read_bytes()
        output = StringIO()
        patches = self._apply_patches()
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(installer.main([
                "--apply",
                "--confirm",
                installer.CONFIRMATION,
                "--release-version",
                "0.1.15",
            ]), 0)
        document = json.loads(output.getvalue())
        key = "cloudx-phi-fixture-new-key"
        self.assertIn(json.dumps(key).encode("utf-8"), self.config.read_bytes())
        self.assertEqual(self.credential.read_text(encoding="utf-8"), key + "\n")
        self.assertEqual(stat.S_IMODE(self.credential.stat().st_mode), 0o640)
        self.assertEqual(self.client.read_bytes(), before_client)
        self.assertTrue(document["cloudxClientCredentialUnchanged"])
        self.assertFalse(document["previousCredentialRetained"])
        self.assertFalse(document["previousCredentialRevoked"])
        self.assertFalse(document["phiServiceRestarted"])
        self.assertNotIn(key, output.getvalue())
        backup = self.config.parent / "backups/config.yaml.before-phi-consumer-123456789"
        self.assertEqual(backup.read_bytes(), CONFIG)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)

    def test_failed_probe_restores_config_and_credential_without_touching_client(self) -> None:
        before_client = self.client.read_bytes()
        patches = self._apply_patches(probe_side_effect=RuntimeError("probe failed"))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertEqual(self.config.read_bytes(), CONFIG)
        self.assertFalse(self.credential.exists())
        self.assertEqual(self.client.read_bytes(), before_client)
        self.assertEqual(list((self.config.parent / "backups").iterdir()), [])

    def test_existing_credential_must_remain_in_gateway_for_overlap_rotation(self) -> None:
        credential = Snapshot(True, b"cloudx-phi-old\n", 0o640, 0, os.getgid())
        with self.assertRaisesRegex(RuntimeError, "not retained"):
            installer._previous_key_is_retained(CONFIG, credential)
        retained = CONFIG.replace(
            b'  - "cloudx-existing"\n',
            b'  - "cloudx-existing"\n  - "cloudx-phi-old"\n',
        )
        self.assertTrue(installer._previous_key_is_retained(retained, credential))

    def test_snapshot_rejects_symlink_and_oversized_credential(self) -> None:
        source = self.root / "source"
        source.write_text("value", encoding="utf-8")
        alias = self.root / "alias"
        alias.symlink_to(source)
        with self.assertRaisesRegex(RuntimeError, "non-symlink"):
            installer._safe_snapshot(alias, "fixture", required=True, maximum=4096)
        source.write_bytes(b"x" * 4097)
        with self.assertRaisesRegex(RuntimeError, "size limit"):
            installer._safe_snapshot(source, "fixture", required=True, maximum=4096)


if __name__ == "__main__":
    unittest.main()
