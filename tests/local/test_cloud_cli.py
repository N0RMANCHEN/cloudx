from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local.cloud_cli import import_source  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
