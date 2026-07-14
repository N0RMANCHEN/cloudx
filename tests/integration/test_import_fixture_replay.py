from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from replay_import_fixtures import main, replay  # noqa: E402


class ImportFixtureReplayTests(unittest.TestCase):
    def test_fixture_matrix_matches_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            result = replay(root)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["fixtures"], 8)
            self.assertEqual(result["idempotentReplays"], 8)
            self.assertFalse(result["rawSourcesRetained"])
            self.assertEqual(list(root.iterdir()), [])

    def test_explicit_root_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            output = StringIO()
            error = StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["--shadow-root", value, "--confirm-shadow-root", value + "-wrong"])
            self.assertEqual(code, 1)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("confirmation does not match", error.getvalue())

    def test_default_cli_output_is_secret_free(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.import-fixture-check.v1")
        serialized = output.getvalue()
        for forbidden in ("fixture.access", "fixture.refresh", "fixture.id", "@fixture.invalid"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
