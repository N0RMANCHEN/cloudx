from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_legacy_health_bridge_artifact as stage  # noqa: E402


IDENTITY = {
    "artifactRef": "refs/heads/release-artifacts/v0.1.15",
    "artifactRefCommit": "a" * 40,
    "sourceRef": "b" * 40,
    "manifestSha256": "c" * 64,
}
SELECTORS = {
    "currentVersion": "0.1.21",
    "previousVersion": "0.1.20",
    "currentArtifactSha256": "d" * 64,
}
STAGED = {
    "schema": "cloudx.release-pinned-compatibility-stage.v1",
    "version": "0.1.15",
    "status": "staged",
    "manifestSha256": "c" * 64,
    "artifactSha256": "e" * 64,
}


class LegacyHealthBridgeArtifactStageTests(unittest.TestCase):
    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(stage, "_fetch_bundle") as fetch, redirect_stdout(output):
            self.assertEqual(stage.main(["--release-version", "0.1.15"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], stage.confirmation("0.1.15"))
        self.assertEqual(document["releaseRefCommit"], "332cb865a97d654efca4b4321b90cdc140e57e64")
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))
        fetch.assert_not_called()

    def test_apply_requires_exact_confirmation_before_runtime_action(self) -> None:
        with mock.patch.object(stage, "_apply") as apply:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                stage.main([
                    "--release-version",
                    "0.1.15",
                    "--apply",
                    "--confirm",
                    "wrong",
                ])
        apply.assert_not_called()

    def test_apply_preserves_selectors_and_reports_no_activation_or_restart(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            release_root = pathlib.Path(value) / "opt/cloudx"
            with mock.patch.object(stage.os, "geteuid", return_value=0), mock.patch.object(
                stage, "_validate_release_root"
            ), mock.patch.object(
                stage, "_transaction_lock", return_value=nullcontext()
            ), mock.patch.object(
                stage, "_fetch_bundle", return_value=(b"bundle", "a" * 40)
            ), mock.patch.object(
                stage.cloud_release, "stage_pinned_compatibility", return_value=dict(STAGED)
            ) as pinned_stage, mock.patch.object(
                stage, "_selector_snapshot", side_effect=(dict(SELECTORS), dict(SELECTORS))
            ), mock.patch.object(
                stage.cloud_release, "release_root", return_value=release_root
            ), mock.patch.object(stage, "_validate_staged_artifact") as validate_artifact:
                result = stage._apply("0.1.15", "repo", IDENTITY)

        self.assertEqual(result["selectorsBefore"], SELECTORS)
        self.assertEqual(result["selectorsAfter"], SELECTORS)
        self.assertFalse(result["releaseActivated"])
        self.assertFalse(result["serviceRestarted"])
        pinned_stage.assert_called_once_with(
            b"bundle",
            expected_version="0.1.15",
            expected_source_commit="b" * 40,
            expected_manifest_sha256="c" * 64,
        )
        validate_artifact.assert_called_once_with(
            release_root / "releases/0.1.15/cloudx-cloud.pyz"
        )

    def test_selector_change_fails_before_acceptance(self) -> None:
        changed = dict(SELECTORS, previousVersion="0.1.15")
        with mock.patch.object(stage.os, "geteuid", return_value=0), mock.patch.object(
            stage, "_validate_release_root"
        ), mock.patch.object(
            stage, "_transaction_lock", return_value=nullcontext()
        ), mock.patch.object(
            stage, "_fetch_bundle", return_value=(b"bundle", "a" * 40)
        ), mock.patch.object(
            stage.cloud_release, "stage_pinned_compatibility", return_value=dict(STAGED)
        ), mock.patch.object(
            stage, "_selector_snapshot", side_effect=(dict(SELECTORS), changed)
        ), mock.patch.object(stage, "_validate_staged_artifact") as validate_artifact:
            with self.assertRaisesRegex(RuntimeError, "selectors changed"):
                stage._apply("0.1.15", "repo", IDENTITY)
        validate_artifact.assert_not_called()

    def test_main_emits_apply_receipt_only_after_exact_confirmation(self) -> None:
        receipt = {
            "schema": "cloudx.legacy-health-bridge-artifact-stage.v1",
            "status": "staged",
        }
        output = StringIO()
        with mock.patch.object(stage, "_apply", return_value=receipt) as apply, redirect_stdout(output):
            self.assertEqual(stage.main([
                "--release-version",
                "0.1.15",
                "--repository",
                "repo",
                "--apply",
                "--confirm",
                stage.confirmation("0.1.15"),
            ]), 0)
        self.assertEqual(json.loads(output.getvalue()), receipt)
        apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()
