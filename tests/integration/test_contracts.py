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

    def test_capacity_example_is_aggregate_and_distinguishes_all_states(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.capacity.v1.schema.json").read_text(encoding="utf-8"))
        document = json.loads((CONTRACTS / "examples/capacity.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "cloudx.capacity.v1")
        self.assertEqual(document["state"], "healthy_capacity")
        states = set(schema["properties"]["state"]["enum"])
        self.assertEqual(states, {
            "healthy_capacity",
            "exhausted_capacity",
            "unknown_observation",
            "stale_contract",
            "probe_failure",
            "incompatible_producer",
        })
        serialized = json.dumps(document).casefold()
        for forbidden in ("api_key", "token", "email", "account_name", "deviceid", "taskid"):
            self.assertNotIn(forbidden, serialized)

    def test_api_diagnosis_is_secret_free_and_distinguishes_user_causes(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.api-diagnosis.v1.schema.json").read_text(encoding="utf-8"))
        document = json.loads((CONTRACTS / "examples/api-diagnosis.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "cloudx.api-diagnosis.v1")
        causes = set(schema["properties"]["cause"]["enum"])
        self.assertTrue({
            "account_deactivated",
            "quota_exhausted",
            "rate_limited",
            "login_required",
            "access_denied",
            "no_usable_accounts",
        }.issubset(causes))
        self.assertEqual(document["cause"], "quota_exhausted")
        self.assertEqual(document["evidence"]["maskedBy"], "no_usable_accounts")
        serialized = json.dumps(document).casefold()
        for forbidden in ("api_key", "token", "email", "account_name", "message"):
            self.assertNotIn(forbidden, serialized)

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

    def test_phi_cloud_consumer_traffic_is_bounded_without_control_plane_fields(self) -> None:
        policy = json.loads(
            (CONTRACTS / "examples/phi-cloud-consumer-traffic-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["schema"], "cloudx.phi-cloud-consumer-traffic-policy.v1")
        limits = policy["limits"]
        self.assertEqual(limits["maxInFlight"], 4)
        self.assertEqual(limits["maxQueueDepth"], 16)
        self.assertEqual(policy["admission"]["unit"], "logical_gateway_request")
        self.assertEqual(limits["sustainedAttemptsPerMinute"], 30)
        self.assertTrue(limits["everyAttemptConsumesRateBudget"])
        self.assertTrue(limits["retryKeepsInFlightSlot"])
        self.assertEqual(policy["queue"]["fullBehavior"], "reject_without_gateway_attempt")
        self.assertLess(policy["timeouts"]["connectMilliseconds"], policy["timeouts"]["overallMilliseconds"])
        self.assertEqual(policy["retry"]["maxAttempts"], 3)
        self.assertTrue(policy["retry"]["neverRetryAfterResponseBytes"])
        self.assertFalse(policy["authorization"]["policyInstallsEnforcement"])
        serialized = json.dumps(policy).casefold()
        for forbidden in ("task", "device", "lease", "approval", "artifact", "workspace"):
            self.assertNotIn(forbidden, serialized)

    def test_release_trust_root_matches_both_endpoint_artifacts(self) -> None:
        expected = (ROOT / "release/allowed_signers").read_bytes()
        self.assertEqual((ROOT / "local/cloudx_local/data/allowed_signers").read_bytes(), expected)
        self.assertEqual((ROOT / "cloud/cloudx_cloud/data/allowed_signers").read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
