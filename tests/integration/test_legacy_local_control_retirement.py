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

import retire_legacy_local_control as retirement  # noqa: E402


class LegacyLocalControlRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name) / "home"
        self.state = self.home / ".local/state/cloudx"
        self.state.mkdir(parents=True, mode=0o700)
        self.live_plist = self.home / "Library/LaunchAgents/com.codexx.control.plist"
        self.live_plist.parent.mkdir(parents=True)
        self.plist_raw = b"plist"
        self.live_plist.write_bytes(self.plist_raw)
        self.plist = {
            "ProgramArguments": ["/retained/codexx", "control", "serve", "--host", "127.0.0.1", "--port", "8765"]
        }
        self.continuity = {
            "selectors": {"current": "0.1.21", "previous": "0.1.20"},
            "shell": {},
            "cpa": {"pid": 300, "identity": "300 cpa"},
        }
        self.contract = {
            "releaseVersion": "0.1.21",
            "plistSha256": retirement.hashlib.sha256(self.plist_raw).hexdigest(),
            "servicePid": 102,
            "retainedBundleId": "20260715T122545Z",
            "migrationBackupId": "20260719T150309Z",
            "minimumIdleSeconds": retirement.migration.MIN_IDLE_SECONDS,
            "selectors": self.continuity["selectors"],
            "localCpaPid": 300,
        }
        self.digest = retirement._digest(self.contract)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _decision(self) -> dict[str, object]:
        return {
            "schema": "cloudx.legacy-local-control-retirement-decision.v1",
            "status": "retirement-ready",
            "decisionDigest": self.digest,
            "releaseVersion": "0.1.21",
            "controlPid": 102,
            "port": 8765,
            "activeConnections": 0,
            "minimumIdleSeconds": retirement.migration.MIN_IDLE_SECONDS,
            "retainedBundleId": "20260715T122545Z",
            "migrationBackupId": "20260719T150309Z",
            "localCpaPid": 300,
            "localCpaChanged": False,
            "serviceStopRequired": True,
            "contract": self.contract,
        }

    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(retirement, "decision") as decision, redirect_stdout(output):
            self.assertEqual(retirement.main(["--release-version", "0.1.21"]), 0)
        decision.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/legacy-local-control-retirement-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertFalse(any(document["authorization"].values()))

    def test_check_returns_public_digest_bound_decision(self) -> None:
        output = StringIO()
        with mock.patch.object(retirement, "decision", return_value=self._decision()), redirect_stdout(output):
            self.assertEqual(retirement.main(["--check", "--release-version", "0.1.21"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["decisionDigest"], self.digest)
        self.assertNotIn("contract", document)

    def test_apply_requires_confirmation_before_inspection(self) -> None:
        with mock.patch.object(retirement, "decision") as decision:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                retirement.main([
                    "--apply", "--confirm", "wrong", "--decision-digest", self.digest,
                    "--release-version", "0.1.21",
                ])
        decision.assert_not_called()

    def test_backup_is_private_and_recovery_script_compiles(self) -> None:
        backup = retirement._prepare_backup(self.home, self.plist_raw, self.contract)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((backup / "recover.py").stat().st_mode), 0o700)
        recovery = (backup / "recover.py").read_text(encoding="utf-8")
        compile(recovery, str(backup / "recover.py"), "exec")
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["recoveryConfirmation"], retirement.RECOVERY_CONFIRMATION)

    def test_success_unloads_and_quarantines_only_launchagent(self) -> None:
        output = StringIO()
        backup = self.state / "legacy-control-retirement-backups/20260719T170000Z"
        (backup / "live").mkdir(parents=True)
        with mock.patch.object(retirement, "decision", return_value=self._decision()), mock.patch.object(
            retirement, "user_home", return_value=self.home
        ), mock.patch.object(retirement, "_lock", return_value=nullcontext()), mock.patch.object(
            retirement, "_contract", return_value=self.contract
        ), mock.patch.object(
            retirement.migration, "_plist", return_value=(self.plist_raw, self.plist)
        ), mock.patch.object(
            retirement.migration, "_plist_path", return_value=self.live_plist
        ), mock.patch.object(
            retirement.migration, "_process_command", return_value=["/python", "/retained/codexx.py", "control", "serve", "--host", "127.0.0.1", "--port", "8765"]
        ), mock.patch.object(
            retirement, "_retained_bundle", return_value=(pathlib.Path("/bundle"), pathlib.Path("/retained/codexx.py"))
        ), mock.patch.object(
            retirement, "_continuity", return_value=self.continuity
        ), mock.patch.object(
            retirement, "_prepare_backup", return_value=backup
        ), mock.patch.object(
            retirement.migration, "_bootout"
        ) as bootout, mock.patch.object(
            retirement, "_service_absent", return_value=True
        ), mock.patch.object(
            retirement.migration.legacy_removal, "_port_open", return_value=False
        ), redirect_stdout(output):
            self.assertEqual(retirement.main([
                "--apply", "--confirm", retirement.CONFIRMATION,
                "--decision-digest", self.digest, "--release-version", "0.1.21",
            ]), 0)
        bootout.assert_called_once()
        document = json.loads(output.getvalue())
        self.assertTrue(document["controlServiceStopped"])
        self.assertFalse(document["localCpaChanged"])
        self.assertFalse(self.live_plist.exists())
        self.assertTrue((backup / "live/com.codexx.control.plist").is_file())

    def test_post_stop_failure_restores_and_bootstraps_control(self) -> None:
        backup = self.state / "legacy-control-retirement-backups/20260719T170000Z"
        (backup / "live").mkdir(parents=True)
        with mock.patch.object(retirement, "decision", return_value=self._decision()), mock.patch.object(
            retirement, "user_home", return_value=self.home
        ), mock.patch.object(retirement, "_lock", return_value=nullcontext()), mock.patch.object(
            retirement, "_contract", return_value=self.contract
        ), mock.patch.object(
            retirement.migration, "_plist", return_value=(self.plist_raw, self.plist)
        ), mock.patch.object(
            retirement.migration, "_plist_path", return_value=self.live_plist
        ), mock.patch.object(
            retirement.migration, "_process_command", return_value=["/python"]
        ), mock.patch.object(
            retirement, "_retained_bundle", return_value=(pathlib.Path("/bundle"), pathlib.Path("/retained/codexx.py"))
        ), mock.patch.object(
            retirement, "_continuity", return_value=self.continuity
        ), mock.patch.object(
            retirement, "_prepare_backup", return_value=backup
        ), mock.patch.object(
            retirement.migration, "_bootout"
        ), mock.patch.object(
            retirement, "_service_absent", return_value=False
        ), mock.patch.object(
            retirement.migration.legacy_removal, "_port_open", return_value=False
        ), mock.patch.object(
            retirement.migration, "_bootstrap", return_value=103
        ) as bootstrap:
            with self.assertRaisesRegex(RuntimeError, "was restored"):
                retirement.main([
                    "--apply", "--confirm", retirement.CONFIRMATION,
                    "--decision-digest", self.digest, "--release-version", "0.1.21",
                ])
        bootstrap.assert_called_once()
        self.assertTrue(self.live_plist.is_file())


if __name__ == "__main__":
    unittest.main()
