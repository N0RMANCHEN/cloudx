from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_release_refs import copy_http_auth, publish  # noqa: E402


def git(command, cwd: pathlib.Path) -> str:
    completed = subprocess.run(
        ["git", *command],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


class PublishReleaseRefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.auth_repo = self.root / "auth-repo"
        self.auth_repo.mkdir()
        git(["init", "--quiet"], self.auth_repo)
        git(
            ["config", "--local", "http.https://github.com/.extraheader", "AUTHORIZATION: basic fixture-token"],
            self.auth_repo,
        )
        self.remote = self.root / "remote.git"
        git(["init", "--bare", "--quiet", str(self.remote)], self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_checkout_http_auth_is_copied_without_becoming_content(self) -> None:
        destination = self.root / "destination"
        destination.mkdir()
        git(["init", "--quiet"], destination)
        copy_http_auth(self.auth_repo, destination)
        value = git(["config", "--local", "--get", "http.https://github.com/.extraheader"], destination)
        self.assertEqual(value, "AUTHORIZATION: basic fixture-token")

    def test_artifact_ref_is_immutable_and_stable_ref_is_replaceable(self) -> None:
        source = self.root / "source"
        source.mkdir()
        (source / "manifest.json").write_text('{"version":"0.1.0"}\n', encoding="utf-8")
        publish(
            source,
            "release-artifacts/v0.1.0",
            str(self.remote),
            "release: artifacts",
            force=False,
            auth_source=self.auth_repo,
        )
        self.assertEqual(
            git(["show", "release-artifacts/v0.1.0:manifest.json"], self.remote),
            '{"version":"0.1.0"}',
        )
        with self.assertRaises(subprocess.CalledProcessError):
            publish(
                source,
                "release-artifacts/v0.1.0",
                str(self.remote),
                "release: duplicate artifacts",
                force=False,
                auth_source=self.auth_repo,
            )

        stable = self.root / "stable"
        stable.mkdir()
        (stable / "index.json").write_text('{"version":"0.1.0","revision":1}\n', encoding="utf-8")
        publish(stable, "release/stable", str(self.remote), "release: stable 1", True, self.auth_repo)
        (stable / "index.json").write_text('{"version":"0.1.0","revision":2}\n', encoding="utf-8")
        publish(stable, "release/stable", str(self.remote), "release: stable 2", True, self.auth_repo)
        self.assertIn('"revision":2', git(["show", "release/stable:index.json"], self.remote))


if __name__ == "__main__":
    unittest.main()
