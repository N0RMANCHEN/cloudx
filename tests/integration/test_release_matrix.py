from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from typing import Optional, Tuple
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "local"))
sys.path.insert(0, str(ROOT / "cloud"))

import build as build_module  # noqa: E402
from cloudx_cloud import release as cloud_release  # noqa: E402
from cloudx_local import updater  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ReleaseVerificationMatrixTests(unittest.TestCase):
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

    def _sources(self, version: str) -> pathlib.Path:
        source_root = self.root / "sources" / version
        shutil.copytree(ROOT / "local", source_root / "local")
        shutil.copytree(ROOT / "cloud", source_root / "cloud")
        (source_root / "VERSION").write_text(version + "\n", encoding="utf-8")
        for component in ("local", "cloud"):
            path = source_root / component / ("cloudx_%s" % component) / "version.py"
            lines = path.read_text(encoding="utf-8").splitlines()
            lines[0] = 'VERSION = "%s"' % version
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return source_root

    def _release(
        self,
        version: str,
        artifact_version: Optional[str] = None,
        manifest_protocol: Optional[dict] = None,
    ) -> Tuple[pathlib.Path, pathlib.Path]:
        release_dir = self.root / "release" / ("%s-from-%s" % (version, artifact_version or version))
        release_dir.mkdir(parents=True)
        with mock.patch.object(build_module, "ROOT", self._sources(artifact_version or version)):
            local_artifact, cloud_artifact = build_module.build_all(release_dir)
        manifest = {
            "schema": "cloudx.release-manifest.v1",
            "product": "cloudx",
            "version": version,
            "sourceCommit": "matrix-%s" % version,
            "protocol": manifest_protocol or {"min": 1, "max": 1},
            "contracts": {"health": 1, "handshake": 1, "import": 1},
            "artifacts": [self._record(local_artifact, "local"), self._record(cloud_artifact, "cloud")],
            "activation": {"automatic": False, "serviceRestartRequired": False},
        }
        manifest_path = release_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", "cloudx-release", str(manifest_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        bundle = self.root / ("%s-from-%s.tar.gz" % (version, artifact_version or version))
        with tarfile.open(bundle, "w:gz") as archive:
            archive.add(release_dir, arcname="cloudx-%s" % version)
        return release_dir, bundle

    @staticmethod
    def _bundle_bytes(path: pathlib.Path) -> bytes:
        return path.read_bytes()

    def test_offline_bundle_downgrade_and_rollback_on_both_endpoints(self) -> None:
        unused_one, bundle_one = self._release("0.1.0")
        unused_two, bundle_two = self._release("0.2.0")
        cloud_root = self.root / "cloud-root"
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ), mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(cloud_root)}):
            local_one = updater.stage(self.config, bundle_one, local_only=True)
            cloud_one = cloud_release.stage(self._bundle_bytes(bundle_one))
            self.assertFalse((self.config.home / ".local/lib/cloudx/current").exists())
            self.assertFalse((cloud_root / "current").exists())
            self.assertEqual(local_one["local"], "staged")
            self.assertEqual(cloud_one["status"], "staged")

            updater.apply(self.config, "0.1.0", "0.1.0", True, False, None)
            cloud_release.activate("0.1.0", "0.1.0")
            updater.stage(self.config, bundle_two, local_only=True)
            cloud_release.stage(self._bundle_bytes(bundle_two))
            updater.apply(self.config, "0.2.0", "0.2.0", True, False, None)
            cloud_release.activate("0.2.0", "0.2.0")

            with self.assertRaisesRegex(RuntimeError, "downgrade"):
                updater.stage(self.config, bundle_one, local_only=True)
            with self.assertRaisesRegex(RuntimeError, "downgrade"):
                cloud_release.stage(self._bundle_bytes(bundle_one))

            updater.rollback(self.config, "0.1.0", local_only=True)
            cloud_release.rollback("0.1.0")
            self.assertEqual((self.config.home / ".local/lib/cloudx/current").resolve().name, "0.1.0")
            self.assertEqual((cloud_root / "current").resolve().name, "0.1.0")

    def test_tampering_is_rejected_on_both_endpoints(self) -> None:
        release_dir, unused_bundle = self._release("0.1.0")
        local_artifact = next(release_dir.glob("cloudx-local-*.pyz"))
        cloud_artifact = next(release_dir.glob("cloudx-cloud-*.pyz"))
        local_artifact.write_bytes(local_artifact.read_bytes() + b"tampered-local")
        cloud_artifact.write_bytes(cloud_artifact.read_bytes() + b"tampered-cloud")
        bundle = self.root / "tampered.tar.gz"
        with tarfile.open(bundle, "w:gz") as archive:
            archive.add(release_dir, arcname="cloudx-0.1.0")
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ), mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(self.root / "tampered-cloud-root")}):
            with self.assertRaisesRegex(RuntimeError, "hash"):
                updater.stage(self.config, bundle, local_only=True)
            with self.assertRaisesRegex(RuntimeError, "hash"):
                cloud_release.stage(self._bundle_bytes(bundle))

    def test_manifest_and_artifact_versions_must_match_on_both_endpoints(self) -> None:
        unused_release, bundle = self._release("0.2.0", artifact_version="0.1.0")
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ), mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(self.root / "mismatch-cloud-root")}):
            with self.assertRaisesRegex(RuntimeError, "version self-check"):
                updater.stage(self.config, bundle, local_only=True)
            with self.assertRaisesRegex(RuntimeError, "version self-check"):
                cloud_release.stage(self._bundle_bytes(bundle))

    def test_manifest_and_artifact_protocols_must_match_on_both_endpoints(self) -> None:
        unused_release, bundle = self._release("0.3.0", manifest_protocol={"min": 1, "max": 2})
        with mock.patch("cloudx_local.updater._trusted_signers", return_value=self.signers), mock.patch(
            "cloudx_cloud.release._allowed_signers", return_value=self.signers
        ), mock.patch.dict(os.environ, {"CLOUDX_RELEASE_ROOT": str(self.root / "protocol-cloud-root")}):
            with self.assertRaisesRegex(RuntimeError, "protocol self-check"):
                updater.stage(self.config, bundle, local_only=True)
            with self.assertRaisesRegex(RuntimeError, "protocol self-check"):
                cloud_release.stage(self._bundle_bytes(bundle))


if __name__ == "__main__":
    unittest.main()
