from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.cli import main  # noqa: E402


class CompatibilityScriptTests(unittest.TestCase):
    def test_signed_artifact_emits_non_http_import_adapter(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["compatibility-script", "codex-gateway-import"]), 0)
        script = output.getvalue()
        self.assertIn('remote=${CLOUDX_REMOTE_BIN:-cloudx-remote}', script)
        self.assertIn('"$remote" import --force --dry-run', script)
        self.assertNotIn("8780", script)
        self.assertNotIn("curl", script)
        self.assertNotIn("token", script.casefold())

    def test_file_import_preserves_force_and_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            script = root / "codex-gateway-import"
            fake = root / "cloudx-remote"
            source = root / "input.json"
            script.write_text(self._script_text(), encoding="utf-8")
            fake.write_text('#!/bin/sh\nprintf "args:%s\\n" "$*"\ncat\n', encoding="utf-8")
            source.write_text('{"synthetic":true}\n', encoding="utf-8")
            script.chmod(0o755)
            fake.chmod(0o755)
            environment = dict(os.environ)
            environment["CLOUDX_REMOTE_BIN"] = str(fake)

            completed = subprocess.run(
                [str(script), "--dry-run", "--force", str(source)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(completed.stdout, 'args:import --force --dry-run\n{"synthetic":true}\n')

    def test_stdin_import_routes_bytes_without_http(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            script = root / "codex-gateway-import"
            fake = root / "cloudx-remote"
            script.write_text(self._script_text(), encoding="utf-8")
            fake.write_text('#!/bin/sh\nprintf "args:%s\\n" "$*"\ncat\n', encoding="utf-8")
            script.chmod(0o755)
            fake.chmod(0o755)
            environment = dict(os.environ)
            environment["CLOUDX_REMOTE_BIN"] = str(fake)

            completed = subprocess.run(
                [str(script), "--dry-run", "-"],
                input="synthetic-stream\n",
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(completed.stdout, "args:import --dry-run\nsynthetic-stream\n")

    @staticmethod
    def _script_text() -> str:
        output = StringIO()
        with redirect_stdout(output):
            if main(["compatibility-script", "codex-gateway-import"]) != 0:
                raise AssertionError("compatibility script emission failed")
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
