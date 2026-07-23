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

    def test_legacy_health_bridge_example_is_secret_free_and_fail_closed(self) -> None:
        document = json.loads((CONTRACTS / "examples/legacy-health.json").read_text(encoding="utf-8"))
        self.assertEqual(document["contract"], "cloudx.health")
        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(document["gateway"]["processState"], "unknown")
        self.assertEqual(document["imports"]["state"], "unknown")
        self.assertEqual(document["imports"]["processState"], "unknown")
        serialized = json.dumps(document).casefold()
        for forbidden in ("api_key", "token", "email", "account_name", "taskid", "deviceid"):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_health_bridge_unit_transaction_is_non_activating(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-unit-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-unit-install.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.legacy-health-bridge-unit-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.legacy-health-bridge-unit-install.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertFalse(plan["canaryStartRequired"])
        self.assertFalse(plan["serviceStartRequired"])
        self.assertFalse(plan["timerEnableRequired"])
        self.assertFalse(receipt["serviceStarted"])
        self.assertFalse(receipt["canaryStarted"])
        self.assertFalse(receipt["timerEnabled"])
        self.assertFalse(receipt["legacyServiceStopped"])
        self.assertFalse(receipt["legacyTimerDisabled"])
        self.assertFalse(receipt["releaseActivated"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "token-", "secret-value"):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_health_bridge_artifact_stage_is_pinned_and_selector_inert(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-artifact-stage-plan.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-artifact-stage.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(plan["releaseVersion"], "0.1.15")
        self.assertEqual(plan["releaseRefCommit"], "332cb865a97d654efca4b4321b90cdc140e57e64")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(receipt["selectorsAfter"], receipt["selectorsBefore"])
        self.assertFalse(receipt["releaseActivated"])
        self.assertFalse(receipt["serviceRestarted"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "token-", "secret-value"):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_health_bridge_canary_is_isolated_and_non_authorizing(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-canary-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-canary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.legacy-health-bridge-canary-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.legacy-health-bridge-canary.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertTrue(receipt["canaryStarted"])
        self.assertTrue(receipt["temporaryOutputRemoved"])
        self.assertFalse(receipt["primaryServiceStarted"])
        self.assertFalse(receipt["primaryTimerEnabled"])
        self.assertFalse(receipt["legacyOutputMutated"])
        self.assertFalse(receipt["releaseActivated"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "token-", "secret-value"):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_health_bridge_cutover_is_overlap_first_and_non_authorizing(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-cutover-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-health-bridge-cutover.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.legacy-health-bridge-cutover-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.legacy-health-bridge-cutover.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(plan["communicationGapAllowed"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertFalse(receipt["communicationGapObserved"])
        self.assertTrue(receipt["rollbackRehearsed"])
        self.assertTrue(receipt["restorationAccepted"])
        self.assertTrue(receipt["primaryTimerEnabled"])
        self.assertTrue(receipt["legacyTimerDisabled"])
        self.assertTrue(receipt["legacyServiceRetained"])
        self.assertFalse(receipt["phiServiceRestarted"])
        self.assertFalse(receipt["releaseActivated"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "token-", "secret-value"):
            self.assertNotIn(forbidden, serialized)

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

    def test_scoped_key_revocation_contract_is_non_authorizing_and_secret_free(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/scoped-key-revocation-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/scoped-key-revocation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.scoped-key-revocation-plan.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(receipt["newCredentialHttpStatus"], 200)
        self.assertEqual(receipt["oldCredentialHttpStatus"], 401)
        self.assertTrue(receipt["previousCredentialRevoked"])
        self.assertTrue(receipt["otherGatewayKeysUnchanged"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "cloudx-old", "cloudx-new", "secret-value"):
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

    def test_local_cpa_import_contract_is_explicit_and_does_not_manage_the_external_service(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.local-cpa-import.v1.schema.json").read_text(encoding="utf-8"))
        document = json.loads((CONTRACTS / "examples/local-cpa-import.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "cloudx.local-cpa-import.v1")
        self.assertEqual(document["destination"], "local_cpa")
        self.assertEqual(document["status"], "accepted")
        self.assertFalse(document["externalService"]["managed"])
        self.assertFalse(document["externalService"]["restarted"])
        self.assertEqual(schema["properties"]["status"]["enum"], ["accepted", "preview", "rejected"])
        serialized = json.dumps(document).casefold()
        for forbidden in ("access_token", "refresh_token", "id_token", "api_key", "email"):
            self.assertNotIn(forbidden, serialized)

    def test_local_cpa_capability_contract_binds_one_exact_runtime(self) -> None:
        document = json.loads(
            (CONTRACTS / "examples/local-cpa-capabilities.json").read_text(encoding="utf-8")
        )
        self.assertEqual(document["schema"], "cloudx.local-cpa-capabilities.v1")
        self.assertEqual(len(document["binarySha256"]), 64)
        self.assertEqual(document["capabilities"], ["codex-agent-identity-v1"])
        serialized = json.dumps(document).casefold()
        for forbidden in ("token", "private_key", "runtime_id", "task_id", "email"):
            self.assertNotIn(forbidden, serialized)

    def test_upgrade_contract_is_explicit_endpoint_only_and_secret_free(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.upgrade.v1.schema.json").read_text(encoding="utf-8"))
        document = json.loads((CONTRACTS / "examples/upgrade.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "cloudx.upgrade.v1")
        self.assertEqual(document["status"], "upgraded")
        self.assertEqual(document["endpoint"], "local")
        self.assertEqual(document["artifactRef"], "refs/heads/release-artifacts/v0.1.26")
        self.assertEqual(len(document["manifestSha256"]), 64)
        self.assertTrue(document["signedIndexVerified"])
        self.assertEqual(document["verificationScope"], "complete-release-chain")
        self.assertTrue(document["explicitInvocation"])
        self.assertFalse(document["backgroundActivation"])
        self.assertFalse(document["serviceRestarted"])
        self.assertFalse(document["externalCpaManaged"])
        self.assertFalse(document["officialCodexReplaced"])
        self.assertFalse(schema.get("additionalProperties", True))
        serialized = json.dumps(document).casefold()
        for forbidden in ("api_key", "token", "credential", "private_key", "email"):
            self.assertNotIn(forbidden, serialized)

    def test_cpa_sweep_contracts_are_identity_free_and_non_authorizing(self) -> None:
        trigger = json.loads((CONTRACTS / "examples/cpa-sweep-trigger.json").read_text(encoding="utf-8"))
        observation = json.loads(
            (CONTRACTS / "examples/cpa-pool-observation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(trigger, {
            "schema": "cloudx.cpa-sweep-trigger.v1",
            "reason": "auth_unavailable",
            "observedAt": "2026-07-18T12:30:00Z",
        })
        self.assertEqual(observation["schema"], "cloudx.cpa-pool-observation.v1")
        self.assertIn(observation["state"], {"available", "unavailable"})
        serialized = json.dumps({"trigger": trigger, "observation": observation}).casefold()
        for forbidden in (
            "token",
            "email",
            "authfile",
            "authsha256",
            "account",
            "provider",
            "model",
            "archive",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_manifest_forbids_automatic_activation(self) -> None:
        schema = json.loads((CONTRACTS / "cloudx.release-manifest.v1.schema.json").read_text(encoding="utf-8"))
        automatic = schema["properties"]["activation"]["properties"]["automatic"]
        self.assertEqual(automatic, {"const": False})

    def test_release_workflow_key_transaction_is_non_publishing_and_secret_free(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/release-workflow-key-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/release-workflow-key.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.release-workflow-key-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.release-workflow-key.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(plan["environment"], "release")
        self.assertTrue(receipt["environmentSecretUpdated"])
        self.assertTrue(receipt["workflowDispatched"])
        self.assertTrue(receipt["signedReleaseVerified"])
        self.assertTrue(receipt["releaseRefsUnchanged"])
        self.assertFalse(receipt["tagCreated"])
        self.assertFalse(receipt["artifactRefPublished"])
        self.assertFalse(receipt["stableMoved"])
        self.assertFalse(receipt["endpointStaged"])
        self.assertFalse(receipt["endpointActivated"])
        self.assertFalse(receipt["serviceRestarted"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in (
            "begin openssh private key",
            "private-key",
            "/users/",
            "gh_token",
            "github_token",
        ):
            self.assertNotIn(forbidden, serialized)

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

    def test_http_importer_stop_transaction_is_explicit_and_retains_rollback(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/http-importer-stop-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/http-importer-stop.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.http-importer-stop-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.http-importer-stop.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertIn("ssh_import_dry_run", plan["canaries"])
        self.assertFalse(receipt["serviceActive"])
        self.assertFalse(receipt["serviceEnabled"])
        self.assertTrue(receipt["listenerClosed"])
        self.assertTrue(receipt["rollbackSnapshotRetained"])
        self.assertFalse(receipt["runtimeRemoved"])
        self.assertFalse(receipt["unitRemoved"])
        self.assertFalse(receipt["tokenRemoved"])
        self.assertFalse(receipt["failureReceiptsRemoved"])
        self.assertFalse(receipt["gatewayRestarted"])
        self.assertFalse(receipt["phiServiceRestarted"])
        self.assertFalse(receipt["releaseActivated"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "access_token", "refresh_token", "secret-value"):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_local_removal_is_quarantine_first_and_preserves_owned_boundaries(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-local-removal-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-local-removal.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.legacy-local-removal-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.legacy-local-removal.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(
            plan["targets"],
            ["legacyRuntime", "legacyLauncher", "recoveryEntrypoint"],
        )
        self.assertTrue(receipt["cloudxEntrypointsUnchanged"])
        self.assertTrue(receipt["shellHookUnchanged"])
        self.assertTrue(receipt["externalLocalCpaUnchanged"])
        self.assertTrue(receipt["accountProfilesRetained"])
        self.assertTrue(receipt["privateRecoveryBundleRetained"])
        self.assertFalse(receipt["processTerminated"])
        self.assertFalse(receipt["serviceRestarted"])
        self.assertTrue(receipt["quarantineRetained"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in (
            "api_key",
            "bearer ",
            "access_token",
            "refresh_token",
            "email",
            "/users/",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_stale_local_exec_retirement_is_digest_bound_and_cpa_inert(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/stale-local-codexx-exec-plan.json").read_text(
                encoding="utf-8"
            )
        )
        decision = json.loads(
            (CONTRACTS / "examples/stale-local-codexx-exec-decision.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (CONTRACTS / "examples/stale-local-codexx-exec-retirement.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertTrue(decision["irreversibleProcessTerminationRequired"])
        self.assertEqual(decision["targetCount"], len(decision["targetPids"]))
        self.assertEqual(decision["targetCount"], len(decision["childPids"]))
        self.assertEqual(receipt["signal"], "SIGTERM")
        self.assertFalse(receipt["sigkillSent"])
        self.assertFalse(receipt["serviceRestarted"])
        self.assertFalse(receipt["localCpaChanged"])

    def test_legacy_control_migration_is_idle_recoverable_and_cpa_inert(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-local-control-migration-plan.json").read_text(
                encoding="utf-8"
            )
        )
        decision = json.loads(
            (CONTRACTS / "examples/legacy-local-control-migration-decision.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-local-control-migration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(decision["activeConnections"], 0)
        self.assertGreaterEqual(decision["minimumIdleSeconds"], 30 * 24 * 60 * 60)
        self.assertTrue(receipt["recoveryScriptPrepared"])
        self.assertTrue(receipt["controlServiceRestarted"])
        self.assertFalse(receipt["legacyPackageQuarantined"])
        self.assertFalse(receipt["localCpaChanged"])
        self.assertFalse(receipt["accountMutation"])

    def test_cloud_legacy_runtime_quarantine_is_reversible_and_service_inert(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/cloud-legacy-runtime-quarantine-plan.json").read_text(
                encoding="utf-8"
            )
        )
        decision = json.loads(
            (CONTRACTS / "examples/cloud-legacy-runtime-quarantine-decision.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (CONTRACTS / "examples/cloud-legacy-runtime-quarantine.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(decision["liveProcessReferences"], 0)
        self.assertTrue(decision["rollbackSnapshotVerified"])
        self.assertTrue(decision["rollbackArchiveContainsTarget"])
        self.assertTrue(receipt["recoveryScriptPrepared"])
        self.assertTrue(receipt["httpImporterRollbackSnapshotRetained"])
        self.assertFalse(receipt["runtimeLive"])
        self.assertFalse(receipt["runtimeDeleted"])
        self.assertFalse(receipt["serviceRestarted"])
        self.assertFalse(receipt["daemonReloaded"])
        self.assertFalse(receipt["credentialMutation"])
        self.assertFalse(receipt["phiServiceRestarted"])

    def test_legacy_control_retirement_is_recoverable_and_cpa_inert(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/legacy-local-control-retirement-plan.json").read_text(
                encoding="utf-8"
            )
        )
        decision = json.loads(
            (CONTRACTS / "examples/legacy-local-control-retirement-decision.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (CONTRACTS / "examples/legacy-local-control-retirement.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertEqual(decision["activeConnections"], 0)
        self.assertTrue(decision["serviceStopRequired"])
        self.assertTrue(receipt["controlServiceStopped"])
        self.assertTrue(receipt["portClosed"])
        self.assertFalse(receipt["launchAgentLoaded"])
        self.assertFalse(receipt["launchAgentLive"])
        self.assertFalse(receipt["controlServiceRestarted"])
        self.assertFalse(receipt["sigkillSent"])
        self.assertFalse(receipt["localCpaChanged"])
        self.assertFalse(receipt["codexProcessTerminated"])

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
        self.assertEqual(contracts["legacyHealthBridge"]["contract"], "cloudx.health")
        self.assertTrue(contracts["legacyHealthBridge"]["migrationOnly"])
        self.assertFalse(contracts["legacyHealthBridge"]["automaticInstallation"])
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

    def test_phi_consumer_key_transaction_is_secret_free_and_non_authorizing(self) -> None:
        plan = json.loads(
            (CONTRACTS / "examples/phi-consumer-key-plan.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (CONTRACTS / "examples/phi-consumer-key-install.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema"], "cloudx.phi-consumer-key-plan.v1")
        self.assertEqual(receipt["schema"], "cloudx.phi-consumer-key-install.v1")
        self.assertFalse(plan["automaticAction"])
        self.assertFalse(any(plan["authorization"].values()))
        self.assertTrue(plan["gatewayRestartRequired"])
        self.assertFalse(plan["phiServiceRestartRequired"])
        self.assertTrue(receipt["cloudxClientCredentialUnchanged"])
        self.assertFalse(receipt["previousCredentialRevoked"])
        self.assertFalse(receipt["phiServiceRestarted"])
        serialized = json.dumps({"plan": plan, "receipt": receipt}).casefold()
        for forbidden in ("api_key", "bearer ", "token-", "secret-value"):
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
