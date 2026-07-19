from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rehearse_legacy_health_bridge_cutover as cutover  # noqa: E402


def unit_state(load: str, active: str, unit_file: str) -> dict[str, str]:
    return {"LoadState": load, "ActiveState": active, "UnitFileState": unit_file}


class LegacyHealthBridgeCutoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.release_root = self.root / "opt/cloudx/releases"
        self.artifact = self.release_root / "0.1.15/cloudx-cloud.pyz"
        self.output = self.root / "var/lib/cloudx/health/v1.json"
        self.backup = self.root / "var/lib/cloudx/legacy-health-bridge-cutover-backups/123456789"
        self.lock = self.root / "run/lock/cutover.lock"
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b"fixture")
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"fixture")
        self.lock.parent.mkdir(parents=True)
        self.timer_active = {
            cutover.units.LEGACY_TIMER: True,
            cutover.units.TARGET_TIMER: False,
        }
        self.actions: list[tuple[str, str]] = []
        self.selectors = {"current": "0.1.13", "previous": "0.1.12"}
        self.gateway = {"activeState": "active", "mainPid": 977036, "restarts": 0}
        self.importer = {"activeState": "active", "mainPid": 133756, "restarts": 0}
        self.old_producer = {
            "name": "cloudx",
            "version": "0.7.0",
            "revision": "0" * 40,
        }
        self.initial_snapshot = cutover.units.Snapshot(True, b"fixture", 0o644, 0, 0)
        self.constants = mock.patch.multiple(
            cutover,
            DEFAULT_OUTPUT=self.output,
            DEFAULT_BACKUP_ROOT=self.backup.parent,
            DEFAULT_LOCK=self.lock,
        )
        self.units_constants = mock.patch.multiple(
            cutover.units,
            DEFAULT_RELEASE_ROOT=self.release_root,
        )
        self.constants.start()
        self.units_constants.start()

    def tearDown(self) -> None:
        self.units_constants.stop()
        self.constants.stop()
        self.temp.cleanup()

    def _unit_state(self, unit: str) -> dict[str, str]:
        if unit in self.timer_active:
            active = self.timer_active[unit]
            return unit_state("loaded", "active" if active else "inactive", "enabled" if active else "disabled")
        if unit in {cutover.units.LEGACY_SERVICE, cutover.units.TARGET_SERVICE, cutover.units.CANARY_SERVICE}:
            return unit_state("loaded", "inactive", "static")
        raise AssertionError(unit)

    def _systemctl(self, action: str, unit: str) -> None:
        self.actions.append((action, unit))
        if action == "enable":
            self.timer_active[unit] = True
            return
        if action == "disable":
            other = (
                cutover.units.TARGET_TIMER
                if unit == cutover.units.LEGACY_TIMER
                else cutover.units.LEGACY_TIMER
            )
            if not self.timer_active[other]:
                raise AssertionError("publisher gap")
            self.timer_active[unit] = False
            return
        if action == "start":
            timer = (
                cutover.units.LEGACY_TIMER
                if unit == cutover.units.LEGACY_SERVICE
                else cutover.units.TARGET_TIMER
            )
            if not self.timer_active[timer]:
                raise AssertionError("writer timer inactive")
            return
        raise AssertionError((action, unit))

    def _initial_output(self) -> dict[str, object]:
        return {
            "document": {"producer": dict(self.old_producer)},
            "sha256": "0" * 64,
            "snapshot": self.initial_snapshot,
        }

    def _process_state(self, unit: str) -> dict[str, object]:
        return dict(self.gateway if unit == cutover.GATEWAY_UNIT else self.importer)

    def _patches(self):
        return [
            mock.patch.object(cutover.os, "geteuid", return_value=0),
            mock.patch.object(cutover, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(cutover.canary, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(cutover.units, "_validate_runtime_directories"),
            mock.patch.object(cutover.units, "_validate_artifact"),
            mock.patch.object(cutover.units, "verify_artifact"),
            mock.patch.object(cutover, "_require_installed_files"),
            mock.patch.object(cutover.units, "_unit_state", side_effect=self._unit_state),
            mock.patch.object(cutover, "_selector_state", side_effect=lambda: dict(self.selectors)),
            mock.patch.object(cutover, "_process_state", side_effect=self._process_state),
            mock.patch.object(cutover, "_read_output", side_effect=self._initial_output),
            mock.patch.object(cutover.canary, "_require_installed_files"),
            mock.patch.object(cutover.canary, "_require_runtime_boundaries"),
            mock.patch.object(
                cutover.canary,
                "run_once",
                return_value={"document": {}, "sha256": "1" * 64},
            ),
            mock.patch.object(cutover, "_prepare_backup", return_value=self.backup),
            mock.patch.object(cutover, "_systemctl", side_effect=self._systemctl),
            mock.patch.object(
                cutover,
                "_validate_candidate_output",
                return_value={"document": {}, "sha256": "2" * 64},
            ),
            mock.patch.object(
                cutover,
                "_validate_legacy_output",
                return_value={"document": {}, "sha256": "4" * 64},
            ),
        ]

    def test_default_plan_is_non_authorizing_and_reads_no_runtime_state(self) -> None:
        self.artifact.unlink()
        output = StringIO()
        with mock.patch.object(cutover, "_selector_state") as selectors, redirect_stdout(output):
            self.assertEqual(cutover.main(["--release-version", "0.1.15"]), 0)
        selectors.assert_not_called()
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], cutover.CONFIRMATION)
        self.assertFalse(document["communicationGapAllowed"])
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_custom_artifact_is_rejected_even_for_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            cutover.main([
                "--release-version",
                "0.1.15",
                "--artifact",
                str(self.root / "other.pyz"),
            ])

    def test_apply_requires_exact_confirmation_before_root_or_artifact_checks(self) -> None:
        with mock.patch.object(cutover.units, "verify_artifact") as verify:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                cutover.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--release-version",
                    "0.1.15",
                ])
        verify.assert_not_called()

    def test_continuity_accepts_disabled_retired_importer_with_closed_port(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout="ActiveState=inactive\nMainPID=0\nNRestarts=0\nUnitFileState=disabled\n",
        )
        with mock.patch.object(cutover.subprocess, "run", return_value=completed), mock.patch.object(
            cutover, "_importer_connections_present", return_value=False
        ):
            state = cutover._process_state(cutover.IMPORT_UNIT)
        self.assertEqual(state, {
            "activeState": "inactive",
            "mainPid": 0,
            "restarts": 0,
            "unitFileState": "disabled",
            "listenerClosed": True,
        })

    def test_retired_importer_with_open_socket_is_rejected(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout="ActiveState=inactive\nMainPID=0\nNRestarts=0\nUnitFileState=disabled\n",
        )
        with mock.patch.object(cutover.subprocess, "run", return_value=completed), mock.patch.object(
            cutover, "_importer_connections_present", return_value=True
        ):
            with self.assertRaisesRegex(RuntimeError, "neither active nor safely retired"):
                cutover._process_state(cutover.IMPORT_UNIT)

    def test_gateway_continuity_still_requires_active_process(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout="ActiveState=inactive\nMainPID=0\nNRestarts=0\nUnitFileState=disabled\n",
        )
        with mock.patch.object(cutover.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "not active"):
                cutover._process_state(cutover.GATEWAY_UNIT)

    def test_success_uses_overlap_before_each_disable_and_finishes_on_primary(self) -> None:
        output = StringIO()
        with ExitStack() as stack:
            for patcher in self._patches():
                stack.enter_context(patcher)
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(cutover.main([
                "--apply",
                "--confirm",
                cutover.CONFIRMATION,
                "--release-version",
                "0.1.15",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "accepted")
        self.assertFalse(document["communicationGapObserved"])
        self.assertTrue(document["rollbackRehearsed"])
        self.assertTrue(document["restorationAccepted"])
        self.assertTrue(document["primaryTimerEnabled"])
        self.assertTrue(document["legacyTimerDisabled"])
        self.assertTrue(document["selectorsUnchanged"])
        self.assertFalse(document["releaseActivated"])
        self.assertEqual([phase["name"] for phase in document["phases"]], [
            "isolated_canary",
            "candidate_overlap",
            "candidate_cutover",
            "legacy_rollback",
            "candidate_restoration",
        ])
        self.assertTrue(self.timer_active[cutover.units.TARGET_TIMER])
        self.assertFalse(self.timer_active[cutover.units.LEGACY_TIMER])
        self.assertEqual(self.actions, [
            ("enable", cutover.units.TARGET_TIMER),
            ("start", cutover.units.TARGET_SERVICE),
            ("disable", cutover.units.LEGACY_TIMER),
            ("start", cutover.units.TARGET_SERVICE),
            ("enable", cutover.units.LEGACY_TIMER),
            ("start", cutover.units.LEGACY_SERVICE),
            ("disable", cutover.units.TARGET_TIMER),
            ("start", cutover.units.LEGACY_SERVICE),
            ("enable", cutover.units.TARGET_TIMER),
            ("start", cutover.units.TARGET_SERVICE),
            ("disable", cutover.units.LEGACY_TIMER),
            ("start", cutover.units.TARGET_SERVICE),
        ])

    def test_candidate_failure_restores_old_timer_without_disabling_both(self) -> None:
        patches = self._patches()
        patches[16] = mock.patch.object(
            cutover,
            "_validate_candidate_output",
            side_effect=RuntimeError("invalid"),
        )
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "old path was restored"):
                cutover.main([
                    "--apply",
                    "--confirm",
                    cutover.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertTrue(self.timer_active[cutover.units.LEGACY_TIMER])
        self.assertFalse(self.timer_active[cutover.units.TARGET_TIMER])
        self.assertEqual(self.actions[:4], [
            ("enable", cutover.units.TARGET_TIMER),
            ("start", cutover.units.TARGET_SERVICE),
            ("start", cutover.units.TARGET_SERVICE),
            ("start", cutover.units.TARGET_SERVICE),
        ])
        self.assertEqual(self.actions[-3:], [
            ("enable", cutover.units.LEGACY_TIMER),
            ("start", cutover.units.LEGACY_SERVICE),
            ("disable", cutover.units.TARGET_TIMER),
        ])

    def test_external_selector_change_fails_closed_and_restores_old_publisher(self) -> None:
        calls = 0

        def selectors() -> dict[str, str]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return dict(self.selectors)
            return {"current": "0.1.12", "previous": "0.1.13"}

        patches = self._patches()
        patches[8] = mock.patch.object(cutover, "_selector_state", side_effect=selectors)
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "recovery incomplete"):
                cutover.main([
                    "--apply",
                    "--confirm",
                    cutover.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertTrue(self.timer_active[cutover.units.LEGACY_TIMER])
        self.assertFalse(self.timer_active[cutover.units.TARGET_TIMER])

    def test_failed_old_writer_recovery_keeps_primary_timer_available(self) -> None:
        self.timer_active[cutover.units.LEGACY_TIMER] = False
        self.timer_active[cutover.units.TARGET_TIMER] = True

        def systemctl(action: str, unit: str) -> None:
            self.actions.append((action, unit))
            if action == "enable" and unit == cutover.units.LEGACY_TIMER:
                self.timer_active[unit] = True
                return
            if action == "start" and unit == cutover.units.LEGACY_SERVICE:
                raise RuntimeError("old writer failed")
            if action == "disable" and unit == cutover.units.TARGET_TIMER:
                self.timer_active[unit] = False

        with mock.patch.object(cutover, "_systemctl", side_effect=systemctl), mock.patch.object(
            cutover,
            "_require_timer",
        ), mock.patch.object(
            cutover,
            "_start_and_validate_legacy",
            side_effect=RuntimeError("old writer failed"),
        ), mock.patch.object(
            cutover.units,
            "atomic_write",
            side_effect=RuntimeError("restore failed"),
        ):
            errors = cutover._recover_old_path(self.initial_snapshot, self.old_producer)
        self.assertIn("old exporter recovery failed", errors)
        self.assertIn("legacy output restore failed", errors)
        self.assertTrue(self.timer_active[cutover.units.TARGET_TIMER])
        self.assertNotIn(("disable", cutover.units.TARGET_TIMER), self.actions)

    def test_candidate_and_old_output_identities_are_distinct(self) -> None:
        candidate = {
            "producer": {"name": "cloudx", "version": "0.1.13", "revision": "unknown"},
            "gateway": {"processState": "unknown"},
            "imports": {"processState": "unknown", "state": "unknown"},
        }
        with mock.patch.object(
            cutover,
            "_read_output",
            return_value={"document": candidate, "sha256": "2" * 64},
        ):
            self.assertEqual(cutover._validate_candidate_output()["sha256"], "2" * 64)

        old = {"producer": dict(self.old_producer)}
        with mock.patch.object(
            cutover,
            "_read_output",
            return_value={"document": old, "sha256": "4" * 64},
        ):
            self.assertEqual(
                cutover._validate_legacy_output(self.old_producer)["sha256"],
                "4" * 64,
            )

        candidate["imports"]["state"] = "degraded"
        with mock.patch.object(
            cutover,
            "_read_output",
            return_value={"document": candidate, "sha256": "2" * 64},
        ):
            with self.assertRaisesRegex(RuntimeError, "not produced"):
                cutover._validate_candidate_output()


if __name__ == "__main__":
    unittest.main()
