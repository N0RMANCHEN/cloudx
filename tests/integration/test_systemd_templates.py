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
        self.assertIn("/opt/cloudx/current/cloudx-cloud.pyz adapt-account-state --json", account)
        self.assertIn("CLOUDX_ACCOUNT_STATE_PATH=/run/cloudx-account-state/accounts.json", account)
        self.assertIn("ReadWritePaths=/run/cloudx-account-state", account)
        self.assertIn("User=cloudx", health)
        self.assertIn("CLOUDX_HEALTH_PATH=/run/cloudx/health.json", health)
        self.assertIn("ReadWritePaths=/run/cloudx", health)
        self.assertIn("InaccessiblePaths=/var/lib/codex-gateway/cliproxy-auth", health)
        for service in (account, health):
            self.assertNotIn("/home/", service)
            self.assertNotIn("18317", service)
            self.assertNotIn("ReadWritePaths=/var/lib/codex-gateway", service)

    def test_active_health_timers_are_explicit_and_repeating(self) -> None:
        for name, unit in (
            ("cloudx-account-state.timer", "cloudx-account-state.service"),
            ("cloudx-health.timer", "cloudx-health.service"),
        ):
            timer = (ACTIVE_SYSTEMD / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("OnUnitActiveSec=1min", timer)
                self.assertIn("Unit=%s" % unit, timer)
                self.assertIn("Persistent=true", timer)


if __name__ == "__main__":
    unittest.main()
