from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/build_cpa_policy_candidate.py"
SPEC = importlib.util.spec_from_file_location("build_cpa_policy_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CpaPolicyCandidateTests(unittest.TestCase):
    def test_manifest_pins_both_existing_endpoint_revisions(self) -> None:
        manifest = MODULE.load_manifest()
        local = MODULE.target_config("local", manifest)
        cloud = MODULE.target_config("cloud", manifest)
        self.assertEqual(local["upstreamCommit"], "15ac7fb9324095330e60f522147b8a8e81f16ab5")
        self.assertEqual(cloud["upstreamCommit"], "5b7f2361ee27d195f6514dde08656f6e4773a9a4")
        self.assertEqual(manifest["policy"]["maxConcurrentAPIRequests"], 2)
        self.assertEqual(manifest["policy"]["minimumFailureEvidence"], 1)
        self.assertTrue(manifest["policy"]["permanentFailureArchivesImmediately"])
        self.assertFalse(manifest["policy"]["provisionalFailureArchived"])
        self.assertEqual(manifest["policy"]["accountProbeConcurrency"], 2)
        self.assertFalse(manifest["policy"]["weeklyQuotaArchived"])
        self.assertEqual(local["candidateSha256"], "f288838053f43a82c50d2ab23bcb096c627a848fdf662413544a483f908f236d")
        self.assertEqual(cloud["candidateSha256"], "7c9603a380f9fbd7bdbe1c8ecbf938504f6055677ba4d4de2cd7004398a02229")

    def test_patch_digests_are_bound_by_manifest(self) -> None:
        manifest = MODULE.load_manifest()
        for target in ("local", "cloud"):
            config = MODULE.target_config(target, manifest)
            patch = MODULE.verified_patch(config)
            self.assertTrue(patch.is_file())
            self.assertEqual(MODULE.sha256_file(patch), config["patchSha256"])

    def test_plan_never_claims_install_activation_or_restart(self) -> None:
        config = MODULE.target_config("local", MODULE.load_manifest())
        document = MODULE.plan_document("local", config, pathlib.Path("/tmp/candidate"))
        self.assertFalse(document["installs"])
        self.assertFalse(document["activates"])
        self.assertFalse(document["restarts"])

    def test_build_rejects_active_and_repository_outputs(self) -> None:
        with self.assertRaises(MODULE.CandidateBuildRejected):
            MODULE.verify_output(pathlib.Path.home() / ".local/bin/cli-proxy-api")
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            with self.assertRaises(MODULE.CandidateBuildRejected):
                MODULE.verify_output(pathlib.Path(temporary) / "candidate")

    def test_patches_encode_strict_quota_exclusion_and_concurrency_two(self) -> None:
        manifest = MODULE.load_manifest()
        for target in ("local", "cloud"):
            patch = MODULE.verified_patch(MODULE.target_config(target, manifest)).read_text(encoding="utf-8")
            self.assertIn("cloudxMaxConcurrentAPIRequests = 2", patch)
            self.assertIn('"weekly quota"', patch)
            self.assertIn('"deactivated_workspace"', patch)
            self.assertIn("status == http.StatusTooManyRequests", patch)
            self.assertIn("if !state.conclusive", patch)
            self.assertIn("FailureCount:         state.count", patch)


if __name__ == "__main__":
    unittest.main()
