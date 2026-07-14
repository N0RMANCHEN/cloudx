from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "local"))
sys.path.insert(0, str(ROOT / "cloud"))

from build import build_all  # noqa: E402
from cloudx_cloud import release as cloud_release  # noqa: E402
from cloudx_local import updater  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ReleaseFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.key = self.root / "key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
        )
        public = self.key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.signers = ("cloudx-release %s %s\n" % (public[0], public[1])).encode("utf-8")
        self.release_dir = self.root / "release/0.1.0"
        self.release_dir.mkdir(parents=True)
        local_artifact, cloud_artifact = build_all(self.release_dir)
        manifest = {
            "schema": "cloudx.release-manifest.v1",
            "product": "cloudx",
            "version": "0.1.0",
            "sourceCommit": "testcommit",
            "protocol": {"min": 1, "max": 1},
            "contracts": {"health": 1, "handshake": 1, "import": 1},
            "artifacts": [self._record(local_artifact, "local"), self._record(cloud_artifact, "cloud")],
            "activation": {"automatic": False, "serviceRestartRequired": False},
        }
        self.manifest = self.release_dir / "manifest.json"
        self.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", "cloudx-release", str(self.manifest)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        home = self.root / "home"
        home.mkdir()
        self.config = LocalConfig(
            home=home,
            config_path=home / ".config/cloudx/config.json",
            state_dir=home / ".local/state/cloudx",
            data_dir=home / ".local/share/cloudx",
            cache_dir=home / ".cache/cloudx",
            accounts_dir=home / ".codex-accounts",
            codex_binary="codex",
            ssh_binary="ssh",
            ssh_host="cloud",
            remote_helper="cloudx-remote",
            legacy_forward_host="gateway",
            legacy_forward_port=8317,
            legacy_api_key_command="legacy",
            broker_idle_seconds=900,
            endpoint_timeout_seconds=5.0,
            endpoint_attempts=3,
            release_repository="repo",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _record(path: pathlib.Path, component: str) -> dict:
        return {
            "name": path.name,
            "component": component,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }

    def _bundle(self) -> bytes:
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            archive.add(self.release_dir, arcname="cloudx-0.1.0")
        return output.getvalue()

    def test_local_stage_never_activates_and_apply_is_explicit(self) -> None:
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers):
            result = updater.stage(self.config, self.release_dir, local_only=True)
            local_root = self.config.home / ".local/lib/cloudx"
            self.assertEqual(result["activated"], False)
            self.assertFalse((local_root / "current").exists())
            activated = updater.apply(self.config, "0.1.0", "0.1.0", True, False, None)
        self.assertEqual(activated["status"], "active")
        self.assertEqual((local_root / "current").resolve().name, "0.1.0")
        self.assertTrue((self.config.home / ".local/bin/codexx").is_symlink())
        self.assertFalse((self.config.home / ".local/bin/codex").exists())

    def test_cloud_stage_never_activates_and_tampering_is_rejected(self) -> None:
        cloud_root = self.root / "cloud-root"
        with mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(cloud_root)}), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ):
            result = cloud_release.stage(self._bundle())
            self.assertEqual(result["status"], "staged")
            self.assertFalse((cloud_root / "current").exists())
            cloud_release.activate("0.1.0", "0.1.0")
            self.assertEqual((cloud_root / "current").resolve().name, "0.1.0")

        cloud_artifact = next(self.release_dir.glob("cloudx-cloud-*.pyz"))
        cloud_artifact.write_bytes(cloud_artifact.read_bytes() + b"tamper")
        with mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(self.root / "tampered")}), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ):
            with self.assertRaises(RuntimeError):
                cloud_release.stage(self._bundle())

    def test_signed_update_check_does_not_stage_or_activate(self) -> None:
        index_dir = self.root / "index"
        index_dir.mkdir()
        index = {
            "schema": "cloudx.release-index.v1",
            "version": "0.2.0",
            "manifestSha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "artifactRef": "refs/heads/release-artifacts/v0.2.0",
            "publishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        index_path = index_dir / "index.json"
        index_path.write_text(json.dumps(index, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", "cloudx-release", str(index_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers):
            result = updater.check(self.config, index_dir, quiet=True)
        self.assertTrue(result["updateAvailable"])
        self.assertFalse((self.config.home / ".local/lib/cloudx/current").exists())


if __name__ == "__main__":
    unittest.main()
