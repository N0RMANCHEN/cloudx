from __future__ import annotations

import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from install_scoped_gateway_key import CONFIRMATION, append_api_key, main, top_level_value  # noqa: E402


CONFIG = b"""# gateway\nhost: 100.90.97.113\nport: 8317\napi-keys:\n  - \"one\"\n  # retained comment\n  - \"two\"\nauth-dir: /var/lib/example\n"""


class ScopedKeyInstallerTests(unittest.TestCase):
    def test_append_preserves_document_and_counts_existing_keys(self) -> None:
        updated, count = append_api_key(CONFIG, "cloudx-fixture")
        self.assertEqual(count, 2)
        self.assertIn(b'  - "cloudx-fixture"\n', updated)
        self.assertIn(b"  # retained comment\n", updated)
        self.assertTrue(updated.endswith(b"auth-dir: /var/lib/example\n"))

    def test_inline_api_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "block list"):
            append_api_key(b"api-keys: [one, two]\n", "cloudx-fixture")

    def test_top_level_host_and_port_are_read_without_other_values(self) -> None:
        self.assertEqual(top_level_value(CONFIG, "host"), "100.90.97.113")
        self.assertEqual(top_level_value(CONFIG, "port"), "8317")

    def test_default_invocation_is_a_read_only_confirmation_plan(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--build-commit", "abcdef0", "--gateway-version", "7.2.71"])
        self.assertEqual(code, 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
