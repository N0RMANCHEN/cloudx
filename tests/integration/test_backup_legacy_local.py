from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from backup_legacy_local import candidate_paths, create_backup  # noqa: E402


class LegacyLocalBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, value: bytes, mode: int = 0o600) -> pathlib.Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        path.chmod(mode)
        return path

    def test_backup_copies_api_cpa_and_entrypoints_without_manifest_secrets(self) -> None:
        secret = b"must-not-appear-in-manifest"
        self.write(".local/bin/codexx", b"legacy", 0o755)
        self.write(".codex-accounts/api/.codex/auth.json", secret)
        self.write(".codex-accounts/cpa/.codex/config.toml", b"cpa")
        self.write(".cli-proxy-api/account.json", b"credential")
        destination = self.home / ".local/state/cloudx/legacy-backups/test"

        result = create_backup(self.home, destination)

        self.assertEqual(result["status"], "created")
        self.assertEqual((destination / "home/.codex-accounts/api/.codex/auth.json").read_bytes(), secret)
        manifest = (destination / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(secret.decode(), manifest)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((destination / "manifest.json").stat().st_mode), 0o600)

    def test_symlink_source_is_rejected(self) -> None:
        target = self.write("target", b"value")
        link = self.home / ".local/bin/codexx"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "regular file"):
            create_backup(self.home, self.home / "backup")

    def test_candidates_include_only_top_level_cpa_files(self) -> None:
        self.write(".cli-proxy-api/account.json", b"credential")
        self.write(".cli-proxy-api/logs/error.log", b"log")
        values = {path.relative_to(self.home).as_posix() for path in candidate_paths(self.home)}
        self.assertIn(".cli-proxy-api/account.json", values)
        self.assertNotIn(".cli-proxy-api/logs/error.log", values)


if __name__ == "__main__":
    unittest.main()
