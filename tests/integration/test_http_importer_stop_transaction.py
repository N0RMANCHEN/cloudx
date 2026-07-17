from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import stop_http_importer as stop  # noqa: E402


class HttpImporterStopTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.evidence = self.root / "evidence.json"
        self.lock = self.root / "state/stop.lock"
        self.snapshot = pathlib.PurePosixPath(
            "/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z"
        )
        self.raw, self.decision = self._fresh_evidence()
        self.evidence.write_bytes(self.raw)
        self.digest = str(self.decision["evidenceDigest"])
        self.continuity = {
            "gatewayPid": 977036,
            "gatewayRestarts": 0,
            "currentSelector": "/opt/cloudx/releases/0.1.13",
            "previousSelector": "/opt/cloudx/releases/0.1.12",
        }
        self.service = {
            "loadState": "loaded",
            "activeState": "active",
            "subState": "running",
            "unitFileState": "enabled",
            "mainPid": 133756,
            "restarts": 0,
        }
        self.lock_patch = mock.patch.object(stop, "DEFAULT_LOCK", self.lock)
        self.lock_patch.start()

    def tearDown(self) -> None:
        self.lock_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _fresh_evidence() -> tuple[bytes, dict[str, object]]:
        document = json.loads(
            (ROOT / "shared/contracts/examples/http-importer-stop-gate-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        now = dt.datetime.now(dt.timezone.utc)
        document["capturedAt"] = now.isoformat().replace("+00:00", "Z")
        document["traffic"]["lastRequestAt"] = (now - dt.timedelta(seconds=30)).isoformat().replace(
            "+00:00", "Z"
        )
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return raw, dict(stop.http_importer_gate.evaluate(raw))

    @staticmethod
    def _completed(stdout: bytes = b"", returncode: int = 0) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")

    def _base_patches(self):
        return [
            mock.patch.object(stop, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(stop, "_safe_evidence", return_value=self.raw),
            mock.patch.object(stop, "_remote_gate", return_value=self.decision),
            mock.patch.object(stop, "_verify_snapshot"),
            mock.patch.object(stop, "_require_active_baseline", return_value=dict(self.service)),
            mock.patch.object(stop, "_continuity_state", return_value=dict(self.continuity)),
            mock.patch.object(stop, "_disable_importer"),
            mock.patch.object(
                stop,
                "_require_stopped",
                return_value={
                    **self.service,
                    "activeState": "inactive",
                    "subState": "dead",
                    "unitFileState": "disabled",
                    "mainPid": 0,
                },
            ),
            mock.patch.object(stop, "_ssh_import_canary"),
            mock.patch.object(stop, "_health_canaries"),
            mock.patch.object(stop, "_restore_importer"),
        ]

    def _apply_arguments(self) -> list[str]:
        return [
            "--apply",
            "--confirm",
            stop.CONFIRMATION,
            "--release-version",
            "0.1.15",
            "--evidence",
            str(self.evidence),
            "--evidence-digest",
            self.digest,
            "--rollback-snapshot",
            str(self.snapshot),
        ]

    def test_default_plan_is_non_authorizing_and_does_not_read_or_connect(self) -> None:
        output = StringIO()
        with mock.patch.object(stop, "_safe_evidence") as evidence, mock.patch.object(
            stop, "_ssh"
        ) as ssh, redirect_stdout(output):
            self.assertEqual(stop.main(["--release-version", "0.1.15"]), 0)
        evidence.assert_not_called()
        ssh.assert_not_called()
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], stop.CONFIRMATION)
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))
        self.assertIn("ssh_import_dry_run", document["canaries"])

    def test_custom_host_or_snapshot_is_rejected_even_for_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "cloud host"):
            stop.main(["--release-version", "0.1.15", "--ssh-host", "other"])
        with self.assertRaisesRegex(RuntimeError, "snapshot"):
            stop.main([
                "--release-version",
                "0.1.15",
                "--rollback-snapshot",
                "/tmp/rollback",
            ])

    def test_apply_requires_exact_confirmation_before_evidence_or_ssh(self) -> None:
        with mock.patch.object(stop, "_safe_evidence") as evidence, mock.patch.object(stop, "_ssh") as ssh:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                stop.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--release-version",
                    "0.1.15",
                ])
        evidence.assert_not_called()
        ssh.assert_not_called()

    def test_success_stops_only_importer_and_accepts_all_canaries(self) -> None:
        output = StringIO()
        patches = self._base_patches()
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(stop.main(self._apply_arguments()), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "stopped")
        self.assertEqual(document["previousPid"], 133756)
        self.assertTrue(document["listenerClosed"])
        self.assertTrue(document["sshImportDryRunAccepted"])
        self.assertTrue(document["formalHealthAccepted"])
        self.assertTrue(document["phiConsumerAccepted"])
        self.assertTrue(document["gatewayModelAccepted"])
        self.assertFalse(document["runtimeRemoved"])
        self.assertFalse(document["unitRemoved"])
        self.assertFalse(document["tokenRemoved"])
        self.assertFalse(document["gatewayRestarted"])
        self.assertFalse(document["phiServiceRestarted"])
        entered[6].assert_called_once_with()
        entered[10].assert_not_called()

    def test_post_stop_failure_restores_importer(self) -> None:
        patches = self._base_patches()
        patches[9] = mock.patch.object(stop, "_health_canaries", side_effect=RuntimeError("failed"))
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(RuntimeError, "service was restored"):
                stop.main(self._apply_arguments())
        entered[10].assert_called_once_with()

    def test_partial_disable_failure_still_attempts_restore(self) -> None:
        patches = self._base_patches()
        patches[6] = mock.patch.object(stop, "_disable_importer", side_effect=RuntimeError("partial"))
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(RuntimeError, "service was restored"):
                stop.main(self._apply_arguments())
        entered[10].assert_called_once_with()

    def test_restore_failure_is_reported_as_incomplete(self) -> None:
        patches = self._base_patches()
        patches[9] = mock.patch.object(stop, "_health_canaries", side_effect=RuntimeError("failed"))
        patches[10] = mock.patch.object(stop, "_restore_importer", side_effect=RuntimeError("restore"))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(RuntimeError, "recovery incomplete"):
                stop.main(self._apply_arguments())

    def test_fresh_gate_rejects_stale_or_wrong_digest_evidence(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "expected evidence"):
            stop._fresh_gate(self.raw, "sha256:" + "0" * 64)
        stale = json.loads(self.raw)
        stale["capturedAt"] = "2026-01-01T00:05:00Z"
        stale["traffic"]["lastRequestAt"] = "2026-01-01T00:00:00Z"
        stale_raw = json.dumps(stale, sort_keys=True, separators=(",", ":")).encode("utf-8")
        stale_digest = str(stop.http_importer_gate.evaluate(stale_raw)["evidenceDigest"])
        with self.assertRaisesRegex(RuntimeError, "not fresh"):
            stop._fresh_gate(stale_raw, stale_digest)

    def test_ssh_import_canary_accepts_preview_counts_without_writing(self) -> None:
        document = {
            "schema": "cloudx.import.v1",
            "requestId": "fixture",
            "requestHash": "0" * 64,
            "status": "accepted",
            "dryRun": True,
            "written": 1,
            "skipped": 0,
            "errors": [],
        }
        with mock.patch.object(
            stop,
            "_ssh",
            return_value=self._completed(json.dumps(document).encode("utf-8")),
        ) as ssh:
            stop._ssh_import_canary()
        self.assertEqual(ssh.call_args.args[0], ["cloudx-remote", "import", "--dry-run"])
        self.assertIn(b"fixture.stop.canary", ssh.call_args.kwargs["input_bytes"])

    def test_snapshot_manifest_requires_all_restore_artifacts(self) -> None:
        names = (
            "importer-runtime.tar.gz",
            "importer-systemd.tar.gz",
            "import-failures.tar.gz",
            "restore-plan.txt",
            "token-metadata.txt",
            "snapshot.json",
        )
        output = "\n".join("%s: OK" % name for name in names).encode("utf-8")
        with mock.patch.object(stop, "_ssh_shell", return_value=self._completed(output)):
            stop._verify_snapshot(self.snapshot)
        incomplete = b"restore-plan.txt: OK\n"
        with mock.patch.object(stop, "_ssh_shell", return_value=self._completed(incomplete)):
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                stop._verify_snapshot(self.snapshot)

    def test_evidence_reader_rejects_symlink_and_oversized_input(self) -> None:
        source = self.root / "source.json"
        source.write_bytes(b"{}")
        alias = self.root / "alias.json"
        alias.symlink_to(source)
        with self.assertRaisesRegex(RuntimeError, "unsafe"):
            stop._safe_evidence(alias)
        source.write_bytes(b"x" * (stop.http_importer_gate.MAX_EVIDENCE_BYTES + 1))
        with self.assertRaisesRegex(RuntimeError, "size limit"):
            stop._safe_evidence(source)


if __name__ == "__main__":
    unittest.main()
