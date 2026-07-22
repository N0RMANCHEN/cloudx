from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/build_cpa_agent_identity_candidate.py"
SPEC = importlib.util.spec_from_file_location("build_cpa_agent_identity_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CpaAgentIdentityCandidateTests(unittest.TestCase):
    def test_manifest_pins_reviewed_official_source_patch_and_candidate(self) -> None:
        manifest = MODULE.load_manifest()
        self.assertEqual(manifest["upstreamTag"], "v7.0.2")
        self.assertEqual(
            manifest["upstreamCommit"],
            "1fca942b9c2c5bbdf78334eb4744a098983a05e9",
        )
        self.assertEqual(manifest["goVersion"], "1.26.0")
        self.assertEqual(manifest["capabilities"], ["codex-agent-identity-v1"])
        self.assertEqual(
            manifest["candidateSha256"],
            "85e8a2a051088ce28cabd4a34847eb77a72a36bac90c3f234e7367e61f189f04",
        )
        self.assertTrue(manifest["preservesFastServiceTier"])

    def test_patch_digest_and_required_runtime_behaviors_are_bound(self) -> None:
        manifest = MODULE.load_manifest()
        patch = MODULE.verified_patch(manifest)
        self.assertEqual(MODULE.sha256_file(patch), manifest["patchSha256"])
        text = patch.read_text(encoding="utf-8")
        self.assertIn("AgentAssertion ", text)
        self.assertIn('"/v1/agent/"', text)
        self.assertIn("codexAgentIdentityRegisterAndCache", text)
        self.assertIn("codexAgentIdentityDecryptTaskID", text)
        self.assertIn("TestCodexAgentIdentityIgnoresImportedTaskID", text)
        self.assertIn("X-Cloudx-CPA-Capabilities", text)
        self.assertIn('case "fast":', text)

    def test_plan_never_claims_install_activation_or_restart(self) -> None:
        document = MODULE.plan_document(MODULE.load_manifest(), pathlib.Path("/tmp/candidate"))
        self.assertFalse(document["installs"])
        self.assertFalse(document["activates"])
        self.assertFalse(document["restarts"])
        self.assertEqual(document["capabilities"], ["codex-agent-identity-v1"])

    def test_build_rejects_active_and_repository_outputs(self) -> None:
        with self.assertRaises(MODULE.CandidateBuildRejected):
            MODULE.verify_output(pathlib.Path.home() / ".local/bin/cli-proxy-api")
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            with self.assertRaises(MODULE.CandidateBuildRejected):
                MODULE.verify_output(pathlib.Path(temporary) / "candidate")


if __name__ == "__main__":
    unittest.main()
