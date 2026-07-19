from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_phi_cloudx_legacy_health_bridge import (  # noqa: E402
    DEFAULT_EVIDENCE,
    BridgeEvidenceRejected,
    evaluate,
    load_evidence,
    main,
    validate_cloudx_source,
)


class PhiLegacyHealthBridgeTests(unittest.TestCase):
    def test_current_evidence_is_runtime_accepted_and_non_authorizing(self) -> None:
        evidence = load_evidence()
        validate_cloudx_source(evidence)
        result = evaluate(evidence)
        self.assertEqual(result["status"], "runtime-accepted")
        self.assertTrue(result["sourceReady"])
        self.assertTrue(all(result["sourceAcceptance"].values()))
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["automaticAction"])
        self.assertFalse(any(result["authorization"].values()))

    def test_runtime_acceptance_requires_all_three_independent_gates(self) -> None:
        evidence = load_evidence()
        evidence["runtimeAcceptance"] = {
            "signedArtifactPublished": True,
            "bridgeUnitInstalled": True,
            "rollbackRehearsed": True,
        }
        result = evaluate(evidence)
        self.assertEqual(result["status"], "runtime-accepted")
        self.assertEqual(result["blockers"], [])

    def test_source_readiness_requires_exact_parser_and_isolated_rollback(self) -> None:
        evidence = load_evidence()
        evidence["sourceAcceptance"]["isolatedSelectorRollback"] = False
        result = evaluate(evidence)
        self.assertEqual(result["status"], "source-incomplete")
        self.assertFalse(result["sourceReady"])

    def test_unknown_evidence_fields_are_rejected(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["phiPrevious"]["taskId"] = "task-1"
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "evidence.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(BridgeEvidenceRejected):
                load_evidence(path)

    def test_published_identity_is_strict_and_bound_to_the_tagged_source(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["cloudx"]["artifactRef"] = "refs/heads/release-artifacts/v9.9.9"
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "evidence.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(BridgeEvidenceRejected, "published bridge identity"):
                load_evidence(path)

        evidence = load_evidence()
        evidence["cloudx"]["sourceRef"] = "0" * 40
        with self.assertRaisesRegex(BridgeEvidenceRejected, "tag does not match"):
            validate_cloudx_source(evidence)

    def test_cli_accepts_current_runtime_evidence_and_strict_gate(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertEqual(output.getvalue().strip(), "legacy-health-bridge: runtime-accepted (0 blockers)")
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--require-runtime-accepted"]), 0)


if __name__ == "__main__":
    unittest.main()
