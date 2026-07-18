from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
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
        self.assertFalse(document["currentTurnRestarted"])
        self.assertTrue(document["realCodexCanaryBeforeActivation"])
        self.assertTrue(document["realCodexCanaryAfterActivation"])
        self.assertTrue(document["realCodexCanaryAfterRollback"])
        self.assertTrue(document["automaticRollback"])
        self.assertFalse(document["automaticAction"])
        self.assertEqual(document["requiredActiveCloudxVersion"], "0.1.16")
        self.assertTrue(document["confirmation"].startswith("ACTIVATE LOCAL CPA POLICY"))

    def test_current_cloudx_version_requires_a_real_selector(self) -> None:
        self.assertEqual(MODULE.current_cloudx_version(pathlib.Path("/nonexistent-cloudx-home")), "")

    def test_worker_accepts_only_installer_result_with_real_communication_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job = pathlib.Path(temporary)
            files = {
                "installer": job / "install_cpa_policy_candidate.py",
                "contract": job / "deployment-contract.json",
                "worker": job / "schedule_local_cpa_policy_activation.py",
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
                    "requiredActiveCloudxVersion": "0.1.16",
                    "candidateVersion": "test-policy.1",
                    "candidateSha256": "a" * 64,
                    "installerSha256": MODULE.sha256(files["installer"].read_bytes()),
                    "contractSha256": MODULE.sha256(files["contract"].read_bytes()),
                    "workerSha256": MODULE.sha256(files["worker"].read_bytes()),
                },
            )
            completed = MODULE.subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({"status": "active", "communicationCanary": "passed"}),
                stderr="",
            )
            with mock.patch.object(MODULE, "current_cloudx_version", return_value="0.1.16"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ):
                self.assertEqual(MODULE.worker(job), 0)
            receipt = json.loads((job / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "accepted")
            self.assertEqual(receipt["communicationCanary"], "passed")


if __name__ == "__main__":
    unittest.main()
