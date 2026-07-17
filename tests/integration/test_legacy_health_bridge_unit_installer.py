from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import install_legacy_health_bridge_units as installer  # noqa: E402


ENVIRONMENT = b"CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT=/fixture/releases/0.1.15/cloudx-cloud.pyz\n"
SERVICE = b"""[Unit]
Description=fixture

[Service]
EnvironmentFile=/etc/cloudx/legacy-health-bridge.env
ExecStart=/usr/bin/python3 ${CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT} legacy-health-bridge --source /run/cloudx/health.json --publish-to /var/lib/cloudx/health/v1.json
RestrictAddressFamilies=AF_UNIX
"""
TIMER = b"""[Timer]
Unit=cloudx-legacy-health-bridge.service

[Install]
WantedBy=timers.target
"""


def state(load: str, active: str, unit_file: str) -> dict[str, str]:
    return {"LoadState": load, "ActiveState": active, "UnitFileState": unit_file}


LEGACY_SERVICE_STATE = state("loaded", "inactive", "static")
LEGACY_TIMER_STATE = state("loaded", "active", "enabled")


class LegacyHealthBridgeUnitInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.release_root = self.root / "fixture/releases"
        self.artifact = self.release_root / "0.1.15/cloudx-cloud.pyz"
        self.environment = self.root / "etc/cloudx/legacy-health-bridge.env"
        self.service = self.root / "etc/systemd/system/cloudx-legacy-health-bridge.service"
        self.timer = self.root / "etc/systemd/system/cloudx-legacy-health-bridge.timer"
        self.backup_root = self.root / "var/lib/cloudx/legacy-health-bridge-install-backups"
        self.lock = self.root / "run/lock/install.lock"
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b"fixture")
        self.environment.parent.mkdir(parents=True)
        self.service.parent.mkdir(parents=True)
        self.backup_root.parent.mkdir(parents=True)
        self.lock.parent.mkdir(parents=True)
        self.constants = mock.patch.multiple(
            installer,
            DEFAULT_RELEASE_ROOT=self.release_root,
            DEFAULT_ENVIRONMENT=self.environment,
            DEFAULT_SERVICE=self.service,
            DEFAULT_TIMER=self.timer,
            DEFAULT_BACKUP_ROOT=self.backup_root,
            DEFAULT_LOCK=self.lock,
        )
        self.constants.start()

    def tearDown(self) -> None:
        self.constants.stop()
        self.temp.cleanup()

    @staticmethod
    def _atomic_write(path: pathlib.Path, data: bytes, mode: int, uid: int, gid: int) -> None:
        del uid, gid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)

    def _unit_state(self, unit: str) -> dict[str, str]:
        if unit == installer.LEGACY_SERVICE:
            return dict(LEGACY_SERVICE_STATE)
        if unit == installer.LEGACY_TIMER:
            return dict(LEGACY_TIMER_STATE)
        if unit == installer.TARGET_SERVICE:
            return state("loaded", "inactive", "static") if self.service.exists() else state("not-found", "inactive", "")
        if unit == installer.TARGET_TIMER:
            return state("loaded", "inactive", "disabled") if self.timer.exists() else state("not-found", "inactive", "")
        raise AssertionError(unit)

    def _patches(self):
        return [
            mock.patch.object(installer.os, "geteuid", return_value=0),
            mock.patch.object(installer, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(installer, "_validate_root_directory"),
            mock.patch.object(installer, "_validate_artifact"),
            mock.patch.object(installer, "verify_artifact"),
            mock.patch.object(
                installer,
                "_templates",
                return_value={"environment": ENVIRONMENT, "service": SERVICE, "timer": TIMER},
            ),
            mock.patch.object(installer, "_unit_state", side_effect=self._unit_state),
            mock.patch.object(installer, "_verify_units"),
            mock.patch.object(installer, "_daemon_reload"),
            mock.patch.object(installer, "atomic_write", side_effect=self._atomic_write),
            mock.patch.object(installer.time, "time_ns", return_value=123456789),
        ]

    def test_default_plan_is_non_authorizing_and_reads_no_runtime_files(self) -> None:
        self.artifact.unlink()
        output = StringIO()
        with mock.patch.object(installer, "_safe_snapshot") as snapshot, redirect_stdout(output):
            self.assertEqual(installer.main(["--release-version", "0.1.15"]), 0)
        snapshot.assert_not_called()
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], installer.CONFIRMATION)
        self.assertFalse(document["serviceStartRequired"])
        self.assertFalse(document["timerEnableRequired"])
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_custom_artifact_is_rejected_even_for_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            installer.main([
                "--release-version",
                "0.1.15",
                "--artifact",
                str(self.root / "other.pyz"),
            ])

    def test_apply_requires_exact_confirmation_before_root_or_artifact_checks(self) -> None:
        with mock.patch.object(installer, "verify_artifact") as verify:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                installer.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--release-version",
                    "0.1.15",
                ])
        verify.assert_not_called()

    def test_success_installs_disabled_inactive_units_and_preserves_legacy_path(self) -> None:
        output = StringIO()
        patches = self._patches()
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(installer.main([
                "--apply",
                "--confirm",
                installer.CONFIRMATION,
                "--release-version",
                "0.1.15",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "installed")
        self.assertEqual(document["filesChanged"], 3)
        self.assertTrue(document["daemonReloaded"])
        self.assertFalse(document["serviceStarted"])
        self.assertFalse(document["timerEnabled"])
        self.assertFalse(document["legacyServiceStopped"])
        self.assertFalse(document["legacyTimerDisabled"])
        self.assertFalse(document["releaseActivated"])
        self.assertEqual(self.environment.read_bytes(), ENVIRONMENT)
        self.assertEqual(self.service.read_bytes(), SERVICE)
        self.assertEqual(self.timer.read_bytes(), TIMER)
        for path in (self.environment, self.service, self.timer):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        backup = self.backup_root / "123456789"
        self.assertTrue((backup / "manifest.json").is_file())
        daemon_reload = entered[8]
        daemon_reload.assert_called_once_with()

    def test_failed_unit_verification_restores_absent_files_and_removes_failed_backup(self) -> None:
        patches = self._patches()
        patches[7] = mock.patch.object(installer, "_verify_units", side_effect=RuntimeError("invalid"))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertFalse(self.environment.exists())
        self.assertFalse(self.service.exists())
        self.assertFalse(self.timer.exists())
        self.assertEqual(list(self.backup_root.iterdir()), [])

    def test_exact_install_is_idempotent_without_daemon_reload_or_backup(self) -> None:
        self._atomic_write(self.environment, ENVIRONMENT, 0o644, 0, 0)
        self._atomic_write(self.service, SERVICE, 0o644, 0, 0)
        self._atomic_write(self.timer, TIMER, 0o644, 0, 0)
        output = StringIO()
        patches = self._patches()
        patches.append(mock.patch.object(installer, "_matches", return_value=True))
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(installer.main([
                "--apply",
                "--confirm",
                installer.CONFIRMATION,
                "--release-version",
                "0.1.15",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "already-installed")
        self.assertEqual(document["filesChanged"], 0)
        self.assertFalse(document["daemonReloaded"])
        self.assertIsNone(document["backup"])
        entered[8].assert_not_called()
        self.assertFalse(self.backup_root.exists())

    def test_active_target_or_unavailable_legacy_timer_is_rejected_before_writes(self) -> None:
        def active_target(unit: str) -> dict[str, str]:
            if unit == installer.TARGET_SERVICE:
                return state("loaded", "active", "static")
            return self._unit_state(unit)

        patches = self._patches()
        patches[6] = mock.patch.object(installer, "_unit_state", side_effect=active_target)
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "must be inactive"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertFalse(self.environment.exists())

        def stopped_legacy(unit: str) -> dict[str, str]:
            if unit == installer.LEGACY_TIMER:
                return state("loaded", "inactive", "enabled")
            return self._unit_state(unit)

        patches = self._patches()
        patches[6] = mock.patch.object(installer, "_unit_state", side_effect=stopped_legacy)
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "must remain loaded"):
                installer.main([
                    "--apply",
                    "--confirm",
                    installer.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])

    def test_template_validation_rejects_mutable_selector(self) -> None:
        service = SERVICE + b"# /opt/cloudx/current\n"

        def template(_artifact: pathlib.Path, name: str) -> bytes:
            return {
                "cloudx-legacy-health-bridge.env.example": (
                    "CLOUDX_LEGACY_HEALTH_BRIDGE_ARTIFACT=%s\n" % self.artifact
                ).encode("utf-8"),
                installer.TARGET_SERVICE: service,
                installer.TARGET_TIMER: TIMER,
            }[name]

        with mock.patch.object(installer, "_artifact_template", side_effect=template):
            with self.assertRaisesRegex(RuntimeError, "mutable code"):
                installer._templates(self.artifact, "0.1.15")

    def test_snapshot_rejects_symlink_and_oversized_unit(self) -> None:
        source = self.root / "source"
        source.write_bytes(b"value")
        alias = self.root / "alias"
        alias.symlink_to(source)
        with self.assertRaisesRegex(RuntimeError, "non-symlink"):
            installer._safe_snapshot(alias, "fixture", required=True, maximum=64)
        source.write_bytes(b"x" * 65)
        with self.assertRaisesRegex(RuntimeError, "size limit"):
            installer._safe_snapshot(source, "fixture", required=True, maximum=64)


if __name__ == "__main__":
    unittest.main()
