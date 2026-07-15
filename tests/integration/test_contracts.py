from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "shared/contracts"


class ContractTests(unittest.TestCase):
    def test_contract_documents_are_valid_json(self) -> None:
        schemas = list(CONTRACTS.glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 5)
        for path in schemas:
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(document["type"], "object")
                self.assertFalse(document.get("additionalProperties", True))

    def test_health_example_is_secret_free(self) -> None:
        document = json.loads((CONTRACTS / "examples/health.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "cloudx.health.v1")
        serialized = json.dumps(document).casefold()
        for forbidden in ("api_key", "token", "email", "auth_dir", "account_name"):
            self.assertNotIn(forbidden, serialized)
        counts = document["accountCounts"]
        self.assertEqual(counts["total"], counts["available"] + counts["limited"] + counts["unavailable"])

    def test_manifest_forbids_automatic_activation(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.release-manifest.v1.schema.json").read_text(encoding="utf-8"))
        automatic = schema["properties"]["activation"]["properties"]["automatic"]
        self.assertEqual(automatic, {"const": False})

    def test_release_trust_root_matches_both_endpoint_artifacts(self) -> None:
        expected = (ROOT / "release/allowed_signers").read_bytes()
        self.assertEqual((ROOT / "local/cloudx_local/data/allowed_signers").read_bytes(), expected)
        self.assertEqual((ROOT / "cloud/cloudx_cloud/data/allowed_signers").read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
