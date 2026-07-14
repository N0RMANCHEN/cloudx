from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "cloud/systemd"


class ShadowSystemdTemplateTests(unittest.TestCase):
    def test_shadow_services_use_versioned_artifact_without_current(self) -> None:
        environment = (SYSTEMD / "cloudx-shadow.env.example").read_text(encoding="utf-8")
        self.assertIn("CLOUDX_CLOUD_ARTIFACT=/opt/cloudx/releases/0.1.1/cloudx-cloud.pyz", environment)
        for name in ("cloudx-shadow-account-state.service", "cloudx-shadow-health.service"):
            service = (SYSTEMD / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("/usr/bin/python3 ${CLOUDX_CLOUD_ARTIFACT}", service)
                self.assertIn("EnvironmentFile=/etc/cloudx/cloudx-shadow.env", service)
                self.assertNotIn("/opt/cloudx/current", service)
                self.assertNotIn("18317", service)

    def test_shadow_services_cannot_write_production_credentials(self) -> None:
        account = (SYSTEMD / "cloudx-shadow-account-state.service").read_text(encoding="utf-8")
        health = (SYSTEMD / "cloudx-shadow-health.service").read_text(encoding="utf-8")
        self.assertIn("User=root", account)
        self.assertIn("InaccessiblePaths=/var/lib/codex-gateway/cliproxy-auth", account)
        self.assertIn("User=cloudx", health)
        for service in (account, health):
            self.assertIn("ReadWritePaths=/run/cloudx-shadow", service)
            self.assertNotIn("ReadWritePaths=/var/lib/codex-gateway", service)


if __name__ == "__main__":
    unittest.main()
