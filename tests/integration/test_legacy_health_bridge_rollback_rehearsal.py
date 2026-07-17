from __future__ import annotations

import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rehearse_legacy_health_bridge_rollback import main, rehearse  # noqa: E402


class LegacyHealthBridgeRollbackRehearsalTests(unittest.TestCase):
    def test_fixed_artifact_survives_isolated_selector_rollback_round_trip(self) -> None:
        result = rehearse()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["selectors"], [
            {"current": "0.1.13", "previous": "0.1.12"},
            {"current": "0.1.12", "previous": "0.1.13"},
            {"current": "0.1.13", "previous": "0.1.12"},
        ])
        self.assertTrue(result["rollbackRoundTrip"])
        self.assertTrue(result["fixedArtifactIndependent"])
        self.assertTrue(result["outputByteStable"])
        self.assertFalse(result["phiPreviousVerified"])
        self.assertFalse(result["automaticAction"])
        self.assertFalse(any(result["authorization"].values()))
        self.assertNotIn("/tmp", json.dumps(result))
        self.assertNotIn("/Users", json.dumps(result))

    def test_cli_reports_the_isolated_rehearsal(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["schema"], "cloudx.legacy-health-bridge-rollback-rehearsal.v1")


if __name__ == "__main__":
    unittest.main()
