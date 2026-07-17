from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local.cloud_cli import import_source, run_import  # noqa: E402


class LocalImportSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_local_file_bytes_are_the_ssh_payload(self) -> None:
        source = self.root / "credentials.json"
        raw = b'{"access_token":"fixture"}\n'
        source.write_bytes(raw)
        self.assertEqual(import_source(str(source)), raw)

    def test_local_directory_becomes_a_deterministic_text_envelope(self) -> None:
        (self.root / "b.txt").write_text("second", encoding="utf-8")
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "a.json").write_text('{"first":true}', encoding="utf-8")
        ignored = self.root / ".git"
        ignored.mkdir()
        (ignored / "secret.json").write_text("ignored", encoding="utf-8")

        document = json.loads(import_source(str(self.root)))

        self.assertEqual(document["schema"], "cloudx.import-source.v1")
        self.assertEqual(
            document["files"],
            [
                {"name": "b.txt", "content": "second"},
                {"name": "nested/a.json", "content": '{"first":true}'},
            ],
        )

    def test_symlink_source_is_not_followed(self) -> None:
        target = self.root / "target.json"
        target.write_text("{}", encoding="utf-8")
        link = self.root / "link.json"
        os.symlink(target, link)
        with self.assertRaisesRegex(RuntimeError, "regular path"):
            import_source(str(link))

    def test_missing_local_path_is_rejected_before_ssh(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not exist"):
            import_source(str(self.root / "missing.json"))

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.cloud_cli.RemoteClient")
    def test_interactive_cloud_import_has_clear_human_summary(
        self,
        remote_class: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        source = self.root / "credentials.json"
        source.write_text('{"access_token":"fixture"}', encoding="utf-8")
        remote_class.return_value.import_payload.return_value = {
            "schema": "cloudx.import.v1",
            "requestId": "26526b576b5d58b3",
            "requestHash": "0" * 64,
            "status": "accepted",
            "dryRun": False,
            "written": 1,
            "skipped": 0,
            "errors": [],
        }
        output = StringIO()

        with redirect_stdout(output):
            result = run_import(mock.sentinel.config, str(source), dry_run=False, force=False)

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Credential import",
                "  Status: succeeded",
                "  Destination: cloud gateway",
                "  Imported: 1",
                "  Skipped: 0",
                "  Verification: not performed during import; cloud health checks live account validity separately",
                "  Request ID: 26526b576b5d58b3",
            ],
        )

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.cloud_cli.RemoteClient")
    def test_interactive_cloud_rejection_reports_reason_on_stderr(
        self,
        remote_class: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        source = self.root / "credentials.json"
        source.write_text("not-json", encoding="utf-8")
        remote_class.return_value.import_payload.return_value = {
            "schema": "cloudx.import.v1",
            "requestId": "deadbeefdeadbeef",
            "requestHash": "0" * 64,
            "status": "rejected",
            "dryRun": False,
            "written": 0,
            "skipped": 0,
            "errors": [{"code": "invalid_json", "message": "import source contains invalid JSON"}],
        }
        errors = StringIO()

        with redirect_stderr(errors):
            result = run_import(mock.sentinel.config, str(source), dry_run=False, force=False)

        self.assertEqual(result, 1)
        self.assertEqual(
            errors.getvalue().splitlines(),
            [
                "Credential import",
                "  Status: failed",
                "  Destination: cloud gateway",
                "  Reason (invalid_json): import source contains invalid JSON",
                "  Imported: 0",
                "  Skipped: 0",
                "  Request ID: deadbeefdeadbeef",
            ],
        )

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.cloud_cli.RemoteClient")
    def test_json_flag_preserves_raw_cloud_contract(
        self,
        remote_class: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        source = self.root / "credentials.json"
        source.write_text('{"access_token":"fixture"}', encoding="utf-8")
        document = {
            "schema": "cloudx.import.v1",
            "requestId": "request-1234",
            "requestHash": "0" * 64,
            "status": "accepted",
            "dryRun": False,
            "written": 1,
            "skipped": 0,
            "errors": [],
        }
        remote_class.return_value.import_payload.return_value = document
        output = StringIO()

        with redirect_stdout(output):
            result = run_import(
                mock.sentinel.config,
                str(source),
                dry_run=False,
                force=False,
                json_output=True,
            )

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), document)

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.cloud_cli.RemoteClient")
    def test_interactive_dry_run_uses_preview_language(
        self,
        remote_class: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        source = self.root / "credentials.json"
        source.write_text('{"access_token":"fixture"}', encoding="utf-8")
        remote_class.return_value.import_payload.return_value = {
            "schema": "cloudx.import.v1",
            "requestId": "preview-request",
            "requestHash": "0" * 64,
            "status": "accepted",
            "dryRun": True,
            "written": 1,
            "skipped": 0,
            "errors": [],
        }
        output = StringIO()

        with redirect_stdout(output):
            result = run_import(mock.sentinel.config, str(source), dry_run=True, force=False)

        self.assertEqual(result, 0)
        self.assertIn("Status: preview succeeded (no changes written)", output.getvalue())
        self.assertIn("Would import: 1", output.getvalue())
        self.assertIn("Would skip: 0", output.getvalue())
        self.assertIn("Verification: not performed for a preview", output.getvalue())

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    @mock.patch("cloudx_local.cloud_cli.RemoteClient")
    def test_interactive_idempotent_import_explains_skip(
        self,
        remote_class: mock.Mock,
        unused_human: mock.Mock,
    ) -> None:
        source = self.root / "credentials.json"
        source.write_text('{"access_token":"fixture"}', encoding="utf-8")
        remote_class.return_value.import_payload.return_value = {
            "schema": "cloudx.import.v1",
            "requestId": "repeat-request",
            "requestHash": "0" * 64,
            "status": "accepted",
            "dryRun": False,
            "written": 0,
            "skipped": 1,
            "errors": [],
        }
        output = StringIO()

        with redirect_stdout(output):
            result = run_import(mock.sentinel.config, str(source), dry_run=False, force=False)

        self.assertEqual(result, 0)
        self.assertIn("Status: succeeded (no changes)", output.getvalue())
        self.assertIn("Imported: 0", output.getvalue())
        self.assertIn("Skipped: 1", output.getvalue())
        self.assertIn("Skip reason: 1 credential was already present and identical", output.getvalue())

    @mock.patch("cloudx_local.cloud_cli.import_ui.human_output", return_value=True)
    def test_interactive_missing_source_reports_local_failure_reason(self, unused_human: mock.Mock) -> None:
        errors = StringIO()

        with redirect_stderr(errors):
            result = run_import(
                mock.sentinel.config,
                str(self.root / "missing.json"),
                dry_run=False,
                force=False,
            )

        self.assertEqual(result, 1)
        self.assertIn("Status: failed", errors.getvalue())
        self.assertIn("Reason: import source does not exist or is not a regular path", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
