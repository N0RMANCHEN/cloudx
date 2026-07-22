from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
MODULE_PATH = ROOT / "scripts/schedule_local_cpa_failure_watcher.py"
SPEC = importlib.util.spec_from_file_location("schedule_local_cpa_failure_watcher", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LocalCpaFailureWatcherSchedulerTests(unittest.TestCase):
    def test_plan_keeps_watcher_separate_and_cpa_inert(self) -> None:
        document = MODULE.plan("20260719T160250Z-9a24174c")
        self.assertEqual(document["confirmation"], MODULE.CONFIRMATION)
        self.assertTrue(document["requiresAcceptedActivationReceipt"])
        self.assertTrue(document["requiresActivationCommunicationCanary"])
        self.assertFalse(document["restartsExternalCPA"])
        self.assertFalse(document["stopsCodexProcesses"])
        self.assertTrue(document["automaticRollback"])
        self.assertFalse(document["automaticAction"])

    def test_schedule_copies_exact_inputs_before_starting_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = pathlib.Path(temporary)
            activation_job = home / ".local/state/cloudx/cpa-policy-activation-jobs/20260719T160250Z-9a24174c"
            activation_job.mkdir(parents=True, mode=0o700)
            activation_document = {"jobId": activation_job.name, "quiescenceDeadlineEpoch": 1000.0}
            watcher = mock.Mock()
            watcher.target_value.return_value = {}
            watcher.plan_document.return_value = {"confirmation": MODULE.CONFIRMATION}
            with mock.patch.object(MODULE.sys, "platform", "darwin"), mock.patch.object(
                MODULE, "activation_job", return_value=(activation_job, activation_document)
            ), mock.patch.object(
                MODULE.activation, "current_cloudx_version", return_value="0.1.29"
            ), mock.patch.object(
                MODULE, "watcher_module", return_value=watcher
            ), mock.patch.object(
                MODULE.pathlib.Path, "home", return_value=home
            ), mock.patch.object(
                MODULE.subprocess, "Popen", return_value=types.SimpleNamespace(pid=123)
            ):
                result = MODULE.schedule(activation_job, MODULE.CONFIRMATION)
            follower = pathlib.Path(result["receipt"]).parent
            document = json.loads((follower / "job.json").read_text(encoding="utf-8"))
            self.assertTrue((follower / "install_cpa_failure_watcher.py").is_file())
            self.assertTrue((follower / "deployment-contract.json").is_file())
            self.assertEqual(document["activationJob"], str(activation_job))
            self.assertEqual(result["workerPid"], 123)
            self.assertFalse(result["restartsExternalCPA"])

    def _worker_job(self, root: pathlib.Path, activation_receipt: dict[str, object]) -> pathlib.Path:
        root = root / "20260719T160250Z-9a24174c"
        root.mkdir()
        names = (
            "install_cpa_failure_watcher.py",
            "deployment-contract.json",
            "schedule_local_cpa_failure_watcher.py",
            "schedule_local_cpa_policy_activation.py",
        )
        for name in names:
            (root / name).write_bytes((name + "-bytes").encode("ascii"))
        source = root / "activation-receipt.json"
        source.write_text(json.dumps(activation_receipt), encoding="utf-8")
        MODULE.activation.atomic_json(root / "job.json", {
            "schema": MODULE.JOB_SCHEMA,
            "jobId": "20260719T160250Z-9a24174c",
            "activationReceipt": str(source),
            "deadlineEpoch": 1000.0,
            "confirmation": MODULE.CONFIRMATION,
            "watcherSha256": MODULE.activation.sha256((root / names[0]).read_bytes()),
            "contractSha256": MODULE.activation.sha256((root / names[1]).read_bytes()),
            "workerSha256": MODULE.activation.sha256((root / names[2]).read_bytes()),
            "schedulerSha256": MODULE.activation.sha256((root / names[3]).read_bytes()),
            "requiredPolicyVersion": MODULE.REQUIRED_POLICY_VERSION,
            "requiredPolicySha256": MODULE.REQUIRED_POLICY_SHA256,
            "pollSeconds": 60,
        })
        return root

    def test_worker_rejects_failed_activation_without_invoking_watcher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = self._worker_job(pathlib.Path(temporary), {
                "schema": MODULE.ACTIVATION_RECEIPT_SCHEMA,
                "jobId": "20260719T160250Z-9a24174c",
                "status": "failed",
            })
            with mock.patch.object(MODULE.subprocess, "run") as run:
                self.assertEqual(MODULE.worker(job), 1)
            run.assert_not_called()
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["failureCode"], "activation_not_accepted")
            self.assertFalse(receipt["watcherActivated"])

    def test_worker_records_fail_closed_receipt_for_invalid_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary) / "20260719T160250Z-9a24174c"
            job.mkdir()
            MODULE.activation.atomic_json(job / "job.json", {
                "schema": MODULE.JOB_SCHEMA,
                "jobId": "20260719T160250Z-deadbeef",
            })
            with mock.patch.object(MODULE.subprocess, "run") as run:
                self.assertEqual(MODULE.worker(job), 1)
            run.assert_not_called()
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["failureCode"], "follower_failed")
            self.assertFalse(receipt["watcherActivated"])

    def test_worker_activates_only_after_accepted_policy_and_communication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = self._worker_job(pathlib.Path(temporary), {
                "schema": MODULE.ACTIVATION_RECEIPT_SCHEMA,
                "jobId": "20260719T160250Z-9a24174c",
                "status": "accepted",
                "candidateVersion": MODULE.REQUIRED_POLICY_VERSION,
                "candidateSha256": MODULE.REQUIRED_POLICY_SHA256,
                "communicationCanary": "passed",
                "serviceAvailable": True,
            })
            completed = MODULE.subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"status": "active"}), stderr=""
            )
            with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
                self.assertEqual(MODULE.worker(job), 0)
            self.assertEqual(run.call_count, 1)
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "accepted")
            self.assertTrue(receipt["watcherActivated"])
            self.assertFalse(receipt["externalCpaRestarted"])


if __name__ == "__main__":
    unittest.main()
