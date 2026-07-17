from __future__ import annotations

import copy
import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import http_importer_gate  # noqa: E402
from cloudx_cloud.cli import main  # noqa: E402


EVIDENCE_PATH = ROOT / "shared/contracts/examples/http-importer-stop-gate-evidence.json"
DECISION_PATH = ROOT / "shared/contracts/examples/http-importer-stop-gate.json"
BLOCKED_EVIDENCE_PATH = ROOT / "docs/archive/2026-07-16-http-importer-stop-gate-evidence.json"
BLOCKED_DECISION_PATH = ROOT / "docs/archive/2026-07-16-http-importer-stop-gate-decision.json"
READY_EVIDENCE_PATH = ROOT / "docs/archive/2026-07-17-http-importer-stop-gate-evidence.json"
READY_DECISION_PATH = ROOT / "docs/archive/2026-07-17-http-importer-stop-gate-decision.json"


class HttpImporterStopGateTests(unittest.TestCase):
    def evidence(self) -> dict:
        return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def encode(document: dict) -> bytes:
        return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    def run_cli(self, raw: bytes) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        stdin = SimpleNamespace(buffer=io.BytesIO(raw))
        with mock.patch("cloudx_cloud.cli.sys.stdin", stdin), redirect_stdout(output), redirect_stderr(error):
            code = main(["http-importer-stop-gate"])
        return code, output.getvalue(), error.getvalue()

    def test_ready_example_is_bound_secret_free_and_non_authorizing(self) -> None:
        raw = self.encode(self.evidence())
        document = http_importer_gate.evaluate(raw)
        expected = json.loads(DECISION_PATH.read_text(encoding="utf-8"))

        self.assertEqual(document, expected)
        self.assertTrue(document["preconditionsSatisfied"])
        self.assertFalse(document["automaticAction"])
        self.assertFalse(document["authorization"]["serviceStop"])
        serialized = json.dumps(document).casefold()
        for forbidden in ("server-admin", "api_key", "bearer", "account", "01234567"):
            self.assertNotIn(forbidden, serialized)

        code, output, error = self.run_cli(raw)
        self.assertEqual(code, 0, msg=error)
        self.assertEqual(json.loads(output), document)

    def test_blockers_are_deterministic_and_cli_returns_two(self) -> None:
        evidence = self.evidence()
        evidence["listener"]["establishedConnections"] = 1
        evidence["traffic"]["unattributedRequests"] = 2
        evidence["transactions"]["lockHolders"] = 1
        evidence["adapter"]["signedArtifactVerified"] = False
        evidence["consumers"]["legacyHealthReaders"] = 1
        evidence["dependencies"]["requiredUnits"] = 1
        evidence["rollback"]["unitSnapshot"] = False

        raw = self.encode(evidence)
        document = http_importer_gate.evaluate(raw)
        self.assertFalse(document["preconditionsSatisfied"])
        self.assertEqual(document["status"], "blocked")
        self.assertEqual(
            [item["code"] for item in document["blockers"]],
            [
                "established_connections",
                "unattributed_requests",
                "import_lock_held",
                "adapter_unsigned",
                "legacy_health_readers",
                "required_units",
                "rollback_unit_missing",
            ],
        )

        code, output, error = self.run_cli(raw)
        self.assertEqual(code, 2, msg=error)
        self.assertEqual(json.loads(output), document)

    def test_equal_request_and_capture_time_needs_no_fixed_wait(self) -> None:
        evidence = self.evidence()
        evidence["traffic"]["lastRequestAt"] = evidence["capturedAt"]
        document = http_importer_gate.evaluate(self.encode(evidence))
        self.assertTrue(document["preconditionsSatisfied"])

    def test_rejects_unknown_duplicate_and_oversized_evidence(self) -> None:
        evidence = self.evidence()
        evidence["credential"] = "must-not-be-accepted"
        with self.assertRaisesRegex(http_importer_gate.EvidenceRejected, "missing or unknown"):
            http_importer_gate.evaluate(self.encode(evidence))
        with self.assertRaisesRegex(http_importer_gate.EvidenceRejected, "duplicate"):
            http_importer_gate.evaluate(b'{"schema":"one","schema":"two"}')
        with self.assertRaisesRegex(http_importer_gate.EvidenceRejected, "64 KiB"):
            http_importer_gate.evaluate(b" " * (http_importer_gate.MAX_EVIDENCE_BYTES + 1))

    def test_rejects_invalid_types_hashes_and_timestamps(self) -> None:
        cases = []
        active_number = self.evidence()
        active_number["service"]["active"] = 1
        cases.append(active_number)
        invalid_hash = self.evidence()
        invalid_hash["adapter"]["sha256"] = "A" * 64
        cases.append(invalid_hash)
        future_request = self.evidence()
        future_request["traffic"]["lastRequestAt"] = "2026-07-16T05:38:36Z"
        cases.append(future_request)

        for evidence in cases:
            with self.subTest(evidence=evidence):
                with self.assertRaises(http_importer_gate.EvidenceRejected):
                    http_importer_gate.evaluate(self.encode(evidence))

    def test_invalid_cli_input_never_echoes_unknown_content(self) -> None:
        evidence = self.evidence()
        evidence["credential"] = "sensitive-value"
        code, output, error = self.run_cli(self.encode(evidence))
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("missing or unknown fields", error)
        self.assertNotIn("credential", error)
        self.assertNotIn("sensitive-value", error)

    def test_evidence_digest_changes_with_gate_state(self) -> None:
        accepted = http_importer_gate.evaluate(self.encode(self.evidence()))
        blocked_evidence = copy.deepcopy(self.evidence())
        blocked_evidence["traffic"]["activeHttpCallers"] = 1
        blocked = http_importer_gate.evaluate(self.encode(blocked_evidence))
        self.assertNotEqual(accepted["evidenceDigest"], blocked["evidenceDigest"])

    def test_archived_blocked_snapshot_matches_machine_decision(self) -> None:
        decision = http_importer_gate.evaluate(BLOCKED_EVIDENCE_PATH.read_bytes())
        expected = json.loads(BLOCKED_DECISION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(decision, expected)
        self.assertEqual(
            [item["code"] for item in decision["blockers"]],
            ["rollback_runtime_missing", "rollback_failure_receipts_missing"],
        )
        self.assertFalse(decision["authorization"]["serviceStop"])

    def test_archived_ready_snapshot_remains_non_authorizing(self) -> None:
        decision = http_importer_gate.evaluate(READY_EVIDENCE_PATH.read_bytes())
        expected = json.loads(READY_DECISION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(decision, expected)
        self.assertEqual(decision["status"], "preconditions-satisfied")
        self.assertTrue(decision["preconditionsSatisfied"])
        self.assertEqual(decision["blockers"], [])
        self.assertFalse(decision["automaticAction"])
        self.assertFalse(decision["authorization"]["serviceStop"])


if __name__ == "__main__":
    unittest.main()
