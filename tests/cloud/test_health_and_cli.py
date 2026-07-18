from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.cli import client_config, handshake, main  # noqa: E402
from cloudx_cloud.compatibility_profile import read_profile  # noqa: E402
from cloudx_cloud.config import Config  # noqa: E402
from cloudx_cloud.consumer_credential import read_policy  # noqa: E402
from cloudx_cloud.consumer_traffic import read_policy as read_traffic_policy  # noqa: E402
from cloudx_cloud.gateway import GatewayProbe  # noqa: E402
from cloudx_cloud.health import build_health, publish  # noqa: E402


class CloudHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.credential = self.root / "credential"
        self.credential.write_text("secret-key\n", encoding="utf-8")
        self.credential.chmod(0o600)
        self.config = Config(
            auth_dir=self.root / "auth",
            import_lock_path=self.root / "run/import.lock",
            health_path=self.root / "run/health.json",
            account_state_path=self.root / "run/accounts.json",
            account_state_source_path=self.root / "legacy/state.json",
            gateway_url="http://127.0.0.1:1",
            gateway_version="7.2.71",
            gateway_forward_host="127.0.0.1",
            gateway_forward_port=8317,
            client_credential_file=self.credential,
            deployment_id="test",
            build_commit="abcdef0",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @mock.patch("cloudx_cloud.cli.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_handshake_has_no_secret(self, unused_probe: mock.Mock) -> None:
        document = handshake(self.config)
        serialized = json.dumps(document)
        self.assertEqual(document["schema"], "cloudx.handshake.v1")
        self.assertNotIn("secret-key", serialized)
        self.assertIn("capacity.v1", document["capabilities"])
        self.assertIn("client-config.v1", document["capabilities"])
        self.assertIn("http-importer-stop-gate.v1", document["capabilities"])
        self.assertIn("legacy-health-bridge.v1", document["capabilities"])
        self.assertIn("phi-cloud-consumer-credential.v1", document["capabilities"])
        self.assertIn("phi-cloud-consumer-traffic-policy.v1", document["capabilities"])
        self.assertIn("phi-mesh-compatibility-profile.v1", document["capabilities"])

    def test_compatibility_profile_is_packaged_read_only_and_secret_free(self) -> None:
        profile = read_profile()
        expected = json.loads(
            (ROOT / "shared/contracts/examples/phi-mesh-compatibility-profile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile, expected)
        self.assertTrue(profile["authorization"]["profileReadOnly"])
        self.assertFalse(profile["authorization"]["profileGrantsCredentialAccess"])
        serialized = json.dumps(profile).casefold()
        for forbidden in ("api_key", "apikey", "token", "deviceid", "taskid", "sessionid"):
            self.assertNotIn(forbidden, serialized)
        bridge = profile["contracts"]["legacyHealthBridge"]
        self.assertTrue(bridge["migrationOnly"])
        self.assertFalse(bridge["automaticInstallation"])

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["compatibility-profile"]), 0)
        self.assertEqual(json.loads(output.getvalue()), profile)

    def test_compatibility_profile_rejects_modified_authority(self) -> None:
        raw = (ROOT / "shared/contracts/examples/phi-mesh-compatibility-profile.json").read_bytes()
        modified = raw.replace(b'"profileReadOnly": true', b'"profileReadOnly": false')
        with mock.patch("cloudx_cloud.compatibility_profile.pkgutil.get_data", return_value=modified):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                read_profile()

    def test_phi_consumer_credential_policy_is_packaged_and_non_authorizing(self) -> None:
        policy = read_policy()
        expected = json.loads(
            (ROOT / "shared/contracts/examples/phi-cloud-consumer-credential.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy, expected)
        self.assertEqual(policy["scope"]["allowedOperations"], ["gateway_inference"])
        self.assertFalse(policy["representation"]["device"])
        self.assertFalse(policy["authorization"]["installAuthorized"])

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["phi-consumer-credential-policy"]), 0)
        self.assertEqual(json.loads(output.getvalue()), policy)

    def test_phi_consumer_credential_policy_rejects_modified_scope(self) -> None:
        raw = (ROOT / "shared/contracts/examples/phi-cloud-consumer-credential.json").read_bytes()
        modified = raw.replace(b'"gateway_inference"', b'"account_import"', 1)
        with mock.patch("cloudx_cloud.consumer_credential.pkgutil.get_data", return_value=modified):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                read_policy()

    def test_phi_consumer_traffic_policy_is_packaged_and_bounded(self) -> None:
        policy = read_traffic_policy()
        expected = json.loads(
            (ROOT / "shared/contracts/examples/phi-cloud-consumer-traffic-policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(policy, expected)
        self.assertEqual(policy["limits"]["maxInFlight"], 4)
        self.assertEqual(policy["limits"]["maxQueueDepth"], 16)
        self.assertEqual(policy["retry"]["maxAttempts"], 3)
        self.assertTrue(policy["retry"]["neverRetryAfterResponseBytes"])

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["phi-consumer-traffic-policy"]), 0)
        self.assertEqual(json.loads(output.getvalue()), policy)

    def test_phi_consumer_traffic_policy_rejects_unbounded_concurrency(self) -> None:
        raw = (ROOT / "shared/contracts/examples/phi-cloud-consumer-traffic-policy.json").read_bytes()
        modified = raw.replace(b'"maxInFlight": 4', b'"maxInFlight": 400')
        with mock.patch("cloudx_cloud.consumer_traffic.pkgutil.get_data", return_value=modified):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                read_traffic_policy()

    def test_client_config_requires_private_file(self) -> None:
        document = client_config(self.config)
        self.assertEqual(document["apiKey"], "secret-key")
        self.credential.chmod(0o644)
        with self.assertRaises(RuntimeError):
            client_config(self.config)

    @mock.patch("cloudx_cloud.health.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_health_is_secret_free_and_publish_is_readable(self, unused_probe: mock.Mock) -> None:
        self.config.auth_dir.mkdir()
        (self.config.auth_dir / "account.json").write_text("{}", encoding="utf-8")
        document = build_health(self.config)
        self.assertEqual(document["importStatus"], "ready")
        self.assertFalse(self.config.import_lock_path.exists())
        self.assertEqual(document["accountCounts"]["total"], 0)
        self.assertEqual(document["freshness"]["state"], "unknown")
        self.assertNotIn("secret-key", json.dumps(document))
        publish(self.config.health_path, document)
        self.assertEqual(stat.S_IMODE(self.config.health_path.stat().st_mode), 0o644)
        self.assertEqual(json.loads(self.config.health_path.read_text())["schema"], "cloudx.health.v1")

    @mock.patch("cloudx_cloud.health.probe_gateway", return_value=GatewayProbe("healthy", 200, "ok"))
    def test_health_observes_a_busy_import_lock_without_writing_it(self, unused_probe: mock.Mock) -> None:
        self.config.import_lock_path.parent.mkdir(parents=True)
        self.config.import_lock_path.write_text("", encoding="utf-8")
        before = self.config.import_lock_path.stat()
        with mock.patch("cloudx_cloud.health.fcntl.flock", side_effect=[BlockingIOError(), None]):
            document = build_health(self.config)
        after = self.config.import_lock_path.stat()
        self.assertEqual(document["importStatus"], "busy")
        self.assertEqual((after.st_size, after.st_mtime_ns), (before.st_size, before.st_mtime_ns))

    def test_signed_artifact_emits_active_health_systemd_templates(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["systemd-template", "cloudx-health.service"]), 0)
        service = output.getvalue()
        self.assertIn("ExecStart=/usr/bin/env CLOUDX_ACCOUNT_STATE_PATH=", service)
        self.assertIn("CLOUDX_HEALTH_PATH=/run/cloudx/health.json", service)
        self.assertIn("RuntimeDirectoryPreserve=yes", service)
        self.assertNotIn("/home/", service)

    def test_signed_artifact_emits_versioned_cpa_health_templates(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["systemd-template", "cloudx-cpa-health.service"]), 0)
        service = output.getvalue()
        self.assertIn("/opt/cloudx/current/cloudx-cloud.pyz cpa-health", service)
        self.assertIn("native signed runtime", service)
        self.assertNotIn("CLOUDX_LEGACY_RUNTIME_ROOT", service)
        self.assertNotIn("/opt/codex-gateway/codexx_app", service)
        self.assertIn("ReadOnlyPaths=/opt/cloudx/releases", service)
        self.assertNotIn("/home/", service)

        path_output = StringIO()
        with redirect_stdout(path_output):
            self.assertEqual(main(["systemd-template", "cloudx-cpa-failure.path"]), 0)
        self.assertIn("Unit=cloudx-cpa-failure.service", path_output.getvalue())

        failure_output = StringIO()
        with redirect_stdout(failure_output):
            self.assertEqual(main(["systemd-template", "cloudx-cpa-failure.service"]), 0)
        self.assertIn("--runtime-failures-only", failure_output.getvalue())
        self.assertIn("PrivateNetwork=true", failure_output.getvalue())

    def test_signed_artifact_emits_fixed_release_legacy_bridge_templates(self) -> None:
        canary_output = StringIO()
        with redirect_stdout(canary_output):
            self.assertEqual(main(["systemd-template", "cloudx-legacy-health-bridge-canary.service"]), 0)
        canary = canary_output.getvalue()
        self.assertIn("/run/cloudx-legacy-health-bridge-canary/v1.json", canary)
        self.assertIn("InaccessiblePaths=", canary)
        self.assertIn("/var/lib/cloudx/health", canary)
        self.assertNotIn("--publish-to /var/lib/cloudx/health", canary)
        service_output = StringIO()
        with redirect_stdout(service_output):
            self.assertEqual(main(["systemd-template", "cloudx-legacy-health-bridge.service"]), 0)
        service = service_output.getvalue()
        self.assertIn("${CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT} legacy-health-bridge", service)
        self.assertIn("/run/cloudx/health.json", service)
        self.assertIn("/var/lib/cloudx/health/v1.json", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertNotIn("/opt/cloudx/current", service)
        self.assertNotIn("/home/", service)


if __name__ == "__main__":
    unittest.main()
