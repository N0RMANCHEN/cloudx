from __future__ import annotations

import io
import json
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_release_trust_recovery import (  # noqa: E402
    RecoveryRejected,
    SIGNER_PATHS,
    confirmation,
    main,
    plan,
    prepare,
)


@unittest.skipUnless(__import__("shutil").which("ssh-keygen"), "ssh-keygen is required")
class ReleaseTrustRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "VERSION").write_text("0.1.15\n", encoding="utf-8")
        current_key = pathlib.Path(self.temp.name) / "current-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(current_key)],
            check=True,
        )
        fields = current_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.current_signer = ("cloudx-release %s %s\n" % (fields[0], fields[1])).encode("utf-8")
        for relative in SIGNER_PATHS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.current_signer)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_plan_is_non_authorizing_and_does_not_expose_private_path(self) -> None:
        before = [(self.root / path).read_bytes() for path in SIGNER_PATHS]
        result = plan(self.root, key_configured=True)
        self.assertEqual(result["status"], "confirmation-required")
        self.assertEqual(result["confirmation"], confirmation("0.1.15"))
        self.assertFalse(result["automaticAction"])
        self.assertFalse(any(result["authorization"].values()))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(before, [(self.root / path).read_bytes() for path in SIGNER_PATHS])

    def test_prepare_generates_external_private_key_and_updates_all_public_roots(self) -> None:
        private_key = pathlib.Path(self.temp.name) / "operator" / "release-key"
        result = prepare(self.root, "0.1.15", private_key, check_git=False)
        self.assertEqual(result["status"], "prepared")
        self.assertNotEqual(result["previousFingerprint"], result["replacementFingerprint"])
        self.assertTrue(private_key.is_file())
        self.assertEqual(stat.S_IMODE(private_key.stat().st_mode), 0o600)
        values = [(self.root / path).read_bytes() for path in SIGNER_PATHS]
        self.assertEqual(len(set(values)), 1)
        self.assertNotEqual(values[0], self.current_signer)
        self.assertTrue(all(stat.S_IMODE((self.root / path).stat().st_mode) == 0o644 for path in SIGNER_PATHS))
        self.assertEqual(stat.S_IMODE(private_key.with_suffix(".pub").stat().st_mode), 0o644)
        self.assertFalse(any(result["authorization"].values()))
        rendered = json.dumps(result)
        self.assertNotIn(str(private_key), rendered)
        self.assertNotIn("PRIVATE KEY", rendered)

    def test_private_key_inside_repository_is_rejected_without_changes(self) -> None:
        with self.assertRaises(RecoveryRejected):
            prepare(self.root, "0.1.15", self.root / "private-key", check_git=False)
        self.assertEqual(
            [(self.root / path).read_bytes() for path in SIGNER_PATHS],
            [self.current_signer] * len(SIGNER_PATHS),
        )

    def test_existing_broad_private_key_directory_is_rejected_without_chmod(self) -> None:
        directory = pathlib.Path(self.temp.name) / "broad-operator"
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
        with self.assertRaisesRegex(RecoveryRejected, "already be mode 0700"):
            prepare(self.root, "0.1.15", directory / "release-key", check_git=False)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)

    def test_mismatched_public_roots_fail_closed(self) -> None:
        (self.root / SIGNER_PATHS[-1]).write_bytes(b"different\n")
        with self.assertRaisesRegex(RecoveryRejected, "differ"):
            plan(self.root)

    def test_dirty_repository_is_rejected_before_key_generation(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Cloudx Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "VERSION", *[str(path) for path in SIGNER_PATHS]], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "baseline"], check=True)
        (self.root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        private_key = pathlib.Path(self.temp.name) / "operator" / "release-key"
        with self.assertRaisesRegex(RecoveryRejected, "clean"):
            prepare(self.root, "0.1.15", private_key)
        self.assertFalse(private_key.exists())

    def test_partial_public_root_failure_restores_roots_and_removes_generated_key(self) -> None:
        private_key = pathlib.Path(self.temp.name) / "operator" / "release-key"
        from prepare_release_trust_recovery import _atomic_write as real_atomic_write

        calls = 0

        def fail_second(path: pathlib.Path, payload: bytes, mode: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated trust write failure")
            real_atomic_write(path, payload, mode)

        with mock.patch("prepare_release_trust_recovery._atomic_write", side_effect=fail_second):
            with self.assertRaises(RecoveryRejected):
                prepare(self.root, "0.1.15", private_key, check_git=False)
        self.assertEqual(
            [(self.root / path).read_bytes() for path in SIGNER_PATHS],
            [self.current_signer] * len(SIGNER_PATHS),
        )
        self.assertFalse(private_key.exists())
        self.assertFalse(private_key.with_suffix(".pub").exists())

    def test_cli_requires_exact_confirmation_before_apply(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors):
            self.assertEqual(main([
                "--apply",
                "--private-key",
                str(pathlib.Path(self.temp.name) / "operator/key"),
                "--confirm",
                "wrong",
            ], root=self.root), 1)
        self.assertIn("confirmation", errors.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([], root=self.root), 0)
        self.assertEqual(json.loads(output.getvalue())["schema"], "cloudx.release-trust-recovery-plan.v1")


if __name__ == "__main__":
    unittest.main()
