from __future__ import annotations

import importlib.util
import os
import pathlib
import plistlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/install_cpa_policy_candidate.py"
SPEC = importlib.util.spec_from_file_location("install_cpa_policy_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CpaPolicyInstallerTests(unittest.TestCase):
    def test_plan_requires_distinct_stage_and_activation_confirmations(self) -> None:
        contract = MODULE.load_contract(MODULE.DEFAULT_CONTRACT)
        value = MODULE.expanded_target("local", contract)
        document = MODULE.plan_document("local", value)
        self.assertTrue(document["stageConfirmation"].startswith("STAGE LOCAL CPA POLICY"))
        self.assertTrue(document["activationConfirmation"].startswith("ACTIVATE LOCAL CPA POLICY"))
        self.assertNotEqual(document["stageConfirmation"], document["activationConfirmation"])
        self.assertFalse(document["stageChangesService"])
        self.assertTrue(document["activationRestartsExternalCPA"])
        self.assertFalse(document["activationStopsCodexProcesses"])
        self.assertTrue(document["gracefulCPAServiceRestart"])
        self.assertFalse(document["inFlightRequestContinuityGuaranteed"])
        self.assertTrue(document["localActivationRequiresRealCodexCanary"])
        self.assertTrue(document["localActivationRollsBackOnCommunicationFailure"])
        self.assertTrue(document["eventDrivenArchiveWatcherActivationSeparate"])
        self.assertEqual(document["requiredActiveCloudxVersion"], "0.1.17")
        self.assertFalse(document["weeklyQuotaArchived"])
        self.assertFalse(document["periodicAccountProbe"])
        self.assertTrue(document["incidentSweepTrigger"])
        self.assertEqual(document["incidentProbeConcurrency"], "adaptive-up-to-32")

    def test_cloud_drop_ins_select_exact_candidate_and_private_failure_dir(self) -> None:
        value = MODULE.expanded_target("cloud", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        gateway, health = MODULE.cloud_drop_ins(value)
        gateway_text = gateway.decode("utf-8")
        health_text = health.decode("utf-8")
        self.assertIn("ExecStart=\nExecStart=%s" % value["stagedBinary"], gateway_text)
        self.assertIn("CLIPROXY_AUTH_DIR=%s" % value["authDirectory"], gateway_text)
        self.assertIn("CLIPROXY_AUTH_FAILURE_DIR=%s" % value["failureDirectory"], gateway_text)
        self.assertIn("CLIPROXY_AUTH_SWEEP_DIR=%s" % value["sweepDirectory"], gateway_text)
        self.assertIn("ReadWritePaths=%s" % value["failureDirectory"], health_text)
        self.assertIn(str(value["sweepDirectory"]), health_text)
        self.assertNotIn("systemctl", gateway_text + health_text)

    def test_local_plist_preserves_launcher_fields_and_adds_only_policy_environment(self) -> None:
        value = MODULE.expanded_target("local", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        original = {
            "Label": value["serviceLabel"],
            "ProgramArguments": [str(value["baselineBinary"]), "--config", str(value["config"])],
            "RunAtLoad": True,
            "StandardOutPath": "/tmp/cpa.out",
            "EnvironmentVariables": {"EXISTING": "kept"},
        }
        updated = plistlib.loads(MODULE.local_plist(plistlib.dumps(original), value))
        self.assertEqual(updated["ProgramArguments"][0], str(value["stagedBinary"]))
        self.assertEqual(updated["ProgramArguments"][1:], original["ProgramArguments"][1:])
        self.assertEqual(updated["StandardOutPath"], original["StandardOutPath"])
        self.assertEqual(updated["EnvironmentVariables"]["EXISTING"], "kept")
        self.assertEqual(updated["EnvironmentVariables"]["CLIPROXY_AUTH_DIR"], str(value["authDirectory"]))
        self.assertEqual(
            updated["EnvironmentVariables"]["CLIPROXY_AUTH_FAILURE_DIR"],
            str(value["failureDirectory"]),
        )
        self.assertEqual(
            updated["EnvironmentVariables"]["CLIPROXY_AUTH_SWEEP_DIR"],
            str(value["sweepDirectory"]),
        )

    def test_local_stage_is_side_by_side_and_idempotent_without_service_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            candidate_path = root / "candidate"
            candidate_raw = b"candidate-bytes"
            candidate_path.write_bytes(candidate_raw)
            value = {
                "version": "test-policy.1",
                "candidateSha256": MODULE.sha256_bytes(candidate_raw),
                "candidateSize": len(candidate_raw),
                "stageRoot": root / "releases",
            }
            value["stagedBinary"] = value["stageRoot"] / value["version"] / "cli-proxy-api"
            snapshot = MODULE.Snapshot(True, candidate_raw, 0o700, os.geteuid(), os.getegid())
            with mock.patch.object(MODULE, "verify_candidate", return_value=snapshot), mock.patch.object(
                MODULE,
                "run_command",
            ) as command:
                first = MODULE.stage_candidate("local", candidate_path, value)
                second = MODULE.stage_candidate("local", candidate_path, value)
            self.assertEqual(first["status"], "staged")
            self.assertEqual(second["status"], "already-staged")
            self.assertEqual(value["stagedBinary"].read_bytes(), candidate_raw)
            command.assert_not_called()

    def test_contract_binds_observed_baseline_and_candidate_digests(self) -> None:
        contract = MODULE.load_contract(MODULE.DEFAULT_CONTRACT)
        local = contract["targets"]["local"]
        cloud = contract["targets"]["cloud"]
        self.assertEqual(local["baselineSha256"], "cf9641b3e50ae486aec1698dec88f735589680f9ae98558c29cde184daac3a96")
        self.assertEqual(cloud["baselineSha256"], "1d0abbc6316b1869f74896109c0efb5e19c8197b8226f48a74212ed0a6f5a39d")
        self.assertEqual(local["candidateSha256"], "1cff3152e34666d2753add54ce7f5f96dbd643e607c1f136a9052cd28eba9ecd")
        self.assertEqual(cloud["candidateSha256"], "453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b")

    def test_activation_rejects_an_older_receipt_consumer(self) -> None:
        value = MODULE.expanded_target("local", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        completed = MODULE.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"schema":"cloudx.self-check.v1","status":"ok","version":"0.1.16"}',
            stderr="",
        )
        with mock.patch.object(MODULE, "safe_snapshot"), mock.patch.object(
            MODULE,
            "run_command",
            return_value=completed,
        ):
            with self.assertRaisesRegex(MODULE.CpaPolicyInstallRejected, "receipt consumer"):
                MODULE.require_active_cloudx("local", value)

    def test_local_communication_canary_uses_pinned_official_codex_profile(self) -> None:
        value = MODULE.expanded_target("local", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        completed = MODULE.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=MODULE.COMMUNICATION_CANARY_TEXT,
            stderr="",
        )
        with mock.patch.object(pathlib.Path, "is_file", return_value=True), mock.patch.object(
            pathlib.Path,
            "is_dir",
            return_value=True,
        ), mock.patch.object(pathlib.Path, "is_symlink", return_value=False), mock.patch.object(
            MODULE.os,
            "access",
            return_value=True,
        ), mock.patch.object(MODULE, "run_command", return_value=completed) as command:
            self.assertEqual(MODULE.probe_local_communication(value), "passed")
        arguments = command.call_args.args[0]
        options = command.call_args.kwargs
        self.assertEqual(arguments[0], str(value["codexBinary"]))
        self.assertIn(MODULE.COMMUNICATION_CANARY_TEXT, arguments[-1])
        self.assertEqual(options["environment"]["CODEX_HOME"], str(value["communicationCodexHome"]))
        self.assertNotIn("OPENAI_BASE_URL", options["environment"])

    def test_local_communication_canary_rejects_missing_expected_reply(self) -> None:
        value = MODULE.expanded_target("local", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        completed = MODULE.subprocess.CompletedProcess(args=[], returncode=0, stdout="different", stderr="")
        with mock.patch.object(pathlib.Path, "is_file", return_value=True), mock.patch.object(
            pathlib.Path,
            "is_dir",
            return_value=True,
        ), mock.patch.object(pathlib.Path, "is_symlink", return_value=False), mock.patch.object(
            MODULE.os,
            "access",
            return_value=True,
        ), mock.patch.object(MODULE, "run_command", return_value=completed):
            with self.assertRaises(MODULE.CpaPolicyInstallRejected):
                MODULE.probe_local_communication(value)


if __name__ == "__main__":
    unittest.main()
