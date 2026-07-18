from __future__ import annotations

import pathlib
import unittest


ACTIVE_SYSTEMD = pathlib.Path(__file__).resolve().parents[2] / "cloud/cloudx_cloud/data/systemd"


ROOT = pathlib.Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "cloud/systemd"


class ShadowSystemdTemplateTests(unittest.TestCase):
    def test_shadow_services_use_versioned_artifact_without_current(self) -> None:
        environment = (SYSTEMD / "cloudx-shadow.env.example").read_text(encoding="utf-8")
        self.assertIn("CLOUDX_CLOUD_ARTIFACT=/opt/cloudx/releases/0.1.2/cloudx-cloud.pyz", environment)
        self.assertIn("CLOUDX_ACCOUNT_STATE_SOURCE=/var/lib/cloudx/cpa-health/state.json", environment)
        for name in ("cloudx-shadow-account-state.service", "cloudx-shadow-health.service"):
            service = (SYSTEMD / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("/usr/bin/python3 ${CLOUDX_CLOUD_ARTIFACT}", service)
                self.assertIn("EnvironmentFile=/etc/cloudx/cloudx-shadow.env", service)
                self.assertNotIn("/opt/cloudx/current", service)
                self.assertNotIn("18317", service)
        account = (SYSTEMD / "cloudx-shadow-account-state.service").read_text(encoding="utf-8")
        self.assertIn("After=cloudx-cpa-health.service", account)
        self.assertIn("/var/lib/cloudx/cpa-health/state.json", account)
        self.assertNotIn("codex-quota-monitor", account)

    def test_shadow_services_cannot_write_production_credentials(self) -> None:
        account = (SYSTEMD / "cloudx-shadow-account-state.service").read_text(encoding="utf-8")
        health = (SYSTEMD / "cloudx-shadow-health.service").read_text(encoding="utf-8")
        self.assertIn("User=root", account)
        self.assertIn("InaccessiblePaths=/var/lib/codex-gateway/cliproxy-auth", account)
        self.assertIn("User=cloudx", health)
        for service in (account, health):
            self.assertIn("ReadWritePaths=/run/cloudx-shadow", service)
            self.assertNotIn("ReadWritePaths=/var/lib/codex-gateway", service)

    def test_active_health_templates_are_signed_artifact_data_and_secret_safe(self) -> None:
        account = (ACTIVE_SYSTEMD / "cloudx-account-state.service").read_text(encoding="utf-8")
        health = (ACTIVE_SYSTEMD / "cloudx-health.service").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/env CLOUDX_ACCOUNT_STATE_PATH=", account)
        self.assertIn("/opt/cloudx/current/cloudx-cloud.pyz adapt-account-state --json", account)
        self.assertIn("CLOUDX_ACCOUNT_STATE_PATH=/run/cloudx-account-state/accounts.json", account)
        self.assertIn("ReadWritePaths=/run/cloudx-account-state", account)
        self.assertIn("RuntimeDirectoryPreserve=yes", account)
        self.assertIn("User=cloudx", health)
        self.assertIn("ExecStart=/usr/bin/env CLOUDX_ACCOUNT_STATE_PATH=", health)
        self.assertIn("CLOUDX_HEALTH_PATH=/run/cloudx/health.json", health)
        self.assertIn("ReadWritePaths=/run/cloudx", health)
        self.assertIn("RuntimeDirectoryPreserve=yes", health)
        self.assertIn("InaccessiblePaths=/var/lib/codex-gateway/cliproxy-auth", health)
        for service in (account, health):
            self.assertNotIn("Environment=CLOUDX_", service)
            self.assertNotIn("/home/", service)
            self.assertNotIn("18317", service)
            self.assertNotIn("ReadWritePaths=/var/lib/codex-gateway", service)

    def test_active_health_timers_are_explicit_and_repeating(self) -> None:
        for name, unit, initial in (
            ("cloudx-account-state.timer", "cloudx-account-state.service", "1min"),
            ("cloudx-health.timer", "cloudx-health.service", "2min"),
        ):
            timer = (ACTIVE_SYSTEMD / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("OnActiveSec=%s" % initial, timer)
                self.assertIn("OnUnitActiveSec=1min", timer)
                self.assertIn("Unit=%s" % unit, timer)
                self.assertIn("Persistent=true", timer)

    def test_cpa_health_template_moves_execution_off_mutable_checkout(self) -> None:
        service = (ACTIVE_SYSTEMD / "cloudx-cpa-health.service").read_text(encoding="utf-8")
        timer = (ACTIVE_SYSTEMD / "cloudx-cpa-health.timer").read_text(encoding="utf-8")
        self.assertIn("/opt/cloudx/current/cloudx-cloud.pyz cpa-health", service)
        self.assertNotIn("ConditionPathExists=/opt/codex-gateway/codexx_app", service)
        self.assertNotIn("CLOUDX_LEGACY_RUNTIME_ROOT", service)
        self.assertIn("ReadOnlyPaths=/opt/cloudx/releases", service)
        self.assertIn("ReadWritePaths=/var/lib/cloudx/cpa-health", service)
        self.assertIn("/var/lib/codex-gateway/cliproxy-auth-failures", service)
        self.assertIn("CLOUDX_CPA_PROBE_CONCURRENCY=2", service)
        self.assertNotIn("/home/", service)
        self.assertNotIn("send-email", service)
        self.assertIn("OnActiveSec=2min", timer)
        self.assertIn("OnUnitActiveSec=5min", timer)

    def test_cpa_failure_receipts_trigger_network_free_archive_maintenance(self) -> None:
        service = (ACTIVE_SYSTEMD / "cloudx-cpa-failure.service").read_text(encoding="utf-8")
        path = (ACTIVE_SYSTEMD / "cloudx-cpa-failure.path").read_text(encoding="utf-8")
        self.assertIn("cpa-health --runtime-failures-only", service)
        self.assertIn("PrivateNetwork=true", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertIn("/var/lib/codex-gateway/cliproxy-auth-failures", service)
        self.assertIn("PathChanged=/var/lib/codex-gateway/cliproxy-auth-failures", path)
        self.assertIn("Unit=cloudx-cpa-failure.service", path)
        self.assertNotIn("phi", path.casefold())

    def test_legacy_health_bridge_is_fixed_to_a_signed_artifact_and_off_network(self) -> None:
        canary = (ACTIVE_SYSTEMD / "cloudx-legacy-health-bridge-canary.service").read_text(encoding="utf-8")
        service = (ACTIVE_SYSTEMD / "cloudx-legacy-health-bridge.service").read_text(encoding="utf-8")
        timer = (ACTIVE_SYSTEMD / "cloudx-legacy-health-bridge.timer").read_text(encoding="utf-8")
        environment = (ACTIVE_SYSTEMD / "cloudx-legacy-health-bridge.env.example").read_text(encoding="utf-8")
        self.assertIn("CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT=/opt/cloudx/releases/0.1.15/", environment)
        self.assertIn("${CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT} legacy-health-bridge", service)
        self.assertIn("ReadOnlyPaths=/opt/cloudx/releases /etc/cloudx /run/cloudx", service)
        self.assertIn("ReadWritePaths=/var/lib/cloudx/health", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertNotIn("/opt/cloudx/current", service)
        self.assertNotIn("/home/", service)
        self.assertIn("--publish-to /run/cloudx-legacy-health-bridge-canary/v1.json", canary)
        self.assertIn("ReadWritePaths=/run/cloudx-legacy-health-bridge-canary", canary)
        self.assertIn("/var/lib/cloudx/health", canary)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", canary)
        self.assertNotIn("[Install]", canary)
        self.assertNotIn("--publish-to /var/lib/cloudx/health", canary)
        self.assertNotIn("/opt/cloudx/current", canary)
        self.assertNotIn("/home/", canary)
        self.assertIn("OnActiveSec=2min", timer)
        self.assertIn("OnUnitActiveSec=1min", timer)
        self.assertIn("Unit=cloudx-legacy-health-bridge.service", timer)


if __name__ == "__main__":
    unittest.main()
