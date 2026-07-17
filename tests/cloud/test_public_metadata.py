from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_health  # noqa: E402
from cloudx_cloud.account_state import publish as publish_account_state  # noqa: E402
from cloudx_cloud.consumer_credential import read_policy  # noqa: E402
from cloudx_cloud.health import publish as publish_health  # noqa: E402
from cloudx_cloud.public_metadata import (  # noqa: E402
    PublicMetadataRejected,
    emit_error,
    emit_json,
    sanitize_public_error,
    validate_public_document,
)


class PublicMetadataTests(unittest.TestCase):
    def test_all_versioned_contract_examples_and_schemas_pass_boundary_validation(self) -> None:
        contract_root = ROOT / "shared/contracts"
        paths = sorted(contract_root.glob("*.schema.json")) + sorted((contract_root / "examples").glob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertIs(validate_public_document(document, path.name), document)

    def test_packaged_credential_policy_may_only_negate_phi_identity_fields(self) -> None:
        policy = read_policy()
        self.assertEqual(policy["representation"], {"principal": "phi_cloud_service", "device": False, "task": False, "session": False})
        modified = json.loads(json.dumps(policy))
        modified["representation"]["device"] = "device-123"
        with self.assertRaises(PublicMetadataRejected):
            validate_public_document(modified)

    def test_phi_control_plane_metadata_is_rejected_at_any_depth(self) -> None:
        prohibited = (
            {"taskId": "task-1"},
            {"result": {"session": {"id": "session-1"}}},
            {"deviceId": "device-1"},
            {"writerLease": "lease-1"},
            {"approvalId": "approval-1"},
            {"localPath": "/Users/example/private.txt"},
            {"transferContent": "payload"},
            {"artifactId": "artifact-1"},
            {"contextRequest": {}},
            {"localAction": {}},
            {"artifacts": [{"id": "phi-artifact-1"}]},
            {"payload": "transfer body"},
        )
        for value in prohibited:
            with self.subTest(value=value), self.assertRaises(PublicMetadataRejected):
                validate_public_document({"schema": "fixture.v1", "value": value})

    def test_public_json_emission_fails_before_writing_prohibited_metadata(self) -> None:
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(PublicMetadataRejected):
            emit_json({"schema": "fixture.v1", "taskId": "task-1"})
        self.assertEqual(output.getvalue(), "")

    def test_public_errors_redact_phi_assignments_and_user_paths(self) -> None:
        raw = "request failed: taskId=task-1 source=/Users/example/private.txt"
        self.assertEqual(
            sanitize_public_error(raw),
            "request failed without exposing prohibited Phi metadata",
        )
        errors = StringIO()
        with redirect_stderr(errors):
            emit_error("capacity", raw)
        rendered = errors.getvalue()
        self.assertNotIn("task-1", rendered)
        self.assertNotIn("/Users/", rendered)
        self.assertIn("prohibited Phi metadata", rendered)

    def test_health_publication_rejects_phi_metadata_before_creating_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "health.json"
            document = {
                "schema": "cloudx.health.v1",
                "cloudxVersion": "0.1.15",
                "protocolVersion": 1,
                "gatewayStatus": "healthy",
                "importStatus": "ready",
                "accountCounts": {"total": 1, "available": 1, "limited": 0, "unavailable": 0},
                "checkedAt": "2026-07-17T00:00:00Z",
                "freshness": {"state": "fresh", "ageSeconds": 0},
                "deviceId": "device-1",
            }
            with self.assertRaises(PublicMetadataRejected):
                publish_health(path, document)
            self.assertFalse(path.exists())

    def test_account_state_publication_rejects_phi_metadata_before_creating_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "accounts.json"
            document = {
                "schema": "cloudx.account-state.v1",
                "source": "credential-health-summary",
                "observedAt": "2026-07-17T00:00:00Z",
                "accountCounts": {"total": 1, "available": 1, "limited": 0, "unavailable": 0},
                "unobservedAccounts": 0,
                "localPath": "/Volumes/private/account.json",
            }
            with self.assertRaises(PublicMetadataRejected):
                publish_account_state(path, document)
            self.assertFalse(path.exists())

    def test_cpa_health_public_summary_rejects_injected_phi_metadata(self) -> None:
        with self.assertRaises(PublicMetadataRejected):
            cpa_health.public_summary({"state": "healthy", "taskId": "task-1"})

    def test_release_state_and_cloudx_release_artifacts_are_not_phi_artifacts(self) -> None:
        document = {
            "schema": "cloudx.release-status.v1",
            "status": "active",
            "currentVersion": "0.1.15",
            "previousVersion": "0.1.13",
            "currentArtifactSha256": "0" * 64,
        }
        self.assertEqual(validate_public_document(document), document)
        manifest = json.loads(
            (ROOT / "shared/contracts/cloudx.release-manifest.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(validate_public_document(manifest), manifest)

    def test_only_cloudx_release_manifest_may_use_artifacts_collection(self) -> None:
        release = {
            "schema": "cloudx.release-manifest.v1",
            "artifacts": [{"name": "cloudx-cloud.pyz", "component": "cloud", "size": 1, "sha256": "0" * 64}],
        }
        self.assertEqual(validate_public_document(release), release)
        with self.assertRaises(PublicMetadataRejected):
            validate_public_document({"schema": "phi.fixture.v1", "artifacts": []})


if __name__ == "__main__":
    unittest.main()
