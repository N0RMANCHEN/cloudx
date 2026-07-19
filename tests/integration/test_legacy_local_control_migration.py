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

import migrate_legacy_local_control as migration  # noqa: E402


class LegacyLocalControlMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = pathlib.Path("/Users/tester")
        self.bundle = pathlib.Path(
            "/Users/tester/.local/state/cloudx/legacy-backups/20260715T122545Z"
        )
        self.target = self.bundle / "home/.local/bin/codexx"
        self.plist = {
            "Label": migration.LABEL,
            "ProgramArguments": [
                "/Users/tester/.local/bin/codexx",
                "control",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
            ],
            "KeepAlive": True,
            "RunAtLoad": True,
        }
        self.plist_raw = b"plist"
        self.continuity = {
            "selectors": {"current": "0.1.21", "previous": "0.1.20"},
            "shell": {"entrypoints": {}},
            "cpa": {"pid": 61859, "identity": "61859 local-cpa"},
        }
        self.contract = migration._decision_contract(
            plist_sha256=migration._sha256(self.plist_raw),
            service_pid=729,
            python_executable="/python",
            bundle=self.bundle,
            target_sha256="1" * 64,
            continuity=self.continuity,
        )
        self.digest = migration._digest(self.contract)

    def _decision(self) -> dict[str, object]:
        return {
            "schema": "cloudx.legacy-local-control-migration-decision.v1",
            "status": "migration-ready",
            "decisionDigest": self.digest,
            "controlPid": 729,
            "port": 8765,
            "activeConnections": 0,
            "minimumIdleSeconds": migration.MIN_IDLE_SECONDS,
            "recoveryBundleId": self.bundle.name,
            "targetLauncherSha256": "1" * 64,
            "localCpaPid": 61859,
            "localCpaChanged": False,
            "contract": self.contract,
        }

    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(migration, "decision") as decision, redirect_stdout(output):
            self.assertEqual(migration.main(["--release-version", "0.1.21"]), 0)
        decision.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/legacy-local-control-migration-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertEqual(document["confirmation"], migration.CONFIRMATION)
        self.assertFalse(any(document["authorization"].values()))

    def test_check_reports_bound_idle_decision(self) -> None:
        output = StringIO()
        with mock.patch.object(migration, "decision", return_value=self._decision()), redirect_stdout(output):
            self.assertEqual(migration.main(["--check", "--release-version", "0.1.21"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "migration-ready")
        self.assertEqual(document["decisionDigest"], self.digest)
        self.assertNotIn("contract", document)

    def test_apply_requires_confirmation_before_inspection(self) -> None:
        with mock.patch.object(migration, "decision") as decision:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                migration.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--decision-digest",
                    self.digest,
                    "--release-version",
                    "0.1.21",
                ])
        decision.assert_not_called()

    def test_target_plist_uses_retained_runtime_and_live_fallback_is_explicit(self) -> None:
        target, fallback = migration._target_plists(
            self.plist,
            target_launcher=self.target,
            live_launcher=self.home / ".local/bin/codexx.py",
            python_executable=pathlib.Path("/python"),
        )
        target_document = migration.plistlib.loads(target)
        fallback_document = migration.plistlib.loads(fallback)
        self.assertEqual(target_document["ProgramArguments"][0], str(self.target))
        self.assertEqual(
            fallback_document["ProgramArguments"][:2],
            ["/python", "/Users/tester/.local/bin/codexx.py"],
        )

    def test_backup_is_private_and_generated_recovery_script_compiles(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value) / "home"
            state = home / ".local/state/cloudx"
            state.mkdir(parents=True, mode=0o700)
            backup = migration._prepare_backup(
                home,
                original=b"original",
                target=b"target",
                fallback=b"fallback",
                contract=self.contract,
            )
            self.assertEqual(
                stat.S_IMODE(backup.parent.stat().st_mode),
                0o700,
            )
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
            recovery = (backup / "recover.py").read_text(encoding="utf-8")
            compile(recovery, str(backup / "recover.py"), "exec")
            manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["recoveryConfirmation"],
                migration.RECOVERY_CONFIRMATION,
            )

    def test_success_prepares_recovery_before_one_control_restart(self) -> None:
        output = StringIO()
        target_plist = b"target"
        fallback_plist = b"fallback"
        backup = self.home / ".local/state/cloudx/legacy-control-migration-backups/id"
        with mock.patch.object(migration, "decision", return_value=self._decision()), mock.patch.object(
            migration, "user_home", return_value=self.home
        ), mock.patch.object(
            migration, "_lock", return_value=nullcontext()
        ), mock.patch.object(
            migration, "_plist", return_value=(self.plist_raw, self.plist)
        ), mock.patch.object(
            migration, "_service", return_value={"pid": 729, "program": "legacy"}
        ), mock.patch.object(
            migration, "_process_command", return_value=["/python", "/Users/tester/.local/bin/codexx.py", "control", "serve", "--host", "127.0.0.1", "--port", "8765"]
        ), mock.patch.object(
            migration, "_recovery", return_value=(self.bundle, self.target, "1" * 64)
        ), mock.patch.object(
            migration, "_continuity", return_value=self.continuity
        ), mock.patch.object(
            migration, "_target_plists", return_value=(target_plist, fallback_plist)
        ), mock.patch.object(
            migration, "_prepare_backup", return_value=backup
        ) as prepare, mock.patch.object(
            migration, "_bootout"
        ) as bootout, mock.patch.object(
            migration, "_bootstrap", return_value=730
        ) as bootstrap, mock.patch.object(
            migration, "_idle_listener"
        ), redirect_stdout(output):
            self.assertEqual(migration.main([
                "--apply",
                "--confirm",
                migration.CONFIRMATION,
                "--decision-digest",
                self.digest,
                "--release-version",
                "0.1.21",
            ]), 0)
        prepare.assert_called_once()
        bootout.assert_called_once()
        bootstrap.assert_called_once_with(
            target_plist,
            self.bundle / "home/.local/bin/codexx.py",
        )
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "migrated")
        self.assertEqual(document["rollbackBackupId"], backup.name)
        self.assertTrue(document["recoveryScriptPrepared"])
        self.assertFalse(document["localCpaChanged"])

    def test_post_restart_failure_restores_live_control(self) -> None:
        with mock.patch.object(migration, "decision", return_value=self._decision()), mock.patch.object(
            migration, "user_home", return_value=self.home
        ), mock.patch.object(
            migration, "_lock", return_value=nullcontext()
        ), mock.patch.object(
            migration, "_plist", return_value=(self.plist_raw, self.plist)
        ), mock.patch.object(
            migration, "_service", return_value={"pid": 729, "program": "legacy"}
        ), mock.patch.object(
            migration, "_process_command", return_value=["/python", "/Users/tester/.local/bin/codexx.py", "control", "serve", "--host", "127.0.0.1", "--port", "8765"]
        ), mock.patch.object(
            migration, "_recovery", return_value=(self.bundle, self.target, "1" * 64)
        ), mock.patch.object(
            migration, "_continuity", return_value=self.continuity
        ), mock.patch.object(
            migration, "_target_plists", return_value=(b"target", b"fallback")
        ), mock.patch.object(
            migration, "_prepare_backup"
        ), mock.patch.object(
            migration, "_bootout"
        ), mock.patch.object(
            migration, "_bootstrap", side_effect=[RuntimeError("target"), 731]
        ) as bootstrap, mock.patch.object(
            migration.legacy_removal, "_port_open", return_value=False
        ):
            with self.assertRaisesRegex(RuntimeError, "live control was restored"):
                migration.main([
                    "--apply",
                    "--confirm",
                    migration.CONFIRMATION,
                    "--decision-digest",
                    self.digest,
                    "--release-version",
                    "0.1.21",
                ])
        self.assertEqual(bootstrap.call_count, 2)


if __name__ == "__main__":
    unittest.main()
