from __future__ import annotations

import importlib.util
import json
import pathlib
import plistlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/install_cpa_agent_identity_candidate.py"
SPEC = importlib.util.spec_from_file_location("install_cpa_agent_identity_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CpaAgentIdentityInstallerTests(unittest.TestCase):
    def test_plan_separates_non_mutating_stage_from_explicit_restart(self) -> None:
        value = MODULE.expanded_contract(MODULE.load_contract(), pathlib.Path("/tmp/cloudx-user"))
        document = MODULE.plan_document(value)
        self.assertFalse(document["stageChangesService"])
        self.assertTrue(document["activationRestartsExternalCPA"])
        self.assertTrue(document["activationRequiresZeroEstablishedConnections"])
        self.assertTrue(document["activationPreservesBaselineBinary"])
        self.assertTrue(document["activationWritesHashBoundCapabilityManifest"])
        self.assertFalse(document["cloudxManagesExternalServiceLifecycle"])
        self.assertFalse(document["automaticActivation"])
        self.assertNotEqual(document["stageConfirmation"], document["activationConfirmation"])

    def test_contract_binds_observed_baseline_and_candidate(self) -> None:
        document = MODULE.load_contract()
        self.assertEqual(
            document["baselineSha256"],
            "9f5b098585723bb99399a6cba13da616099b653f62f9f59c7183d961567705c3",
        )
        self.assertEqual(
            document["candidateSha256"],
            "85e8a2a051088ce28cabd4a34847eb77a72a36bac90c3f234e7367e61f189f04",
        )
        self.assertEqual(document["requiredActiveCloudxVersion"], "0.1.22")

    def test_stage_is_side_by_side_idempotent_and_service_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            candidate = root / "candidate"
            raw = b"candidate"
            candidate.write_bytes(raw)
            value = {
                "version": "test-agent.1",
                "candidateSha256": MODULE.sha256_bytes(raw),
                "candidateSize": len(raw),
                "capabilities": ["codex-agent-identity-v1"],
                "stageRoot": root / "releases",
            }
            value["stagedBinary"] = value["stageRoot"] / value["version"] / "cli-proxy-api"
            first = MODULE.stage_candidate(candidate, value)
            second = MODULE.stage_candidate(candidate, value)
            self.assertEqual(first["status"], "staged")
            self.assertEqual(second["status"], "already-staged")
            self.assertFalse(first["serviceChanged"])
            self.assertEqual(value["stagedBinary"].read_bytes(), raw)

    def test_launcher_changes_only_selected_binary(self) -> None:
        document = {
            "Label": "com.codexx.cliproxyapi",
            "ProgramArguments": ["/old/cpa", "--config", "/config.yaml"],
            "RunAtLoad": True,
            "EnvironmentVariables": {"PRESERVED": "yes"},
        }
        value = {"stagedBinary": pathlib.Path("/new/cpa")}
        updated = plistlib.loads(MODULE.updated_launcher(document, value))
        self.assertEqual(updated["ProgramArguments"], ["/new/cpa", "--config", "/config.yaml"])
        self.assertEqual(updated["EnvironmentVariables"], {"PRESERVED": "yes"})
        self.assertTrue(updated["RunAtLoad"])

    def test_capability_manifest_binds_staged_binary_digest(self) -> None:
        value = {
            "stagedBinary": pathlib.Path("/staged/cli-proxy-api"),
            "candidateSha256": "a" * 64,
            "version": "7.0.2-agent.1",
            "capabilities": ["codex-agent-identity-v1"],
        }
        document = json.loads(MODULE.capability_manifest(value))
        self.assertEqual(document["schema"], MODULE.CAPABILITY_SCHEMA)
        self.assertEqual(document["binary"], "/staged/cli-proxy-api")
        self.assertEqual(document["binarySha256"], "a" * 64)

    def test_activation_switches_side_by_side_and_preserves_auth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            value = self._value(root)
            before = (value["authDirectory"] / "account.json").read_bytes()
            with mock.patch.object(MODULE, "require_active_cloudx"), mock.patch.object(
                MODULE, "zero_established_connections"
            ), mock.patch.object(MODULE, "bootout") as bootout, mock.patch.object(
                MODULE, "bootstrap"
            ) as bootstrap, mock.patch.object(MODULE, "probe_health") as probe:
                result = MODULE.activate(value, root)
            self.assertEqual(result["status"], "activated")
            self.assertTrue(result["capabilityAttested"])
            self.assertTrue(result["externalCPARestarted"])
            bootout.assert_called_once_with(value)
            bootstrap.assert_called_once_with(value)
            probe.assert_called_once_with(value, require_capability=True)
            self.assertEqual((value["authDirectory"] / "account.json").read_bytes(), before)
            launcher = plistlib.loads(value["launcher"].read_bytes())
            self.assertEqual(launcher["ProgramArguments"][0], str(value["stagedBinary"]))
            capability = json.loads(value["capabilityManifest"].read_text(encoding="utf-8"))
            self.assertEqual(capability["binarySha256"], value["candidateSha256"])

    def test_failed_activation_restores_original_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            value = self._value(root)
            original = value["launcher"].read_bytes()
            with mock.patch.object(MODULE, "require_active_cloudx"), mock.patch.object(
                MODULE, "zero_established_connections"
            ), mock.patch.object(MODULE, "bootout"), mock.patch.object(
                MODULE, "bootstrap"
            ), mock.patch.object(
                MODULE,
                "probe_health",
                side_effect=[MODULE.AgentIdentityInstallRejected("candidate failed"), None],
            ):
                with self.assertRaisesRegex(MODULE.AgentIdentityInstallRejected, "candidate failed"):
                    MODULE.activate(value, root)
            self.assertEqual(value["launcher"].read_bytes(), original)
            self.assertFalse(value["capabilityManifest"].exists())

    def test_automatic_rollback_does_not_overwrite_a_concurrent_external_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            value = self._value(root)
            updated = b"external-updater-replacement"

            def fail_after_external_update(unused_value: object, require_capability: bool) -> None:
                if require_capability:
                    value["baselineBinary"].write_bytes(updated)
                    raise MODULE.AgentIdentityInstallRejected("candidate failed")

            with mock.patch.object(MODULE, "require_active_cloudx"), mock.patch.object(
                MODULE, "zero_established_connections"
            ), mock.patch.object(MODULE, "bootout"), mock.patch.object(
                MODULE, "bootstrap"
            ), mock.patch.object(MODULE, "probe_health", side_effect=fail_after_external_update):
                with self.assertRaisesRegex(MODULE.AgentIdentityInstallRejected, "candidate failed"):
                    MODULE.activate(value, root)

            self.assertEqual(value["baselineBinary"].read_bytes(), updated)

    def test_explicit_restore_preserves_recorded_file_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            value = self._value(root)
            original_launcher, unused_document = MODULE.launcher_bytes(value)
            backup = MODULE.backup_state(value, original_launcher)
            value["baselineBinary"].chmod(0o700)
            value["baselineMetadata"].chmod(0o600)
            value["launcher"].chmod(0o600)
            with mock.patch.object(MODULE, "bootout"), mock.patch.object(
                MODULE, "bootstrap"
            ), mock.patch.object(MODULE, "probe_health"):
                MODULE.restore(value, backup)
            self.assertEqual(value["baselineBinary"].stat().st_mode & 0o777, 0o755)
            self.assertEqual(value["baselineMetadata"].stat().st_mode & 0o777, 0o644)
            self.assertEqual(value["launcher"].stat().st_mode & 0o777, 0o644)

    def _value(self, root: pathlib.Path) -> dict[str, object]:
        baseline = root / "baseline"
        baseline_raw = b"baseline"
        baseline.write_bytes(baseline_raw)
        baseline.chmod(0o755)
        metadata = root / "baseline.json"
        metadata_raw = b'{}\n'
        metadata.write_bytes(metadata_raw)
        metadata.chmod(0o644)
        stage = root / "releases/test-agent/cli-proxy-api"
        stage.parent.mkdir(parents=True)
        candidate_raw = b"candidate"
        stage.write_bytes(candidate_raw)
        stage.chmod(0o700)
        launcher = root / "agent.plist"
        launcher.write_bytes(plistlib.dumps({
            "Label": "com.codexx.cliproxyapi",
            "ProgramArguments": [str(baseline), "--config", str(root / "config.yaml")],
            "RunAtLoad": True,
        }))
        launcher.chmod(0o644)
        auth = root / "auth"
        auth.mkdir()
        (auth / "account.json").write_text('{"access_token":"secret"}\n', encoding="utf-8")
        return {
            "version": "test-agent",
            "candidateSha256": MODULE.sha256_bytes(candidate_raw),
            "candidateSize": len(candidate_raw),
            "requiredActiveCloudxVersion": "test",
            "baselineBinary": baseline,
            "baselineSha256": MODULE.sha256_bytes(baseline_raw),
            "baselineMetadata": metadata,
            "baselineMetadataSha256": MODULE.sha256_bytes(metadata_raw),
            "stageRoot": root / "releases",
            "stagedBinary": stage,
            "backupRoot": root / "backups",
            "capabilityManifest": root / "capabilities.json",
            "authDirectory": auth,
            "config": root / "config.yaml",
            "launcher": launcher,
            "serviceLabel": "com.codexx.cliproxyapi",
            "listenHost": "127.0.0.1",
            "listenPort": 8317,
            "capabilities": ["codex-agent-identity-v1"],
        }


if __name__ == "__main__":
    unittest.main()
