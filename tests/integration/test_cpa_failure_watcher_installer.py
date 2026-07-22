from __future__ import annotations

import importlib.util
import pathlib
import plistlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/install_cpa_failure_watcher.py"
SPEC = importlib.util.spec_from_file_location("install_cpa_failure_watcher", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CpaFailureWatcherInstallerTests(unittest.TestCase):
    def test_plan_requires_policy_and_never_restarts_cpa_or_codex(self) -> None:
        for target in ("local", "cloud"):
            value = MODULE.target_value(target, MODULE.DEFAULT_CONTRACT)
            document = MODULE.plan_document(target, value)
            with self.subTest(target=target):
                self.assertEqual(
                    document["requiredActiveCloudxVersion"],
                    "0.1.21" if target == "local" else "0.1.25",
                )
                self.assertEqual(document["requiredActivePolicyVersion"], value["version"])
                self.assertEqual(document["trigger"], "permanent-receipt-or-pool-unavailable")
                self.assertFalse(document["networkProbeOnPermanentReceipt"])
                self.assertTrue(document["networkProbeOnPoolUnavailable"])
                self.assertEqual(document["incidentProbeConcurrency"], "adaptive-up-to-32")
                self.assertFalse(document["periodicAccountProbe"])
                self.assertEqual(document["updatesTriggerAwareHealthFallback"], target == "cloud")
                self.assertFalse(document["restartsExternalCPA"])
                self.assertFalse(document["stopsCodexProcesses"])
                self.assertFalse(document["automaticAction"])
                self.assertTrue(document["confirmation"].startswith("ACTIVATE %s" % target.upper()))

    def test_local_launcher_adds_path_trigger_and_two_minute_fallback(self) -> None:
        value = MODULE.target_value("local", MODULE.DEFAULT_CONTRACT)
        original = {
            "Label": value["maintenanceLabel"],
            "ProgramArguments": [
                str(pathlib.Path.home().resolve() / ".local/bin/codexx"),
                "api",
                "refresh",
                "--apply",
            ],
            "RunAtLoad": True,
            "StartInterval": 900,
            "StandardOutPath": "/tmp/refresh.out",
            "StandardErrorPath": "/tmp/refresh.err",
        }
        updated = plistlib.loads(MODULE.local_launcher(plistlib.dumps(original), value))
        self.assertEqual(updated["WatchPaths"], [
            str(value["failureDirectory"]),
            str(value["sweepDirectory"] / "trigger.json"),
        ])
        self.assertEqual(updated["StartInterval"], 120)
        self.assertEqual(updated["ThrottleInterval"], 5)
        self.assertEqual(updated["ProgramArguments"], original["ProgramArguments"])
        self.assertEqual(updated["StandardOutPath"], original["StandardOutPath"])

    def test_signed_cloud_units_select_network_free_receipt_consumer(self) -> None:
        value = MODULE.target_value("cloud", MODULE.DEFAULT_CONTRACT)
        completed = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "ExecStart=cloudx cpa-health --sweep-if-triggered\n"
                    "CLOUDX_CPA_SWEEP_CONCURRENCY=32\n%s\n" % value["sweepDirectory"]
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="OnUnitActiveSec=5min\nUnit=cloudx-cpa-health.service\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="ExecStart=cloudx cpa-health --runtime-failures-only\nPrivateNetwork=true\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "PathChanged=%s\nUnit=cloudx-cpa-failure.service\n"
                    % value["failureDirectory"]
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="ExecStart=cloudx cpa-health --sweep-if-triggered\nCLOUDX_CPA_SWEEP_CONCURRENCY=32\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "PathChanged=%s/trigger.json\nUnit=cloudx-cpa-sweep.service\n"
                    % value["sweepDirectory"]
                ),
                stderr="",
            ),
        ]
        with mock.patch.object(MODULE, "run_command", side_effect=completed) as command:
            units = MODULE.signed_cloud_units(
                pathlib.Path("/signed/cloudx.pyz"),
                value,
            )
        self.assertIn(b"--sweep-if-triggered", units["health-service"])
        self.assertIn(b"OnUnitActiveSec=5min", units["health-timer"])
        self.assertIn(b"--runtime-failures-only", units["failure-service"])
        self.assertIn(b"PathChanged=", units["failure-path"])
        self.assertIn(b"--sweep-if-triggered", units["sweep-service"])
        self.assertIn(b"trigger.json", units["sweep-path"])
        self.assertEqual(command.call_count, 6)

    def test_cloud_activation_never_restarts_the_external_cpa(self) -> None:
        value = MODULE.target_value("cloud", MODULE.DEFAULT_CONTRACT)
        absent = MODULE.Snapshot(False, b"", 0, 0, 0)
        present = MODULE.Snapshot(True, b"old", 0o644, 0, 0)
        cliproxy = mock.Mock(pw_uid=100, pw_gid=101)
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.sys, "platform", "linux"), mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(MODULE, "require_active_cloudx", return_value=pathlib.Path("/signed/cloudx.pyz")), mock.patch.object(
            MODULE, "require_receipt_producer"
        ), mock.patch.object(
            MODULE, "signed_cloud_units", return_value={
                "health-service": b"health-service", "health-timer": b"health-timer",
                "failure-service": b"failure-service", "failure-path": b"failure-path",
                "sweep-service": b"sweep-service", "sweep-path": b"sweep-path",
            }
        ), mock.patch.object(
            MODULE, "safe_snapshot", side_effect=[present, present, absent, absent, absent, absent]
        ), mock.patch.object(
            MODULE, "unit_state", side_effect=[
                (False, False), (False, False), (True, True),
                (True, True), (True, True), (True, True),
            ]
        ), mock.patch.object(
            MODULE.pwd, "getpwnam", return_value=cliproxy
        ), mock.patch.object(
            MODULE, "ensure_directory"
        ), mock.patch.object(
            MODULE, "backup", return_value=pathlib.Path("/backup/1")
        ), mock.patch.object(
            MODULE, "atomic_write"
        ), mock.patch.object(
            MODULE, "run_command", return_value=completed
        ) as command:
            document = MODULE.activate_cloud(value)

        self.assertEqual(document["status"], "active")
        commands = [call.args[0] for call in command.call_args_list]
        self.assertFalse(any("restart" in argv for argv in commands))
        self.assertFalse(any(value["service"] in argv for argv in commands))

    def test_cloud_activation_failure_restores_files_and_prior_path_state(self) -> None:
        value = MODULE.target_value("cloud", MODULE.DEFAULT_CONTRACT)
        service_before = MODULE.Snapshot(True, b"old-service", 0o644, 0, 0)
        path_before = MODULE.Snapshot(True, b"old-path", 0o644, 0, 0)
        sweep_service_before = MODULE.Snapshot(True, b"old-sweep-service", 0o644, 0, 0)
        sweep_path_before = MODULE.Snapshot(True, b"old-sweep-path", 0o644, 0, 0)
        health_service_before = MODULE.Snapshot(True, b"old-health-service", 0o644, 0, 0)
        health_timer_before = MODULE.Snapshot(True, b"old-health-timer", 0o644, 0, 0)
        cliproxy = mock.Mock(pw_uid=100, pw_gid=101)
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        def command(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            del check
            if argv[:4] == ["systemctl", "enable", "--now", MODULE.CLOUD_FAILURE_PATH_UNIT]:
                raise MODULE.FailureWatcherRejected("injected enable failure")
            return completed

        with mock.patch.object(MODULE.sys, "platform", "linux"), mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(MODULE, "require_active_cloudx", return_value=pathlib.Path("/signed/cloudx.pyz")), mock.patch.object(
            MODULE, "require_receipt_producer"
        ), mock.patch.object(
            MODULE,
            "signed_cloud_units",
            return_value={
                "health-service": b"new-health-service", "health-timer": b"new-health-timer",
                "failure-service": b"new-service", "failure-path": b"new-path",
                "sweep-service": b"new-sweep-service", "sweep-path": b"new-sweep-path",
            },
        ), mock.patch.object(
            MODULE,
            "safe_snapshot",
            side_effect=[
                health_service_before, health_timer_before, service_before,
                path_before, sweep_service_before, sweep_path_before,
            ],
        ), mock.patch.object(
            MODULE, "unit_state", side_effect=[(True, True), (True, True), (True, True), (True, True)]
        ), mock.patch.object(
            MODULE.pwd, "getpwnam", return_value=cliproxy
        ), mock.patch.object(
            MODULE, "ensure_directory"
        ), mock.patch.object(
            MODULE, "backup", return_value=pathlib.Path("/backup/1")
        ), mock.patch.object(
            MODULE, "atomic_write"
        ), mock.patch.object(
            MODULE, "restore_snapshot"
        ) as restore, mock.patch.object(
            MODULE, "restore_cloud_state"
        ) as restore_state, mock.patch.object(
            MODULE, "run_command", side_effect=command
        ):
            with self.assertRaisesRegex(MODULE.FailureWatcherRejected, "was rolled back"):
                MODULE.activate_cloud(value)

        self.assertEqual(restore.call_count, 6)
        restore.assert_any_call(value["healthServiceUnit"], health_service_before)
        restore.assert_any_call(value["healthTimerUnit"], health_timer_before)
        restore.assert_any_call(value["failureServiceUnit"], service_before)
        restore.assert_any_call(value["failurePathUnit"], path_before)
        restore.assert_any_call(value["sweepServiceUnit"], sweep_service_before)
        restore.assert_any_call(value["sweepPathUnit"], sweep_path_before)
        self.assertEqual(restore_state.call_count, 2)


if __name__ == "__main__":
    unittest.main()
