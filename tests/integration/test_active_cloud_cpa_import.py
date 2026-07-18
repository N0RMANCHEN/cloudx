from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import import_active_cloud_cpa_credential as transaction  # noqa: E402


class ActiveCloudCpaImportTests(unittest.TestCase):
    def test_plan_is_non_authorizing_and_exact(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(transaction.main([]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], transaction.CONFIRMATION)
        self.assertTrue(document["rawCredentialStored"] is False)
        self.assertTrue(document["serviceRestarted"] is False)
        self.assertTrue(document["requiresEmptyActivePool"])

    @mock.patch("import_active_cloud_cpa_credential.apply")
    def test_wrong_confirmation_reads_no_input(self, apply_call: mock.Mock) -> None:
        stream = mock.Mock()
        with self.assertRaisesRegex(transaction.ActiveImportRejected, "confirmation"):
            transaction.main(["--apply", "--confirm", "wrong"], stream=stream)
        stream.read.assert_not_called()
        apply_call.assert_not_called()

    def test_input_is_bounded(self) -> None:
        with self.assertRaisesRegex(transaction.ActiveImportRejected, "empty or oversized"):
            transaction.read_input(io.BytesIO(b""))
        with self.assertRaisesRegex(transaction.ActiveImportRejected, "empty or oversized"):
            transaction.read_input(io.BytesIO(b"x" * (transaction.MAX_INPUT_BYTES + 1)))

    def test_model_selection_prefers_codex(self) -> None:
        document = {"data": [{"id": "gpt-other"}, {"id": "gpt-5.2-codex"}]}
        self.assertEqual(transaction.select_model(document), "gpt-5.2-codex")

    def test_recursive_response_text_extraction(self) -> None:
        document = {"output": [{"content": [{"text": transaction.EXPECTED_TEXT}]}]}
        self.assertIn(transaction.EXPECTED_TEXT, list(transaction.strings(document)))

    def test_regular_json_files_rejects_symlink_root_and_entries(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as value:
            root = pathlib.Path(value) / "auth"
            root.mkdir()
            (root / "one.json").write_text("{}", encoding="utf-8")
            (root / "two.json").symlink_to(root / "one.json")
            self.assertEqual([path.name for path in transaction.regular_json_files(root)], ["one.json"])
            link = pathlib.Path(value) / "link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(transaction.ActiveImportRejected, "unavailable"):
                transaction.regular_json_files(link)

    @mock.patch("import_active_cloud_cpa_credential.apply", return_value={"schema": transaction.RESULT_SCHEMA, "status": "accepted"})
    def test_apply_reads_stdin_only_after_exact_confirmation(self, apply_call: mock.Mock) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                transaction.main(["--apply", "--confirm", transaction.CONFIRMATION], stream=io.BytesIO(b"credential")),
                0,
            )
        apply_call.assert_called_once_with(b"credential", "100.90.97.113", 8317)
        self.assertEqual(json.loads(output.getvalue())["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
