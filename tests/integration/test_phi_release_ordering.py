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

from check_phi_cloudx_release_ordering import (  # noqa: E402
    DEFAULT_EVIDENCE,
    EvidenceRejected,
    evaluate,
    load_evidence,
    main,
)


class PhiCloudxReleaseOrderingTests(unittest.TestCase):
    @staticmethod
    def _by_name(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        return {str(item["name"]): item for item in items}

    def test_current_evidence_truthfully_records_the_unaccepted_legacy_bridge(self) -> None:
        evidence = load_evidence()
        result = evaluate(evidence)
        self.assertEqual(result["status"], "blocked")
        matrix = {
            (item["cloudxRelease"], item["phiRelease"]): item
            for item in result["matrix"]
        }
        self.assertTrue(matrix[("current", "current")]["compatible"])
        self.assertEqual(matrix[("current", "current")]["healthPath"], "direct")
        self.assertTrue(matrix[("previous", "current")]["compatible"])
        self.assertFalse(matrix[("current", "previous")]["compatible"])
        self.assertEqual(matrix[("current", "previous")]["healthPath"], "legacy_bridge_pending")
        self.assertEqual(
            matrix[("current", "previous")]["reasons"],
            ["legacy_bridge_not_runtime_accepted"],
        )
        self.assertEqual(result["legacyBridgeStatus"], "source-ready")
        self.assertEqual(len(result["legacyBridgeBlockers"]), 3)
        orders = self._by_name(result["orders"])
        self.assertTrue(orders["cloudx_rollback"]["compatible"])
        self.assertFalse(orders["phi_rollback"]["compatible"])
        self.assertFalse(orders["cloudx_first_upgrade"]["compatible"])
        self.assertFalse(orders["phi_first_upgrade"]["compatible"])

    def test_formal_phi_n_minus_one_would_make_all_release_orders_compatible(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["phi"]["previous"]["healthContract"] = "schema=cloudx.health.v1"
        document["expectedStatus"] = "compatible"
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "evidence.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = evaluate(load_evidence(path))
        self.assertEqual(result["status"], "compatible")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(item["compatible"] for item in result["orders"]))

    def test_runtime_accepted_legacy_bridge_would_make_all_release_orders_compatible(self) -> None:
        evidence = load_evidence()
        from check_phi_cloudx_release_ordering import _bridge_evidence

        bridge = _bridge_evidence(evidence)
        bridge["runtimeAcceptance"] = {
            "signedArtifactPublished": True,
            "bridgeUnitInstalled": True,
            "rollbackRehearsed": True,
        }
        result = evaluate(evidence, bridge)
        self.assertEqual(result["status"], "compatible")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(item["compatible"] for item in result["orders"]))
        bridged = [item for item in result["matrix"] if item["phiRelease"] == "previous"]
        self.assertTrue(all(item["healthPath"] == "legacy_bridge" for item in bridged))

    def test_protocol_range_mismatch_is_distinct_from_contract_mismatch(self) -> None:
        evidence = load_evidence()
        evidence["phi"]["current"]["consumerProtocol"] = {"min": 2, "max": 2}
        result = evaluate(evidence)
        current_pair = next(
            item
            for item in result["matrix"]
            if item["cloudxRelease"] == "current" and item["phiRelease"] == "current"
        )
        self.assertEqual(current_pair["reasons"], ["protocol_range_mismatch"])

    def test_unknown_evidence_fields_are_rejected(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["phi"]["current"]["taskId"] = "task-1"
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "evidence.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(EvidenceRejected):
                load_evidence(path)

    def test_cli_accepts_valid_blocking_evidence_but_can_require_compatibility(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertEqual(output.getvalue().strip(), "release-ordering: blocked (2 blockers)")
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--require-compatible"]), 2)


if __name__ == "__main__":
    unittest.main()
