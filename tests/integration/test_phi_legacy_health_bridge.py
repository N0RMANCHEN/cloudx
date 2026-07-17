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
    def test_current_evidence_is_source_ready_and_non_authorizing(self) -> None:
        evidence = load_evidence()
        validate_cloudx_source(evidence)
        result = evaluate(evidence)
        self.assertEqual(result["status"], "source-ready")
        self.assertTrue(result["sourceReady"])
        self.assertTrue(all(result["sourceAcceptance"].values()))
        self.assertEqual(result["blockers"], [
            "signed_artifact_not_published",
            "bridge_unit_not_installed",
            "rollback_not_rehearsed",
        ])
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

    def test_cli_accepts_source_readiness_but_can_require_runtime_acceptance(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertEqual(output.getvalue().strip(), "legacy-health-bridge: source-ready (3 blockers)")
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--require-runtime-accepted"]), 2)


if __name__ == "__main__":
    unittest.main()
