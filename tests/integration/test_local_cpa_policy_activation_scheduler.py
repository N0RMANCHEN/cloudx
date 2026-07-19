from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/schedule_local_cpa_policy_activation.py"
SPEC = importlib.util.spec_from_file_location("schedule_local_cpa_policy_activation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LocalCpaPolicyActivationSchedulerTests(unittest.TestCase):
    def test_plan_defers_restart_and_requires_three_real_communication_gates(self) -> None:
        document = MODULE.plan(180)
        self.assertEqual(document["deferredSeconds"], 180)
        self.assertTrue(document["waitsForNaturalQuiescence"])
        self.assertEqual(document["maximumQuiescenceWaitSeconds"], 7 * 24 * 60 * 60)
        self.assertEqual(document["quiescencePollSeconds"], 60)
        self.assertFalse(document["currentTurnRestarted"])
        self.assertFalse(document["codexProcessesStopped"])
        self.assertTrue(document["sharedCPAUnavailableDuringRestart"])
        self.assertFalse(document["inFlightRequestContinuityGuaranteed"])
        self.assertTrue(document["realCodexCanaryBeforeActivation"])
        self.assertTrue(document["realCodexCanaryAfterActivation"])
        self.assertTrue(document["realCodexCanaryAfterRollback"])
        self.assertTrue(document["automaticRollback"])
        self.assertTrue(document["requiresZeroEstablishedConnections"])
        self.assertTrue(document["manualRecoveryPreparedBeforeRestart"])
        self.assertTrue(document["automaticRecoveryUsesManualTool"])
        self.assertTrue(document["failureStageReceipt"])
        self.assertFalse(document["automaticAction"])
        self.assertEqual(document["requiredActiveCloudxVersion"], "0.1.21")
        self.assertTrue(document["confirmation"].startswith("ACTIVATE LOCAL CPA POLICY"))

    def test_current_cloudx_version_requires_a_real_selector(self) -> None:
        self.assertEqual(MODULE.current_cloudx_version(pathlib.Path("/nonexistent-cloudx-home")), "")

    def test_schedule_prepares_manual_recovery_before_starting_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = pathlib.Path(temporary)
            launcher = home / "Library/LaunchAgents/com.codexx.cliproxyapi.plist"
            baseline = home / ".local/bin/cli-proxy-api"
            launcher.parent.mkdir(parents=True)
            baseline.parent.mkdir(parents=True)
            launcher_raw = b"baseline-launcher"
            baseline_raw = b"baseline-binary"
            launcher.write_bytes(launcher_raw)
            baseline.write_bytes(baseline_raw)
            value = {
                "version": "test-policy.1",
                "candidateSha256": "a" * 64,
                "baselineSha256": MODULE.sha256(baseline_raw),
                "stagedBinary": home / "candidate",
                "launcher": launcher,
                "baselineBinary": baseline,
                "serviceLabel": "com.codexx.cliproxyapi",
                "config": home / "config.yaml",
                "codexBinary": home / "codex",
                "communicationCodexHome": home / "codex-home",
            }
            launcher_snapshot = types.SimpleNamespace(
                data=launcher_raw, mode=0o644, uid=os.geteuid(), gid=os.getegid()
            )
            baseline_snapshot = types.SimpleNamespace(
                data=baseline_raw, mode=0o700, uid=os.geteuid(), gid=os.getegid()
            )
            fake = mock.Mock()
            fake.load_contract.return_value = {}
            fake.expanded_target.return_value = value
            fake.confirmations.return_value = (
                "STAGE LOCAL CPA POLICY test abcdef123456",
                "ACTIVATE LOCAL CPA POLICY test abcdef123456",
            )
            fake.safe_snapshot.side_effect = [launcher_snapshot, baseline_snapshot]
            fake.sha256_bytes.side_effect = MODULE.sha256
            fake.MAX_LAUNCHER_BYTES = 256 * 1024
            fake.MAX_CANDIDATE_BYTES = 100 * 1024 * 1024
            process = types.SimpleNamespace(pid=123)
            with mock.patch.object(MODULE.sys, "platform", "darwin"), mock.patch.object(
                MODULE, "installer_module", return_value=fake
            ), mock.patch.object(
                MODULE, "current_cloudx_version", return_value="0.1.21"
            ), mock.patch.object(MODULE.pathlib.Path, "home", return_value=home), mock.patch.object(
                MODULE.subprocess, "Popen", return_value=process
            ):
                result = MODULE.schedule(180, "ACTIVATE LOCAL CPA POLICY test abcdef123456")
            job = pathlib.Path(result["receipt"]).parent
            document = json.loads((job / "job.json").read_text(encoding="utf-8"))
            self.assertTrue((job / "recover_local_cpa_policy.py").is_file())
            self.assertEqual((job / "launcher.before").read_bytes(), launcher_raw)
            self.assertTrue((job / "RECOVERY.txt").is_file())
            self.assertEqual(document["baselineSha256"], MODULE.sha256(baseline_raw))
            self.assertEqual(document["launcherSnapshotSha256"], MODULE.sha256(launcher_raw))
            self.assertEqual(result["recoveryCommand"][-1], document["recoveryConfirmation"])
            self.assertGreater(document["quiescenceDeadlineEpoch"], document["executeAfterEpoch"])
            self.assertEqual(result["maximumQuiescenceWaitSeconds"], 7 * 24 * 60 * 60)

    def test_quiescence_monitor_waits_without_mutating_until_five_sample_gate_passes(self) -> None:
        job = pathlib.Path("/private/job")
        recovery = job / "recover_local_cpa_policy.py"
        document = {
            "jobId": "test-job",
            "quiescenceDeadlineEpoch": 1000.0,
            "quiescencePollSeconds": 60,
        }
        busy = MODULE.subprocess.CompletedProcess(
            args=[], returncode=1, stdout=json.dumps({"status": "busy"}), stderr=""
        )
        ready = MODULE.subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"status": "quiescent"}), stderr=""
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[busy, ready]) as run, mock.patch.object(
            MODULE.time, "time", side_effect=[0.0]
        ), mock.patch.object(MODULE.time, "sleep") as sleep:
            self.assertTrue(MODULE.wait_for_quiescence(job, recovery, document))
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(60)

    def test_quiescence_timeout_records_no_activation_or_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary)
            files = {
                "installer": job / "install_cpa_policy_candidate.py",
                "recovery": job / "recover_local_cpa_policy.py",
                "contract": job / "deployment-contract.json",
                "worker": job / "schedule_local_cpa_policy_activation.py",
                "launcher": job / "launcher.before",
            }
            for name, path in files.items():
                path.write_bytes((name + "-bytes").encode("ascii"))
            MODULE.atomic_json(job / "job.json", {
                "schema": MODULE.JOB_SCHEMA,
                "jobId": "test-job",
                "executeAfterEpoch": 0,
                "quiescenceDeadlineEpoch": 1,
                "confirmation": "ACTIVATE LOCAL CPA POLICY test abcdef123456",
                "requiredActiveCloudxVersion": "0.1.21",
                "candidateVersion": "test-policy.1",
                "candidateSha256": "a" * 64,
                "installerSha256": MODULE.sha256(files["installer"].read_bytes()),
                "recoveryToolSha256": MODULE.sha256(files["recovery"].read_bytes()),
                "contractSha256": MODULE.sha256(files["contract"].read_bytes()),
                "workerSha256": MODULE.sha256(files["worker"].read_bytes()),
                "launcherSnapshotSha256": MODULE.sha256(files["launcher"].read_bytes()),
                "recoveryConfirmation": "RESTORE LOCAL CPA BASELINE test-job abcdef123456",
            })
            with mock.patch.object(MODULE, "current_cloudx_version", return_value="0.1.21"), mock.patch.object(
                MODULE, "wait_for_quiescence", return_value=False
            ), mock.patch.object(MODULE.subprocess, "run") as run:
                self.assertEqual(MODULE.worker(job), 1)
            run.assert_not_called()
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["failureCode"], "connections_present")
            self.assertEqual(receipt["recoveryStatus"], "not-required")
            self.assertTrue(receipt["serviceAvailable"])

    def test_worker_accepts_only_installer_result_with_real_communication_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary)
            files = {
                "installer": job / "install_cpa_policy_candidate.py",
                "recovery": job / "recover_local_cpa_policy.py",
                "contract": job / "deployment-contract.json",
                "worker": job / "schedule_local_cpa_policy_activation.py",
                "launcher": job / "launcher.before",
            }
            for name, path in files.items():
                path.write_bytes((name + "-bytes").encode("ascii"))
            MODULE.atomic_json(
                job / "job.json",
                {
                    "schema": MODULE.JOB_SCHEMA,
                    "jobId": "test-job",
                    "executeAfterEpoch": 0,
                    "confirmation": "ACTIVATE LOCAL CPA POLICY test abcdef123456",
                    "requiredActiveCloudxVersion": "0.1.21",
                    "candidateVersion": "test-policy.1",
                    "candidateSha256": "a" * 64,
                    "installerSha256": MODULE.sha256(files["installer"].read_bytes()),
                    "recoveryToolSha256": MODULE.sha256(files["recovery"].read_bytes()),
                    "contractSha256": MODULE.sha256(files["contract"].read_bytes()),
                    "workerSha256": MODULE.sha256(files["worker"].read_bytes()),
                    "launcherSnapshotSha256": MODULE.sha256(files["launcher"].read_bytes()),
                    "recoveryConfirmation": "RESTORE LOCAL CPA BASELINE test-job abcdef123456",
                },
            )
            completed = MODULE.subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({"status": "active", "communicationCanary": "passed"}),
                stderr="",
            )
            with mock.patch.object(MODULE, "current_cloudx_version", return_value="0.1.21"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                self.assertEqual(MODULE.worker(job), 0)
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "accepted")
            self.assertEqual(receipt["communicationCanary"], "passed")
            self.assertTrue(receipt["serviceAvailable"])
            self.assertEqual(receipt["recoveryStatus"], "not-required")

    def test_worker_records_failure_stage_and_independent_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary)
            files = {
                "installer": job / "install_cpa_policy_candidate.py",
                "recovery": job / "recover_local_cpa_policy.py",
                "contract": job / "deployment-contract.json",
                "worker": job / "schedule_local_cpa_policy_activation.py",
                "launcher": job / "launcher.before",
            }
            for name, path in files.items():
                path.write_bytes((name + "-bytes").encode("ascii"))
            MODULE.atomic_json(job / "job.json", {
                "schema": MODULE.JOB_SCHEMA,
                "jobId": "test-job",
                "executeAfterEpoch": 0,
                "confirmation": "ACTIVATE LOCAL CPA POLICY test abcdef123456",
                "requiredActiveCloudxVersion": "0.1.21",
                "candidateVersion": "test-policy.1",
                "candidateSha256": "a" * 64,
                "installerSha256": MODULE.sha256(files["installer"].read_bytes()),
                "recoveryToolSha256": MODULE.sha256(files["recovery"].read_bytes()),
                "contractSha256": MODULE.sha256(files["contract"].read_bytes()),
                "workerSha256": MODULE.sha256(files["worker"].read_bytes()),
                "launcherSnapshotSha256": MODULE.sha256(files["launcher"].read_bytes()),
                "recoveryConfirmation": "RESTORE LOCAL CPA BASELINE test-job abcdef123456",
            })
            completed = MODULE.subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="local CPA activation requires zero established connections"
            )
            recovered = {"status": "accepted", "communicationCanary": "passed", "serviceRestarted": False, "serviceAvailable": True}
            with mock.patch.object(MODULE, "current_cloudx_version", return_value="0.1.21"), mock.patch.object(
                MODULE.subprocess, "run", return_value=completed
            ), mock.patch.object(MODULE, "run_recovery", return_value=recovered):
                self.assertEqual(MODULE.worker(job), 1)
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["failureCode"], "connections_present")
            self.assertEqual(receipt["recoveryStatus"], "accepted")
            self.assertTrue(receipt["serviceAvailable"])


if __name__ == "__main__":
    unittest.main()
