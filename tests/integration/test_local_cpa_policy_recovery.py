from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import pathlib
import plistlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/recover_local_cpa_policy.py"
SPEC = importlib.util.spec_from_file_location("recover_local_cpa_policy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LocalCpaPolicyRecoveryTests(unittest.TestCase):
    def make_job(self, root: pathlib.Path) -> tuple[pathlib.Path, dict[str, object]]:
        job = root / "test-job"
        job.mkdir(mode=0o700)
        launcher_dir = root / "LaunchAgents"
        launcher_dir.mkdir()
        baseline = root / "cli-proxy-api"
        baseline.write_bytes(b"baseline-binary")
        baseline.chmod(0o700)
        config = root / "config.yaml"
        config.write_text("host: 127.0.0.1\nport: 8317\n", encoding="utf-8")
        codex = root / "codex"
        codex.write_text("#!/bin/sh\n", encoding="utf-8")
        codex.chmod(0o700)
        codex_home = root / "codex-home"
        codex_home.mkdir()
        launcher = launcher_dir / "com.codexx.cliproxyapi.plist"
        launcher_raw = plistlib.dumps({
            "Label": "com.codexx.cliproxyapi",
            "ProgramArguments": [str(baseline), "--config", str(config)],
            "RunAtLoad": True,
        })
        launcher.write_bytes(launcher_raw)
        snapshot = job / "launcher.before"
        snapshot.write_bytes(launcher_raw)
        snapshot.chmod(0o600)
        recovery_raw = MODULE_PATH.read_bytes()
        launcher_digest = MODULE.sha256_bytes(launcher_raw)
        document: dict[str, object] = {
            "schema": MODULE.JOB_SCHEMA,
            "jobId": job.name,
            "baselineSha256": MODULE.sha256_file(baseline, MODULE.MAX_BINARY_BYTES),
            "launcherSnapshotSha256": launcher_digest,
            "recoveryToolSha256": MODULE.sha256_bytes(recovery_raw),
            "baselineBinary": str(baseline),
            "launcherPath": str(launcher),
            "launcherMode": stat.S_IMODE(launcher.stat().st_mode),
            "launcherUid": os.geteuid(),
            "launcherGid": os.getegid(),
            "serviceLabel": "com.codexx.cliproxyapi",
            "configPath": str(config),
            "codexBinary": str(codex),
            "communicationCodexHome": str(codex_home),
            "recoveryConfirmation": "RESTORE LOCAL CPA BASELINE test-job %s" % launcher_digest[:12],
            "quiescenceSamples": 3,
            "quiescenceIntervalSeconds": 0,
        }
        job_json = job / "job.json"
        job_json.write_text(json.dumps(document), encoding="utf-8")
        job_json.chmod(0o600)
        return job, document

    def test_plan_is_read_only_and_exposes_an_argument_vector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, unused = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "launch_state", return_value=(True, 123, True)):
                plan = MODULE.plan(document)
        self.assertEqual(plan["status"], "confirmation-required")
        self.assertEqual(plan["currentPid"], 123)
        self.assertIsInstance(plan["command"], list)
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(plan["stopsCodexProcesses"])

    def test_quiescence_fails_closed_before_any_service_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, unused = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "established_socket_rows", return_value=8):
                result = MODULE.check_quiescent(document)
        self.assertEqual(result["status"], "busy")
        self.assertEqual(result["establishedSocketRows"], 8)
        self.assertFalse(result["serviceChanged"])

    def test_quiescence_requires_repeated_zero_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, unused = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "established_socket_rows", side_effect=[0, 0, 0]) as audit, mock.patch.object(
                MODULE.time, "sleep"
            ):
                result = MODULE.check_quiescent(document)
        self.assertEqual(result["status"], "quiescent")
        self.assertEqual(audit.call_count, 3)

    def test_already_healthy_baseline_is_verified_without_rewrite_or_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, raw = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "launch_state", return_value=(True, 321, True)), mock.patch.object(
                MODULE, "probe_health", return_value=True
            ), mock.patch.object(MODULE, "probe_communication", return_value=True), mock.patch.object(
                MODULE, "atomic_write"
            ) as write, mock.patch.object(MODULE, "run_command") as command:
                result = MODULE.recover(document, str(raw["recoveryConfirmation"]))
            self.assertEqual(result["status"], "already-recovered")
            self.assertFalse(result["serviceRestarted"])
            write.assert_not_called()
            command.assert_not_called()

    def test_healthy_baseline_with_failed_account_canary_is_not_restarted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, raw = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "launch_state", return_value=(True, 321, True)), mock.patch.object(
                MODULE, "probe_health", return_value=True
            ), mock.patch.object(MODULE, "probe_communication", return_value=False), mock.patch.object(
                MODULE, "atomic_write"
            ) as write, mock.patch.object(MODULE, "run_command") as command:
                with self.assertRaisesRegex(MODULE.RecoveryRejected, "communication canary failed"):
                    MODULE.recover(document, str(raw["recoveryConfirmation"]))
            write.assert_not_called()
            command.assert_not_called()

    def test_launcher_only_drift_is_restored_without_restarting_healthy_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            job, raw = self.make_job(root)
            document = MODULE.load_job(job)
            launcher = pathlib.Path(str(raw["launcherPath"]))
            launcher.write_bytes(plistlib.dumps({
                "Label": "com.codexx.cliproxyapi",
                "ProgramArguments": [str(root / "candidate"), "--config", str(raw["configPath"])],
            }))
            with mock.patch.object(MODULE, "launch_state", side_effect=[(True, 321, True), (True, 321, True)]), mock.patch.object(
                MODULE, "probe_health", return_value=True
            ), mock.patch.object(MODULE, "probe_communication", return_value=True), mock.patch.object(
                MODULE, "run_command"
            ) as command:
                result = MODULE.recover(document, str(raw["recoveryConfirmation"]))
            self.assertEqual(result["status"], "recovered")
            self.assertTrue(result["launcherRestored"])
            self.assertFalse(result["serviceRestarted"])
            command.assert_not_called()

    def test_offline_service_restores_snapshot_and_bootstraps_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, raw = self.make_job(pathlib.Path(temporary))
            document = MODULE.load_job(job)
            with mock.patch.object(MODULE, "launch_state", return_value=(False, 0, False)), mock.patch.object(
                MODULE, "bootstrap_baseline", return_value=456
            ) as bootstrap, mock.patch.object(MODULE, "probe_health", return_value=True), mock.patch.object(
                MODULE, "probe_communication", return_value=True
            ):
                result = MODULE.recover(document, str(raw["recoveryConfirmation"]))
            self.assertEqual(result["status"], "recovered")
            self.assertEqual(result["pid"], 456)
            self.assertTrue(result["serviceRestarted"])
            bootstrap.assert_called_once()

    def test_loaded_candidate_is_fully_unloaded_before_baseline_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            job, raw = self.make_job(root)
            document = MODULE.load_job(job)
            launcher = pathlib.Path(str(raw["launcherPath"]))
            launcher.write_bytes(plistlib.dumps({
                "Label": "com.codexx.cliproxyapi",
                "ProgramArguments": [str(root / "candidate"), "--config", str(raw["configPath"])],
            }))
            completed = MODULE.subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with mock.patch.object(MODULE, "launch_state", side_effect=[(True, 999, False), (True, 999, False)]), mock.patch.object(
                MODULE, "run_command", return_value=completed
            ) as command, mock.patch.object(MODULE, "wait_unloaded") as unloaded, mock.patch.object(
                MODULE, "bootstrap_baseline", return_value=456
            ), mock.patch.object(MODULE, "probe_health", return_value=True), mock.patch.object(
                MODULE, "probe_communication", return_value=True
            ):
                result = MODULE.recover(document, str(raw["recoveryConfirmation"]))
            self.assertEqual(result["status"], "recovered")
            self.assertIn("bootout", command.call_args.args[0])
            unloaded.assert_called_once()

    def test_tampered_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job, unused = self.make_job(pathlib.Path(temporary))
            (job / "launcher.before").write_bytes(b"changed")
            with self.assertRaisesRegex(MODULE.RecoveryRejected, "snapshot changed"):
                MODULE.load_job(job)

    def test_failed_communication_receipt_preserves_healthy_service_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary)
            document = {
                "jobId": job.name,
                "jobPath": str(job),
                "recoveryConfirmation": "RESTORE LOCAL CPA BASELINE test abcdef123456",
            }
            failure = MODULE.RecoveryRejected(
                "communication_failed", "communication failed", service_restarted=True
            )
            output = io.StringIO()
            with mock.patch.object(MODULE.sys, "platform", "darwin"), mock.patch.object(
                MODULE, "load_job", return_value=document
            ), mock.patch.object(MODULE, "recover", side_effect=failure), mock.patch.object(
                MODULE, "launch_state", return_value=(True, 654, True)
            ), mock.patch.object(MODULE, "probe_health", return_value=True), contextlib.redirect_stdout(output):
                self.assertEqual(MODULE.main(["--job", str(job), "--apply", "--confirm", "x"]), 1)
            result = json.loads(output.getvalue())
            receipt = json.loads((job / "recovery-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(result["failureCode"], "communication_failed")
            self.assertTrue(result["serviceAvailable"])
            self.assertEqual(result["healthCanary"], "passed")
            self.assertTrue(receipt["serviceRestarted"])


if __name__ == "__main__":
    unittest.main()
