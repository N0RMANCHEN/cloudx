from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import plistlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/install_cpa_policy_candidate.py"
SPEC = importlib.util.spec_from_file_location("install_cpa_policy_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CpaPolicyInstallerTests(unittest.TestCase):
    def test_health_canary_retries_until_the_listener_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "config.yaml"
            config.write_text("host: 127.0.0.1\nport: 8317\n", encoding="utf-8")
            response = mock.Mock(status=200)
            response.read.return_value = b'{"status":"ok"}'
            connection = mock.Mock()
            connection.getresponse.return_value = response
            with mock.patch.object(
                MODULE.http.client,
                "HTTPConnection",
                side_effect=[ConnectionRefusedError("listener race"), connection],
            ) as constructor, mock.patch.object(MODULE.time, "sleep"):
                MODULE.probe_health(config)
        self.assertEqual(constructor.call_count, 2)
        connection.request.assert_called_once_with("GET", "/healthz")

    def test_health_canary_requires_the_declared_agent_identity_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "config.yaml"
            config.write_text("host: 127.0.0.1\nport: 8317\n", encoding="utf-8")
            missing = mock.Mock(status=200)
            missing.read.return_value = b'{"status":"ok"}'
            missing.getheader.return_value = "another-capability-v1"
            accepted = mock.Mock(status=200)
            accepted.read.return_value = b'{"status":"ok"}'
            accepted.getheader.return_value = "codex-agent-identity-v1"
            connections = []
            for response in (missing, accepted):
                connection = mock.Mock()
                connection.getresponse.return_value = response
                connections.append(connection)
            with mock.patch.object(
                MODULE.http.client,
                "HTTPConnection",
                side_effect=connections,
            ), mock.patch.object(MODULE.time, "sleep"):
                MODULE.probe_health(config, "codex-agent-identity-v1")
        self.assertEqual(sum(item.request.call_count for item in connections), 2)

    def test_policy_rollback_removes_only_empty_directories_created_by_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            failure = root / "failures"
            sweep = root / "sweeps"
            failure.mkdir()
            sweep.mkdir()
            MODULE.remove_created_empty_directories([failure, sweep])
            self.assertFalse(failure.exists())
            self.assertFalse(sweep.exists())

    def test_policy_rollback_refuses_to_remove_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary) / "failures"
            directory.mkdir()
            (directory / "receipt.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.CpaPolicyInstallRejected, "not empty or safe"):
                MODULE.remove_created_empty_directories([directory])
            self.assertTrue(directory.exists())

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
        self.assertTrue(document["localActivationRequiresPreparedRecoveryTool"])
        self.assertTrue(document["localActivationRequiresZeroEstablishedConnections"])
        self.assertTrue(document["eventDrivenArchiveWatcherActivationSeparate"])
        self.assertEqual(document["requiredActiveCloudxVersion"], "0.1.21")
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

        capability = json.loads(MODULE.capability_manifest_bytes(value))
        self.assertEqual(capability["schema"], "cloudx.cloud-cpa-capabilities.v1")
        self.assertEqual(capability["binary"], str(value["stagedBinary"]))
        self.assertEqual(capability["binarySha256"], value["candidateSha256"])
        self.assertEqual(capability["capabilities"], ["codex-agent-identity-v1"])

    def test_cloud_activation_publishes_capability_only_after_live_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            baseline_raw = b"baseline"
            value = {
                "version": "7.2.71-cloudx-policy.6",
                "candidateSha256": "a" * 64,
                "baselineSha256": MODULE.sha256_bytes(baseline_raw),
                "baselineBinary": root / "baseline",
                "stagedBinary": root / "candidate",
                "gatewayDropIn": root / "gateway.conf",
                "healthDropIn": root / "health.conf",
                "capabilityManifest": root / "capabilities.json",
                "failureDirectory": root / "failures",
                "sweepDirectory": root / "sweeps",
                "backupRoot": root / "backups",
                "authDirectory": root / "auth",
                "config": root / "config.yaml",
                "service": "cliproxy.service",
                "capabilities": ["codex-agent-identity-v1"],
            }
            absent = MODULE.Snapshot(False, b"", 0, 0, 0)
            baseline = MODULE.Snapshot(True, baseline_raw, 0o755, 0, 0)

            def snapshot(path: pathlib.Path, **unused: object) -> object:
                return baseline if path == value["baselineBinary"] else absent

            def command(argv: list[str], **unused: object) -> object:
                stdout = "ExecStart=%s\n" % value["stagedBinary"] if "ExecStart" in argv else ""
                return MODULE.subprocess.CompletedProcess(argv, 0, stdout, "")

            writes = []
            with mock.patch.object(MODULE.os, "geteuid", return_value=0), mock.patch.object(
                MODULE.sys, "platform", "linux"
            ), mock.patch.object(MODULE, "require_active_cloudx"), mock.patch.object(
                MODULE, "verify_candidate"
            ), mock.patch.object(MODULE, "safe_snapshot", side_effect=snapshot), mock.patch.object(
                MODULE.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=100, pw_gid=101)
            ), mock.patch.object(MODULE, "ensure_directory"), mock.patch.object(
                MODULE, "backup_snapshot", return_value=root / "backup"
            ), mock.patch.object(MODULE, "atomic_write", side_effect=lambda path, *args, **kwargs: writes.append(path)), mock.patch.object(
                MODULE, "run_command", side_effect=command
            ), mock.patch.object(MODULE, "wait_systemd_active", return_value=123), mock.patch.object(
                MODULE, "probe_policy", return_value=(401, "2")
            ), mock.patch.object(MODULE, "probe_health") as health:
                result = MODULE.activate_cloud(value)

        self.assertEqual(result["status"], "active")
        self.assertEqual(writes[-1], value["capabilityManifest"])
        health.assert_called_once_with(value["config"], "codex-agent-identity-v1")

    def test_cloud_activation_restores_capability_sidecar_when_publication_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            baseline_raw = b"baseline"
            value = {
                "version": "7.2.71-cloudx-policy.6",
                "candidateSha256": "a" * 64,
                "baselineSha256": MODULE.sha256_bytes(baseline_raw),
                "baselineBinary": root / "baseline",
                "stagedBinary": root / "candidate",
                "gatewayDropIn": root / "gateway.conf",
                "healthDropIn": root / "health.conf",
                "capabilityManifest": root / "capabilities.json",
                "failureDirectory": root / "failures",
                "sweepDirectory": root / "sweeps",
                "backupRoot": root / "backups",
                "authDirectory": root / "auth",
                "config": root / "config.yaml",
                "service": "cliproxy.service",
                "capabilities": ["codex-agent-identity-v1"],
            }
            absent = MODULE.Snapshot(False, b"", 0, 0, 0)
            baseline = MODULE.Snapshot(True, baseline_raw, 0o755, 0, 0)

            def snapshot(path: pathlib.Path, **unused: object) -> object:
                return baseline if path == value["baselineBinary"] else absent

            def write(path: pathlib.Path, *unused_args: object, **unused_kwargs: object) -> None:
                if path == value["capabilityManifest"]:
                    raise OSError("simulated sidecar failure")

            def command(argv: list[str], **unused: object) -> object:
                stdout = "ExecStart=%s\n" % value["stagedBinary"] if "ExecStart" in argv else ""
                return MODULE.subprocess.CompletedProcess(argv, 0, stdout, "")

            with mock.patch.object(MODULE.os, "geteuid", return_value=0), mock.patch.object(
                MODULE.sys, "platform", "linux"
            ), mock.patch.object(MODULE, "require_active_cloudx"), mock.patch.object(
                MODULE, "verify_candidate"
            ), mock.patch.object(MODULE, "safe_snapshot", side_effect=snapshot), mock.patch.object(
                MODULE.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=100, pw_gid=101)
            ), mock.patch.object(MODULE, "ensure_directory"), mock.patch.object(
                MODULE, "backup_snapshot", return_value=root / "backup"
            ), mock.patch.object(MODULE, "atomic_write", side_effect=write), mock.patch.object(
                MODULE, "run_command", side_effect=command
            ), mock.patch.object(MODULE, "wait_systemd_active", return_value=123), mock.patch.object(
                MODULE, "probe_policy", return_value=(401, "2")
            ), mock.patch.object(MODULE, "probe_health"), mock.patch.object(
                MODULE, "remove_created_empty_directories"
            ), mock.patch.object(MODULE, "restore_snapshot") as restore:
                with self.assertRaisesRegex(MODULE.CpaPolicyInstallRejected, "rolled back"):
                    MODULE.activate_cloud(value)

        restored_paths = [call.args[0] for call in restore.call_args_list]
        self.assertIn(value["capabilityManifest"], restored_paths)

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
        self.assertEqual(local["candidateSha256"], "bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3")
        self.assertEqual(cloud["candidateSha256"], "0a3b146dc607bf58aa648d0b80f4df3d81737103799593cbae501e843f7e8d80")
        self.assertEqual(cloud["capabilityManifest"], "/etc/cloudx/cloud-cpa-capabilities.json")
        self.assertEqual(cloud["capabilities"], ["codex-agent-identity-v1"])

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

    def test_local_activation_rejects_direct_use_without_a_recovery_bundle(self) -> None:
        value = MODULE.expanded_target("local", MODULE.load_contract(MODULE.DEFAULT_CONTRACT))
        unused_stage, confirmation = MODULE.confirmations("local", value)
        with self.assertRaisesRegex(MODULE.CpaPolicyInstallRejected, "prepared recovery bundle"):
            MODULE.main(["--target", "local", "--activate", "--confirm", confirmation])

    def test_local_recovery_quiescence_fails_closed_on_established_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            tool = root / "recover.py"
            tool.write_text("pass\n", encoding="utf-8")
            job = root / "job"
            job.mkdir()
            completed = MODULE.subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout=json.dumps({"status": "busy", "establishedSocketRows": 4}),
                stderr="",
            )
            with mock.patch.object(MODULE, "run_command", return_value=completed):
                with self.assertRaisesRegex(MODULE.CpaPolicyInstallRejected, "zero established connections"):
                    MODULE.run_local_recovery(tool, job, "confirm", quiescence=True)

    def test_local_recovery_accepts_the_prepared_manual_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            tool = root / "recover.py"
            tool.write_text("pass\n", encoding="utf-8")
            job = root / "job"
            job.mkdir()
            completed = MODULE.subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({"status": "already-recovered", "communicationCanary": "passed"}),
                stderr="",
            )
            with mock.patch.object(MODULE, "run_command", return_value=completed):
                result = MODULE.run_local_recovery(tool, job, "confirm", quiescence=False)
            self.assertEqual(result["status"], "already-recovered")

    def test_launchd_unload_requires_three_consecutive_absent_samples(self) -> None:
        absent = MODULE.subprocess.CompletedProcess(args=[], returncode=113, stdout="", stderr="")
        present = MODULE.subprocess.CompletedProcess(args=[], returncode=0, stdout="pid = 1", stderr="")
        with mock.patch.object(
            MODULE, "run_command", side_effect=[present, absent, absent, absent]
        ) as command, mock.patch.object(MODULE.time, "sleep"):
            MODULE.wait_launchd_unloaded("gui/501", "com.example")
        self.assertEqual(command.call_count, 4)


if __name__ == "__main__":
    unittest.main()
