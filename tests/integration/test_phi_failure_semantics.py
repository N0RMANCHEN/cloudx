from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_phi_cloudx_failure_semantics import (  # noqa: E402
    DEFAULT_EVIDENCE,
    EvidenceRejected,
    evaluate,
    load_evidence,
    main,
    validate_contract_bindings,
    verify_phi_snapshot,
)


class PhiCloudxFailureSemanticsTests(unittest.TestCase):
    @staticmethod
    def _write(document: dict[str, object], directory: str) -> pathlib.Path:
        path = pathlib.Path(directory) / "evidence.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_current_evidence_accepts_every_scenario_without_coupling_future_roadmap_work(self) -> None:
        evidence = load_evidence()
        validate_contract_bindings(evidence)
        result = evaluate(evidence)
        self.assertTrue(result["cloudxContractMatrixReady"])
        self.assertEqual(result["scenarioCount"], 9)
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["crossRepositoryRuntimeAccepted"])
        self.assertTrue(result["phiRoadmapStatusesInformational"])
        self.assertEqual(result["blockers"], [])

    def test_roadmap_statuses_block_only_when_evidence_explicitly_makes_them_normative(self) -> None:
        evidence = load_evidence()
        evidence["acceptance"]["phiRoadmapStatusesInformational"] = False
        result = evaluate(
            evidence,
            release_result={"status": "compatible"},
            privileged_result={"status": "secure"},
            phi_snapshot_verified=True,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["blockers"],
            ["phi_int_p1_1_not_complete", "phi_ct_p1_3_not_complete"],
        )
        evidence["phiSnapshot"]["roadmapStatuses"] = {
            "INT/P1-1": "complete",
            "CT/P1-3": "complete",
        }
        result = evaluate(
            evidence,
            release_result={"status": "compatible"},
            privileged_result={"status": "secure"},
            phi_snapshot_verified=True,
        )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["crossRepositoryRuntimeAccepted"])

    def test_unknown_fields_and_weakened_scenarios_are_rejected(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["scenarios"][0]["taskId"] = "task-1"
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaises(EvidenceRejected):
                load_evidence(self._write(document, value))
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["scenarios"][0]["phiTruthMutationAllowed"] = True
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaises(EvidenceRejected):
                load_evidence(self._write(document, value))

    def test_optional_phi_snapshot_verifies_recorded_commit_independent_of_current_head(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value) / "phi"
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            payloads = {
                "docs/architecture/personal-agent-mesh.md": b"mesh\n",
                "docs/standards/product-acceptance.md": b"acceptance\n",
                "docs/roadmap/roadmap.json": json.dumps({
                    "items": [
                        {"id": "INT/P1-1", "status": "blocked"},
                        {"id": "CT/P1-3", "status": "blocked"},
                    ]
                }).encode("utf-8"),
            }
            for record in document["phiSnapshot"]["files"]:
                path = root / record["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payloads[record["path"]])
                record["sha256"] = hashlib.sha256(payloads[record["path"]]).hexdigest()
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Cloudx Test",
                    "-c", "user.email=cloudx-test.invalid", "commit", "-qm", "snapshot",
                ],
                check=True,
            )
            document["phiSnapshot"]["sourceRef"] = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout.strip()
            evidence_path = self._write(document, value)
            evidence = load_evidence(evidence_path)
            self.assertTrue(verify_phi_snapshot(evidence, root))
            (root / "docs/architecture/personal-agent-mesh.md").write_text(
                "changed\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Cloudx Test",
                    "-c", "user.email=cloudx-test.invalid", "commit", "-qm", "later work",
                ],
                check=True,
            )
            self.assertTrue(verify_phi_snapshot(evidence, root))
            evidence["phiSnapshot"]["files"][0]["sha256"] = "0" * 64
            with self.assertRaises(EvidenceRejected):
                verify_phi_snapshot(evidence, root)

    def test_fixture_and_result_remain_secret_free(self) -> None:
        fixture = DEFAULT_EVIDENCE.read_text(encoding="utf-8")
        result = json.dumps(evaluate(load_evidence()), sort_keys=True)
        for forbidden in ("/Users/", "/home/", "/etc/", "@", "39.96."):
            self.assertNotIn(forbidden, fixture)
            self.assertNotIn(forbidden, result)

    def test_cli_reports_strict_cross_repository_acceptance(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertEqual(
            output.getvalue().strip(),
            "phi-failure-semantics: accepted (0 blockers; 9 scenarios; phi-snapshot=recorded)",
        )
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--require-accepted"]), 0)


if __name__ == "__main__":
    unittest.main()
