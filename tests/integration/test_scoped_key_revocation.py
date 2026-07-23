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
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import revoke_scoped_gateway_key as revoker  # noqa: E402
from install_scoped_gateway_key import Snapshot, sha256  # noqa: E402


OLD_KEY = "cloudx-old-fixture"
NEW_KEY = "cloudx-new-fixture"
OTHER_KEY = "cloudx-other-fixture"
CONFIG = (
    "host: 127.0.0.1\n"
    "port: 8317\n"
    "api-keys:\n"
    "  - %s\n"
    "  - %s\n"
    "  - %s\n"
    "auth-dir: /var/lib/example\n"
    % (json.dumps(OTHER_KEY), json.dumps(OLD_KEY), json.dumps(NEW_KEY))
).encode("utf-8")


def manifest(transaction_id: str = "20260723T120000Z-1234abcd") -> dict:
    return {
        "schema": revoker.ROTATION_SCHEMA,
        "status": "rotated",
        "transactionId": transaction_id,
        "releaseVersion": "0.1.30",
        "artifact": "/opt/cloudx/releases/0.1.30/cloudx-cloud.pyz",
        "unit": revoker.DEFAULT_UNIT,
        "config": str(revoker.DEFAULT_CONFIG),
        "credential": str(revoker.DEFAULT_CREDENTIAL),
        "environment": "/etc/cloudx/cloudx-shadow.env",
        "oldCredentialSha256": sha256(OLD_KEY.encode("utf-8")),
        "newCredentialSha256": sha256(NEW_KEY.encode("utf-8")),
        "configSha256Before": "1" * 64,
        "configSha256After": sha256(CONFIG),
        "gatewayKeyCountBefore": 2,
        "gatewayKeyCountAfter": 3,
        "oldPid": 100,
        "newPid": 200,
        "gatewayHttpStatus": 200,
        "inotifyWatches": 2,
        "backup": "/etc/cliproxy/backups/config.yaml.fixture",
        "previousCredentialRetained": True,
        "previousCredentialRevoked": False,
    }


class ScopedKeyRevocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.config = self.root / "config.yaml"
        self.credential = self.root / "client-credential"
        self.transaction = self.root / "transaction"
        self.transaction.mkdir(mode=0o700)
        self.config.write_bytes(CONFIG)
        self.credential.write_text(NEW_KEY + "\n", encoding="utf-8")
        self.credential.chmod(0o600)
        self.constants = mock.patch.multiple(
            revoker,
            DEFAULT_CONFIG=self.config,
            DEFAULT_CREDENTIAL=self.credential,
            DEFAULT_ROTATION_ROOT=self.root,
        )
        self.constants.start()
        (self.transaction / "manifest.json").write_text(
            json.dumps(manifest()) + "\n", encoding="utf-8"
        )
        (self.transaction / "manifest.json").chmod(0o600)

    def tearDown(self) -> None:
        self.constants.stop()
        self.temp.cleanup()

    @staticmethod
    def _atomic_write(path: pathlib.Path, data: bytes, mode: int, uid: int, gid: int) -> None:
        del uid, gid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)

    @classmethod
    def _atomic_json(cls, path: pathlib.Path, document: dict) -> None:
        cls._atomic_write(
            path,
            (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"),
            0o600,
            0,
            0,
        )

    def _snapshot(self, path: pathlib.Path, label: str, maximum: int) -> Snapshot:
        del label, maximum
        data = path.read_bytes()
        metadata = path.stat()
        return Snapshot(True, data, stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)

    def _patches(self, *, new_probe: object = 200, old_status: object = 401):
        return [
            mock.patch.object(revoker.os, "geteuid", return_value=0),
            mock.patch.object(revoker, "verify_artifact"),
            mock.patch.object(revoker, "scoped_key_lock", return_value=nullcontext()),
            mock.patch.object(revoker, "_transaction_directory", return_value=self.transaction),
            mock.patch.object(revoker, "_manifest", return_value=manifest()),
            mock.patch.object(revoker, "_safe_snapshot", side_effect=self._snapshot),
            mock.patch.object(revoker, "atomic_write", side_effect=self._atomic_write),
            mock.patch.object(revoker, "atomic_json", side_effect=self._atomic_json),
            mock.patch.object(revoker, "systemctl", side_effect=lambda *a, **k: "100"),
            mock.patch.object(revoker, "wait_active", return_value=200),
            mock.patch.object(revoker, "probe", side_effect=new_probe if isinstance(new_probe, Exception) else None, return_value=None if isinstance(new_probe, Exception) else new_probe),
            mock.patch.object(revoker, "wait_status", side_effect=old_status if isinstance(old_status, Exception) else None, return_value=None if isinstance(old_status, Exception) else old_status),
            mock.patch.object(revoker, "inotify_watch_count", return_value=2),
        ]

    def test_default_plan_is_non_authorizing_and_reads_no_files(self) -> None:
        self.config.unlink()
        self.credential.unlink()
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(revoker.main([
                "--release-version", "0.1.30",
                "--transaction-id", "20260723T120000Z-1234abcd",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], revoker.PLAN_SCHEMA)
        self.assertEqual(document["confirmation"], revoker.CONFIRMATION)
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_remove_exact_digest_preserves_order_and_other_keys(self) -> None:
        updated, removed, count = revoker.remove_api_key_by_digest(
            CONFIG, sha256(OLD_KEY.encode("utf-8"))
        )
        self.assertEqual(removed, OLD_KEY)
        self.assertEqual(count, 3)
        self.assertEqual(
            revoker.api_keys(updated),
            [OTHER_KEY, NEW_KEY],
        )
        self.assertNotIn(OLD_KEY.encode("utf-8"), updated)

    def test_revocation_accepts_plain_existing_key_and_preserves_scalar_styles(self) -> None:
        document = CONFIG.replace(json.dumps(OLD_KEY).encode(), OLD_KEY.encode())
        updated, removed, count = revoker.remove_api_key_by_digest(
            document, sha256(OLD_KEY.encode("utf-8"))
        )
        self.assertEqual((removed, count), (OLD_KEY, 3))
        self.assertEqual(revoker.api_keys(updated), [OTHER_KEY, NEW_KEY])

    def test_duplicate_digest_is_rejected(self) -> None:
        duplicate = CONFIG.replace(
            ("  - %s\n" % json.dumps(NEW_KEY)).encode("utf-8"),
            ("  - %s\n  - %s\n" % (json.dumps(OLD_KEY), json.dumps(NEW_KEY))).encode("utf-8"),
        )
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            revoker.remove_api_key_by_digest(duplicate, sha256(OLD_KEY.encode("utf-8")))

    def test_success_revokes_old_only_and_emits_no_key(self) -> None:
        output = StringIO()
        with ExitStack() as stack:
            for patcher in self._patches():
                stack.enter_context(patcher)
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(revoker.main([
                "--apply",
                "--confirm", revoker.CONFIRMATION,
                "--release-version", "0.1.30",
                "--transaction-id", "20260723T120000Z-1234abcd",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(revoker.api_keys(self.config.read_bytes()), [OTHER_KEY, NEW_KEY])
        self.assertEqual(self.credential.read_text(encoding="utf-8"), NEW_KEY + "\n")
        self.assertEqual(document["oldCredentialHttpStatus"], 401)
        self.assertEqual(document["newCredentialHttpStatus"], 200)
        self.assertTrue(document["otherGatewayKeysUnchanged"])
        for secret in (OLD_KEY, NEW_KEY, OTHER_KEY):
            self.assertNotIn(secret, output.getvalue())

    def test_config_drift_rejects_before_restart(self) -> None:
        changed = manifest()
        changed["configSha256After"] = "f" * 64
        restart = mock.Mock()
        with ExitStack() as stack:
            for patcher in self._patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(revoker, "_manifest", return_value=changed))
            stack.enter_context(mock.patch.object(revoker, "systemctl", restart))
            with self.assertRaisesRegex(RuntimeError, "changed after rotation"):
                revoker.main([
                    "--apply", "--confirm", revoker.CONFIRMATION,
                    "--release-version", "0.1.30",
                    "--transaction-id", "20260723T120000Z-1234abcd",
                ])
        restart.assert_not_called()

    def test_failed_old_key_rejection_restores_full_config(self) -> None:
        before = self.config.read_bytes()

        def restore_snapshot(path: pathlib.Path, value: Snapshot) -> None:
            self._atomic_write(path, value.data, value.mode, value.uid, value.gid)

        probes = mock.Mock(side_effect=[200, 200, 200])
        with ExitStack() as stack:
            for patcher in self._patches(old_status=RuntimeError("still accepted")):
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(revoker, "probe", probes))
            stack.enter_context(mock.patch.object(revoker, "restore", side_effect=restore_snapshot))
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                revoker.main([
                    "--apply", "--confirm", revoker.CONFIRMATION,
                    "--release-version", "0.1.30",
                    "--transaction-id", "20260723T120000Z-1234abcd",
                ])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.transaction / "revocation.json").exists())
        self.assertFalse((self.transaction / "config.before-revocation.yaml").exists())

    def test_manifest_rejects_unknown_fields_and_invalid_digest(self) -> None:
        path = self.transaction / "manifest.json"
        document = manifest()
        document["unknown"] = True
        raw = json.dumps(document).encode("utf-8")
        with mock.patch.object(revoker, "_safe_bytes", return_value=raw):
            with self.assertRaisesRegex(RuntimeError, "shape"):
                revoker._manifest(path, document["transactionId"], "0.1.30")
        document.pop("unknown")
        document["oldCredentialSha256"] = "bad"
        with mock.patch.object(revoker, "_safe_bytes", return_value=json.dumps(document).encode()):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                revoker._manifest(path, document["transactionId"], "0.1.30")


if __name__ == "__main__":
    unittest.main()
