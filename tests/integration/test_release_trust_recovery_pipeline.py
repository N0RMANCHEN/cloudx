from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from typing import Dict, List, Optional


ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_release_trust_recovery import SIGNER_PATHS, prepare  # noqa: E402


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ReleaseTrustRecoveryPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        shutil.copy2(ROOT / "VERSION", self.source / "VERSION")
        for name in ("local", "cloud", "release"):
            shutil.copytree(ROOT / name, self.source / name)
        scripts = self.source / "scripts"
        scripts.mkdir()
        for name in (
            "build.py",
            "create_release.py",
            "create_stable_index.py",
            "release_lib.py",
            "verify_release.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_ok(
        self,
        command: List[str],
        *,
        cwd: Optional[pathlib.Path] = None,
        payload: Optional[bytes] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            command,
            cwd=str(cwd or self.source),
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr.decode("utf-8", errors="replace"),
        )
        return completed

    def test_replacement_root_builds_signs_and_stages_both_candidates(self) -> None:
        old_signers = self.root / "old-allowed-signers"
        old_signers.write_bytes((self.source / SIGNER_PATHS[0]).read_bytes())
        private_key = self.root / "operator" / "release-key"

        recovery = prepare(self.source, VERSION, private_key, check_git=False)

        self.assertEqual(recovery["status"], "prepared")
        self.assertTrue(recovery["publicRootsMatch"])
        self.assertFalse(any(recovery["authorization"].values()))
        new_signers = (self.source / SIGNER_PATHS[0]).read_bytes()
        self.assertNotEqual(new_signers, old_signers.read_bytes())
        self.assertEqual(
            [(self.source / path).read_bytes() for path in SIGNER_PATHS],
            [new_signers] * len(SIGNER_PATHS),
        )

        output = self.root / "release-output"
        self.run_ok([
            sys.executable,
            str(self.source / "scripts/create_release.py"),
            "--output",
            str(output),
            "--signing-key",
            str(private_key),
            "--allowed-signers",
            str(self.source / SIGNER_PATHS[0]),
        ])
        release = output / VERSION
        bundle = output / ("cloudx-%s-offline.tar.gz" % VERSION)
        local_artifact = release / ("cloudx-local-%s.pyz" % VERSION)
        cloud_artifact = release / ("cloudx-cloud-%s.pyz" % VERSION)
        self.assertTrue(bundle.is_file())

        with zipfile.ZipFile(local_artifact) as archive:
            self.assertEqual(archive.read("cloudx_local/data/allowed_signers"), new_signers)
        with zipfile.ZipFile(cloud_artifact) as archive:
            self.assertEqual(archive.read("cloudx_cloud/data/allowed_signers"), new_signers)

        verified = self.run_ok([
            sys.executable,
            str(self.source / "scripts/verify_release.py"),
            str(release),
            "--allowed-signers",
            str(self.source / SIGNER_PATHS[0]),
        ])
        self.assertIn(("release: verified %s" % VERSION).encode(), verified.stdout)
        old_root_result = subprocess.run(
            [
                sys.executable,
                str(self.source / "scripts/verify_release.py"),
                str(release),
                "--allowed-signers",
                str(old_signers),
            ],
            cwd=str(self.source),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(old_root_result.returncode, 0)
        self.assertIn(b"release signature verification failed", old_root_result.stderr)

        stable = self.root / "stable"
        self.run_ok([
            sys.executable,
            str(self.source / "scripts/create_stable_index.py"),
            str(release),
            "--signing-key",
            str(private_key),
            "--output",
            str(stable),
        ])
        index = json.loads((stable / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["version"], VERSION)
        self.assertEqual(
            index["manifestSha256"],
            hashlib.sha256((release / "manifest.json").read_bytes()).hexdigest(),
        )

        local_home = self.root / "local-home"
        local_home.mkdir()
        local_environment = dict(os.environ)
        local_environment.update({
            "CLOUDX_DISABLE_UPDATE_CHECK": "1",
            "CLOUDX_USER_HOME": str(local_home),
            "HOME": str(local_home),
        })
        checked = self.run_ok(
            [
                sys.executable,
                str(local_artifact),
                "update",
                "check",
                "--index-dir",
                str(stable),
            ],
            environment=local_environment,
        )
        check_document = json.loads(checked.stdout)
        self.assertEqual(check_document["available"], VERSION)
        self.assertFalse(check_document["updateAvailable"])
        self.assertFalse(check_document["activated"])

        local_first = self.run_ok(
            [
                sys.executable,
                str(local_artifact),
                "update",
                "stage",
                str(bundle),
                "--local-only",
            ],
            environment=local_environment,
        )
        local_repeat = self.run_ok(
            [
                sys.executable,
                str(local_artifact),
                "update",
                "stage",
                str(bundle),
                "--local-only",
            ],
            environment=local_environment,
        )
        self.assertEqual(json.loads(local_first.stdout)["local"], "staged")
        self.assertEqual(json.loads(local_repeat.stdout)["local"], "already-staged")

        cloud_root = self.root / "cloud-root"
        cloud_environment = dict(os.environ)
        cloud_environment["CLOUDX_RELEASE_ROOT"] = str(cloud_root)
        bundle_bytes = bundle.read_bytes()
        cloud_first = self.run_ok(
            [sys.executable, str(cloud_artifact), "release-stage"],
            payload=bundle_bytes,
            environment=cloud_environment,
        )
        cloud_repeat = self.run_ok(
            [sys.executable, str(cloud_artifact), "release-stage"],
            payload=bundle_bytes,
            environment=cloud_environment,
        )
        self.assertEqual(json.loads(cloud_first.stdout)["status"], "staged")
        self.assertEqual(json.loads(cloud_repeat.stdout)["status"], "already-staged")

        local_root = local_home / ".local/lib/cloudx"
        for root in (local_root, cloud_root):
            self.assertFalse((root / "current").exists() or (root / "current").is_symlink())
            self.assertFalse((root / "previous").exists() or (root / "previous").is_symlink())
        self.assertEqual(
            (local_root / "releases" / VERSION / "allowed_signers").read_bytes(),
            new_signers,
        )
        self.assertEqual(
            (cloud_root / "releases" / VERSION / "allowed_signers").read_bytes(),
            new_signers,
        )


if __name__ == "__main__":
    unittest.main()
