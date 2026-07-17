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

from check_phi_cloudx_privileged_boundary import (  # noqa: E402
    DEFAULT_EVIDENCE,
    EvidenceRejected,
    evaluate,
    load_evidence,
    main,
)


class PhiCloudxPrivilegedBoundaryTests(unittest.TestCase):
    @staticmethod
    def _surface(result: dict[str, object], name: str) -> dict[str, object]:
        return next(item for item in result["surfaces"] if item["name"] == name)

    @staticmethod
    def _write(document: dict[str, object], directory: str) -> pathlib.Path:
        path = pathlib.Path(directory) / "evidence.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_current_evidence_truthfully_records_agent_root_reachability(self) -> None:
        result = evaluate(load_evidence())
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["credentialScoped"])
        self.assertEqual(len(result["blockers"]), 9)
        interactive = self._surface(result, "interactive_cli")
        mail = self._surface(result, "mail_command")
        orchestrator = self._surface(result, "orchestrator")
        self.assertTrue(interactive["elevationReachable"])
        self.assertTrue(mail["elevationReachable"])
        self.assertFalse(orchestrator["elevationReachable"])
        self.assertEqual(orchestrator["blockers"], [])
        self.assertTrue(all(interactive["effectiveCapabilities"].values()))
        self.assertTrue(all(mail["effectiveCapabilities"].values()))

    def test_scoped_credential_and_no_new_privileges_make_snapshot_secure(self) -> None:
        evidence = load_evidence()
        evidence["consumerCredential"] = {
            "class": "scoped_phi_consumer",
            "privilegeElevation": False,
        }
        for surface in evidence["agentSurfaces"]:
            surface["noNewPrivileges"] = True
        result = evaluate(evidence)
        self.assertEqual(result["status"], "secure")
        self.assertEqual(result["blockers"], [])

    def test_direct_agent_capability_blocks_even_when_elevation_is_disabled(self) -> None:
        evidence = load_evidence()
        evidence["consumerCredential"] = {
            "class": "scoped_phi_consumer",
            "privilegeElevation": False,
        }
        for surface in evidence["agentSurfaces"]:
            surface["noNewPrivileges"] = True
        orchestrator = next(
            item for item in evidence["agentSurfaces"] if item["name"] == "orchestrator"
        )
        orchestrator["directCapabilities"]["importInvoke"] = True
        result = evaluate(evidence)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blockers"], ["orchestrator_import_invoke"])

    def test_unknown_fields_and_incomplete_surface_inventory_are_rejected(self) -> None:
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["agentSurfaces"][0]["taskId"] = "task-1"
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaises(EvidenceRejected):
                load_evidence(self._write(document, value))
        document = json.loads(DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        document["agentSurfaces"].pop()
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaises(EvidenceRejected):
                load_evidence(self._write(document, value))

    def test_fixture_and_result_remain_secret_free(self) -> None:
        text = DEFAULT_EVIDENCE.read_text(encoding="utf-8")
        for forbidden in ("/home/", "/etc/", "/var/", "@", "hirohi", "39.96."):
            self.assertNotIn(forbidden, text)
        result = json.dumps(evaluate(load_evidence()), sort_keys=True)
        for forbidden in ("/home/", "/etc/", "/var/", "@", "hirohi", "39.96."):
            self.assertNotIn(forbidden, result)

    def test_cli_accepts_valid_blocking_evidence_but_can_require_security(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertEqual(
            output.getvalue().strip(),
            "phi-privileged-boundary: blocked (9 blockers)",
        )
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--require-secure"]), 2)


if __name__ == "__main__":
    unittest.main()
