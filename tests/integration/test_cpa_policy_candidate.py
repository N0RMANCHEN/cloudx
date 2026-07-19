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
        self.assertFalse(manifest["policy"]["periodicAccountProbe"])
        self.assertEqual(manifest["policy"]["incidentProbeConcurrency"], "adaptive-up-to-32")
        self.assertEqual(
            manifest["policy"]["aggregateSweepTriggerCodes"],
            ["auth_unavailable", "model_cooldown"],
        )
        self.assertEqual(manifest["policy"]["sweepTriggerSchema"], "cloudx.cpa-sweep-trigger.v1")
        self.assertFalse(manifest["policy"]["weeklyQuotaArchived"])
        self.assertEqual(local["candidateSha256"], "bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3")
        self.assertEqual(cloud["candidateSha256"], "5f83b1821d2be7cf5b7615973e4e6130d477386e16eae3a50af46e99bf7af7f8")

    def test_patch_digests_are_bound_by_manifest(self) -> None:
        manifest = MODULE.load_manifest()
        for target in ("local", "cloud"):
            config = MODULE.target_config(target, manifest)
            patches = MODULE.verified_patches(config)
            self.assertEqual(len(patches), 2)
            self.assertEqual(MODULE.sha256_file(patches[0]), config["patchSha256"])
            self.assertEqual(
                MODULE.sha256_file(patches[1]),
                config["supplementalPatches"][0]["sha256"],
            )

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

            sweep = MODULE.verified_patches(MODULE.target_config(target, manifest))[1].read_text(
                encoding="utf-8"
            )
            self.assertIn("cloudx.cpa-sweep-trigger.v1", sweep)
            self.assertIn("CLIPROXY_AUTH_SWEEP_DIR", sweep)
            self.assertIn('code == "auth_unavailable"', sweep)
            self.assertIn("func (e *modelCooldownError) CloudxPoolUnavailable() bool", sweep)
            self.assertIn("errors.As(err, &poolUnavailable)", sweep)
            self.assertIn("newModelCooldownError", sweep)
            self.assertNotIn('code == "model_cooldown"', sweep)
            trigger_fields = sweep.split("type cloudxSweepTrigger struct", 1)[1].split("}", 1)[0]
            for forbidden in ("Provider", "Model", "AuthFile", "Token"):
                self.assertNotIn(forbidden, trigger_fields)


if __name__ == "__main__":
    unittest.main()
