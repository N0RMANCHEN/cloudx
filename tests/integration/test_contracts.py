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

    def test_http_importer_stop_gate_is_secret_free_and_non_authorizing(self) -> None:
        evidence = json.loads(
            (CONTRACTS / "examples/http-importer-stop-gate-evidence.json").read_text(encoding="utf-8")
        )
        decision = json.loads(
            (CONTRACTS / "examples/http-importer-stop-gate.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["schema"], "cloudx.http-importer-stop-gate-evidence.v1")
        self.assertEqual(decision["schema"], "cloudx.http-importer-stop-gate.v1")
        self.assertFalse(decision["automaticAction"])
        self.assertFalse(decision["authorization"]["serviceStop"])
        serialized = json.dumps(decision).casefold()
        for forbidden in ("token", "email", "account", "server-admin", "api_key"):
            self.assertNotIn(forbidden, serialized)

    def test_phi_mesh_compatibility_profile_references_existing_contracts(self) -> None:
        profile = json.loads(
            (CONTRACTS / "examples/phi-mesh-compatibility-profile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["schema"], "cloudx.phi-mesh-compatibility-profile.v1")
        self.assertEqual(profile["topology"]["consumer"], "phi_cloud")
        self.assertFalse(profile["topology"]["directDeviceAccess"])
        contracts = profile["contracts"]
        self.assertEqual(contracts["handshake"]["schema"], "cloudx.handshake.v1")
        self.assertEqual(contracts["health"]["schema"], "cloudx.health.v1")
        self.assertEqual(contracts["gateway"]["configurationSchema"], "cloudx.client-config.v1")
        self.assertEqual(contracts["credential"]["configurationSchema"], "cloudx.client-config.v1")
        self.assertEqual(contracts["release"]["manifestSchema"], "cloudx.release-manifest.v1")
        self.assertEqual(contracts["rollback"]["resultSchema"], "cloudx.release-rollback.v1")
        handshake = json.loads((CONTRACTS / "examples/handshake.json").read_text(encoding="utf-8"))
        self.assertTrue(set(contracts["handshake"]["requiredCapabilities"]).issubset(handshake["capabilities"]))
        self.assertFalse(profile["compatibility"]["synchronizedDeploymentRequired"])
        self.assertFalse(profile["authorization"]["profileGrantsReleaseMutation"])

    def test_phi_cloud_consumer_credential_is_scoped_and_rotatable(self) -> None:
        policy = json.loads(
            (CONTRACTS / "examples/phi-cloud-consumer-credential.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["schema"], "cloudx.phi-cloud-consumer-credential.v1")
        self.assertEqual(policy["scope"]["allowedOperations"], ["gateway_inference"])
        denied = set(policy["scope"]["deniedOperations"])
        self.assertTrue({
            "account_import",
            "gateway_configuration_mutation",
            "release_activation",
            "device_identity_assertion",
        }.issubset(denied))
        self.assertFalse(policy["representation"]["device"])
        self.assertFalse(policy["enforcement"]["sshLogin"])
        self.assertFalse(policy["enforcement"]["cloudxRemote"])
        self.assertNotEqual(policy["storage"]["secretPath"], "/etc/cloudx/client-credential")
        self.assertTrue(policy["lifecycle"]["revocable"])
        self.assertTrue(policy["lifecycle"]["rotatable"])
        self.assertEqual(policy["lifecycle"]["rotationOrder"][-1], "revoke_previous_gateway_key")
        self.assertFalse(policy["authorization"]["serviceRestartAuthorized"])
        serialized = json.dumps(policy).casefold()
        for forbidden in ("api_key", "apikey", "bearer ", "token-"):
            self.assertNotIn(forbidden, serialized)

    def test_release_trust_root_matches_both_endpoint_artifacts(self) -> None:
        expected = (ROOT / "release/allowed_signers").read_bytes()
        self.assertEqual((ROOT / "local/cloudx_local/data/allowed_signers").read_bytes(), expected)
        self.assertEqual((ROOT / "cloud/cloudx_cloud/data/allowed_signers").read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
