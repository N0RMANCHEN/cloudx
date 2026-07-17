from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_legacy_health_bridge_canary as canary  # noqa: E402


RESULT = {
    "LoadState": "loaded",
    "ActiveState": "inactive",
    "UnitFileState": "static",
    "Result": "success",
    "ExecMainStatus": "0",
}


class LegacyHealthBridgeCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.release_root = self.root / "opt/cloudx/releases"
        self.artifact = self.release_root / "0.1.15/cloudx-cloud.pyz"
        self.environment = self.root / "etc/cloudx/legacy-health-bridge.env"
        self.canary_unit = self.root / "etc/systemd/system/cloudx-legacy-health-bridge-canary.service"
        self.service = self.root / "etc/systemd/system/cloudx-legacy-health-bridge.service"
        self.timer = self.root / "etc/systemd/system/cloudx-legacy-health-bridge.timer"
        self.output = self.root / "run/cloudx-legacy-health-bridge-canary/v1.json"
        self.lock = self.root / "run/lock/canary.lock"
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b"fixture")
        self.lock.parent.mkdir(parents=True)
        self.units_constants = mock.patch.multiple(
            canary.units,
            DEFAULT_RELEASE_ROOT=self.release_root,
            DEFAULT_ENVIRONMENT=self.environment,
            DEFAULT_CANARY=self.canary_unit,
            DEFAULT_SERVICE=self.service,
            DEFAULT_TIMER=self.timer,
        )
        self.runner_constants = mock.patch.multiple(
            canary,
            DEFAULT_OUTPUT=self.output,
            DEFAULT_LOCK=self.lock,
        )
        self.units_constants.start()
        self.runner_constants.start()

    def tearDown(self) -> None:
        self.runner_constants.stop()
        self.units_constants.stop()
        self.temp.cleanup()

    def _patches(self):
        return [
            mock.patch.object(canary.os, "geteuid", return_value=0),
            mock.patch.object(canary, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(canary.units, "_validate_runtime_directories"),
            mock.patch.object(canary.units, "_validate_artifact"),
            mock.patch.object(canary.units, "verify_artifact"),
            mock.patch.object(canary, "_require_installed_files"),
            mock.patch.object(canary, "_require_runtime_boundaries"),
            mock.patch.object(canary, "_canary_result", return_value=dict(RESULT)),
            mock.patch.object(
                canary,
                "_validate_output",
                return_value={"document": {}, "sha256": "a" * 64},
            ),
            mock.patch.object(canary, "_cleanup_output", side_effect=self._cleanup_fixture),
        ]

    def _systemctl_success(self, action: str) -> None:
        if action == "start":
            self.output.parent.mkdir(parents=True, mode=0o755)
            self.output.write_text("fixture", encoding="utf-8")
        elif action != "stop":
            raise AssertionError(action)

    def _cleanup_fixture(self) -> None:
        self.output.unlink(missing_ok=True)
        try:
            self.output.parent.rmdir()
        except FileNotFoundError:
            pass

    def test_default_plan_is_non_authorizing_and_reads_no_runtime_state(self) -> None:
        self.artifact.unlink()
        output = StringIO()
        with mock.patch.object(canary, "_require_runtime_boundaries") as runtime, redirect_stdout(output):
            self.assertEqual(canary.main(["--release-version", "0.1.15"]), 0)
        runtime.assert_not_called()
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], canary.CONFIRMATION)
        self.assertEqual(document["outputPath"], str(self.output))
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))

    def test_custom_artifact_is_rejected_even_for_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            canary.main([
                "--release-version",
                "0.1.15",
                "--artifact",
                str(self.root / "other.pyz"),
            ])

    def test_apply_requires_exact_confirmation_before_root_or_artifact_checks(self) -> None:
        with mock.patch.object(canary.units, "verify_artifact") as verify:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                canary.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--release-version",
                    "0.1.15",
                ])
        verify.assert_not_called()

    def test_success_runs_only_canary_and_removes_temporary_output(self) -> None:
        output = StringIO()
        patches = self._patches()
        patches.append(mock.patch.object(canary, "_systemctl", side_effect=self._systemctl_success))
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(canary.main([
                "--apply",
                "--confirm",
                canary.CONFIRMATION,
                "--release-version",
                "0.1.15",
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "accepted")
        self.assertTrue(document["canaryStarted"])
        self.assertTrue(document["temporaryOutputRemoved"])
        self.assertFalse(document["primaryServiceStarted"])
        self.assertFalse(document["primaryTimerEnabled"])
        self.assertFalse(document["legacyOutputMutated"])
        self.assertFalse(document["releaseActivated"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.parent.exists())
        systemctl = entered[-1]
        systemctl.assert_called_once_with("start")

    def test_failed_start_stops_canary_and_removes_temporary_state(self) -> None:
        calls = []

        def systemctl(action: str) -> None:
            calls.append(action)
            if action == "start":
                raise RuntimeError("failed")

        patches = self._patches()
        patches.append(mock.patch.object(canary, "_systemctl", side_effect=systemctl))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "temporary state was removed"):
                canary.main([
                    "--apply",
                    "--confirm",
                    canary.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertEqual(calls, ["start", "stop"])
        self.assertFalse(self.output.exists())

    def test_invalid_output_stops_canary_and_cleans_the_file(self) -> None:
        patches = self._patches()
        patches[8] = mock.patch.object(canary, "_validate_output", side_effect=RuntimeError("invalid"))
        patches.append(mock.patch.object(canary, "_systemctl", side_effect=self._systemctl_success))
        with ExitStack() as stack:
            systemctl = None
            for patcher in patches:
                entered = stack.enter_context(patcher)
                if patcher is patches[-1]:
                    systemctl = entered
            with self.assertRaisesRegex(RuntimeError, "temporary state was removed"):
                canary.main([
                    "--apply",
                    "--confirm",
                    canary.CONFIRMATION,
                    "--release-version",
                    "0.1.15",
                ])
        self.assertIsNotNone(systemctl)
        self.assertEqual(systemctl.call_args_list, [mock.call("start"), mock.call("stop")])
        self.assertFalse(self.output.exists())

    def test_stale_output_is_rejected_before_canary_start(self) -> None:
        self.output.parent.mkdir(parents=True)
        self.output.write_text("stale", encoding="utf-8")
        patches = self._patches()
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with mock.patch.object(canary, "_systemctl") as systemctl:
                with self.assertRaisesRegex(RuntimeError, "must be absent"):
                    canary.main([
                        "--apply",
                        "--confirm",
                        canary.CONFIRMATION,
                        "--release-version",
                        "0.1.15",
                    ])
        systemctl.assert_not_called()

    def test_output_validation_accepts_only_the_strict_public_legacy_contract(self) -> None:
        data = (ROOT / "shared/contracts/examples/legacy-health.json").read_bytes()
        snapshot = canary.units.Snapshot(True, data, 0o644, 0, 0)
        with mock.patch.object(canary, "_require_output_directory", return_value=True), mock.patch.object(
            canary.units, "_safe_snapshot", return_value=snapshot
        ):
            result = canary._validate_output()
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())

        invalid = canary.units.Snapshot(True, b"{}", 0o644, 0, 0)
        with mock.patch.object(canary, "_require_output_directory", return_value=True), mock.patch.object(
            canary.units, "_safe_snapshot", return_value=invalid
        ):
            with self.assertRaisesRegex(RuntimeError, "legacy contract"):
                canary._validate_output()

    def test_installed_canary_must_match_the_exact_signed_template(self) -> None:
        environment = b"environment\n"
        unit = b"unit\n"
        snapshots = [
            canary.units.Snapshot(True, environment, 0o644, 0, 0),
            canary.units.Snapshot(True, unit, 0o644, 0, 0),
        ]
        with mock.patch.object(
            canary.units,
            "_templates",
            return_value={"environment": environment, "canary": unit},
        ), mock.patch.object(canary.units, "_safe_snapshot", side_effect=snapshots):
            canary._require_installed_files(self.artifact, "0.1.15")

        snapshots[-1] = canary.units.Snapshot(True, b"other", 0o644, 0, 0)
        with mock.patch.object(
            canary.units,
            "_templates",
            return_value={"environment": environment, "canary": unit},
        ), mock.patch.object(canary.units, "_safe_snapshot", side_effect=snapshots):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                canary._require_installed_files(self.artifact, "0.1.15")


if __name__ == "__main__":
    unittest.main()
