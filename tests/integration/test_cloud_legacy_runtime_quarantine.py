from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import quarantine_cloud_legacy_runtime as quarantine  # noqa: E402


class CloudLegacyRuntimeQuarantineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.target = self.root / "opt/codex-gateway/codexx_app"
        self.target.mkdir(parents=True, mode=0o755)
        (self.target / "module.py").write_text("value = 1\n", encoding="utf-8")
        (self.target / "module.py").chmod(0o644)
        nested = self.target / "nested"
        nested.mkdir(mode=0o755)
        (nested / "helper.py").write_text("pass\n", encoding="utf-8")
        (nested / "helper.py").chmod(0o644)
        self.quarantine_root = self.root / "var/lib/cloudx/legacy-runtime-quarantine"
        self.quarantine_root.parent.mkdir(parents=True, mode=0o700)
        self.lock = self.root / "var/lib/cloudx/legacy-runtime-quarantine.lock"
        self.snapshot = quarantine._tree_snapshot(self.target)
        self.continuity = {
            "gateway": {"mainPid": 100, "restarts": 0},
            "selectors": {"current": "0.1.21", "previous": "0.1.20"},
            "dependencyUnits": {},
            "continuityUnits": {},
            "publicCanaries": {},
            "rollback": {"archiveSha256": "1" * 64, "targetEntries": 2},
        }
        self.contract = {
            "releaseVersion": "0.1.21",
            "targetDevice": self.snapshot.device,
            "targetInode": self.snapshot.inode,
            "targetFileCount": self.snapshot.file_count,
            "targetBytes": self.snapshot.total_bytes,
            "targetTreeSha256": self.snapshot.tree_sha256,
            "processReferences": [],
            "dependencySources": {"import_api.py": "2" * 64},
            "referenceUnits": ["codex-import.service"],
            "cronReferences": 0,
            "continuity": self.continuity,
        }
        self.digest = quarantine._digest(self.contract)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _decision(self) -> dict[str, object]:
        return {
            "schema": "cloudx.cloud-legacy-runtime-quarantine-decision.v1",
            "status": "quarantine-ready",
            "decisionDigest": self.digest,
            "releaseVersion": "0.1.21",
            "targetFileCount": self.snapshot.file_count,
            "targetBytes": self.snapshot.total_bytes,
            "targetTreeSha256": self.snapshot.tree_sha256,
            "liveProcessReferences": 0,
            "dependencySourceCount": 1,
            "referenceUnitCount": 1,
            "scheduledReferences": 0,
            "rollbackSnapshotVerified": True,
            "rollbackArchiveContainsTarget": True,
            "gatewayPid": 100,
            "gatewayRestarts": 0,
            "currentVersion": "0.1.21",
            "previousVersion": "0.1.20",
            "serviceRestartRequired": False,
            "contract": self.contract,
        }

    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(quarantine, "decision") as decision, redirect_stdout(output):
            self.assertEqual(quarantine.main(["--release-version", "0.1.21"]), 0)
        decision.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/cloud-legacy-runtime-quarantine-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_check_returns_bound_public_decision(self) -> None:
        output = StringIO()
        with mock.patch.object(quarantine, "decision", return_value=self._decision()), redirect_stdout(output):
            self.assertEqual(
                quarantine.main(["--check", "--release-version", "0.1.21"]),
                0,
            )
        document = json.loads(output.getvalue())
        self.assertEqual(document["decisionDigest"], self.digest)
        self.assertNotIn("contract", document)

    def test_apply_requires_confirmation_before_inspection(self) -> None:
        with mock.patch.object(quarantine, "decision") as decision:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                quarantine.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--decision-digest",
                    self.digest,
                    "--release-version",
                    "0.1.21",
                ])
        decision.assert_not_called()

    def test_tree_inventory_rejects_symlink_and_writable_entry(self) -> None:
        alias = self.target / "alias.py"
        alias.symlink_to(self.target / "module.py")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            quarantine._tree_snapshot(self.target)
        alias.unlink()
        (self.target / "module.py").chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, "writable"):
            quarantine._tree_snapshot(self.target)

    def test_timer_state_defaults_absent_process_properties_to_zero(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=(
                b"LoadState=loaded\nActiveState=active\nSubState=waiting\n"
                b"UnitFileState=enabled\n"
            ),
            stderr=b"",
        )
        with mock.patch.object(quarantine, "_run", return_value=completed):
            state = quarantine._unit_state("fixture.timer")
        self.assertEqual(state["mainPid"], 0)
        self.assertEqual(state["restarts"], 0)

    def test_backup_is_private_and_recovery_script_compiles(self) -> None:
        with mock.patch.object(quarantine, "QUARANTINE_ROOT", self.quarantine_root), mock.patch.object(
            quarantine, "TARGET", self.target
        ):
            backup = quarantine._prepare_backup(self.contract, self.snapshot)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((backup / "recover.py").stat().st_mode), 0o700)
        recovery = (backup / "recover.py").read_text(encoding="utf-8")
        compile(recovery, str(backup / "recover.py"), "exec")
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["treeSha256"], self.snapshot.tree_sha256)
        self.assertEqual(manifest["recoveryConfirmation"], quarantine.RECOVERY_CONFIRMATION)

    def test_success_moves_only_runtime_and_preserves_continuity(self) -> None:
        output = StringIO()
        with mock.patch.object(quarantine, "TARGET", self.target), mock.patch.object(
            quarantine, "QUARANTINE_ROOT", self.quarantine_root
        ), mock.patch.object(quarantine, "LOCK_PATH", self.lock), mock.patch.object(
            quarantine, "decision", return_value=self._decision()
        ), mock.patch.object(
            quarantine, "_contract", return_value=(self.contract, self.snapshot)
        ), mock.patch.object(
            quarantine, "_lock", return_value=nullcontext()
        ), mock.patch.object(
            quarantine, "_process_references", return_value=[]
        ), mock.patch.object(
            quarantine, "_continuity", return_value=self.continuity
        ), redirect_stdout(output):
            self.assertEqual(quarantine.main([
                "--apply",
                "--confirm",
                quarantine.CONFIRMATION,
                "--decision-digest",
                self.digest,
                "--release-version",
                "0.1.21",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "quarantined")
        self.assertFalse(document["serviceRestarted"])
        self.assertFalse(document["credentialMutation"])
        self.assertFalse(self.target.exists())
        held = self.quarantine_root / document["backupId"] / "live/codexx_app"
        self.assertTrue(held.is_dir())

    def test_post_move_failure_restores_runtime(self) -> None:
        with mock.patch.object(quarantine, "TARGET", self.target), mock.patch.object(
            quarantine, "QUARANTINE_ROOT", self.quarantine_root
        ), mock.patch.object(quarantine, "LOCK_PATH", self.lock), mock.patch.object(
            quarantine, "decision", return_value=self._decision()
        ), mock.patch.object(
            quarantine, "_contract", return_value=(self.contract, self.snapshot)
        ), mock.patch.object(
            quarantine, "_lock", return_value=nullcontext()
        ), mock.patch.object(
            quarantine, "_process_references", return_value=[]
        ), mock.patch.object(
            quarantine,
            "_continuity",
            side_effect=[RuntimeError("post-move"), self.continuity],
        ):
            with self.assertRaisesRegex(RuntimeError, "was restored"):
                quarantine.main([
                    "--apply",
                    "--confirm",
                    quarantine.CONFIRMATION,
                    "--decision-digest",
                    self.digest,
                    "--release-version",
                    "0.1.21",
                ])
        self.assertTrue(self.target.is_dir())
        self.assertEqual(list(self.quarantine_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
