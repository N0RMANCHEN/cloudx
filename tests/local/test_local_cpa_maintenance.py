from __future__ import annotations

import hashlib
import json
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import codexx_cli, local_cpa_maintenance  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


class LocalCpaMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name) / "home"
        self.home.mkdir()
        self.auth_dir = self.home / ".cli-proxy-api"
        self.archive_dir = self.home / ".cli-proxy-api-archive"
        self.failure_dir = self.home / ".local/state/cloudx/cpa-auth-failures"
        self.config = LocalConfig(
            home=self.home,
            config_path=self.home / ".config/cloudx/config.json",
            state_dir=self.home / ".local/state/cloudx",
            data_dir=self.home / ".local/share/cloudx",
            cache_dir=self.home / ".cache/cloudx",
            accounts_dir=self.home / ".codex-accounts",
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
            local_cpa_auth_dir=self.auth_dir,
            local_cpa_archive_dir=self.archive_dir,
            local_cpa_failure_dir=self.failure_dir,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_auth(self, name: str, document: dict[str, object]) -> pathlib.Path:
        self.auth_dir.mkdir(mode=0o700, exist_ok=True)
        path = self.auth_dir / name
        path.write_text(json.dumps(document), encoding="utf-8")
        path.chmod(0o600)
        return path

    @staticmethod
    def _auth(*, refresh: bool = True, expired: bool = False) -> dict[str, object]:
        expires_at = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=1))
        return {
            "type": "codex",
            "access_token": "header.payload.signature",
            "refresh_token": "refresh.sanitized" if refresh else "",
            "expired": expires_at.isoformat(),
        }

    def _receipt(
        self,
        auth: pathlib.Path,
        *,
        reason: str = "authentication_unauthorized",
        weekly: bool = False,
        digest: str = "",
        failures: int = 2,
    ) -> pathlib.Path:
        self.failure_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        receipt = self.failure_dir / (hashlib.sha256(auth.name.encode("utf-8")).hexdigest() + ".json")
        receipt.write_text(
            json.dumps({
                "schema": local_cpa_maintenance.FAILURE_SCHEMA,
                "authFile": auth.name,
                "authSha256": digest or hashlib.sha256(auth.read_bytes()).hexdigest(),
                "reason": reason,
                "failureCount": failures,
                "permanentAuthFailure": True,
                "weeklyQuota": weekly,
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }),
            encoding="utf-8",
        )
        receipt.chmod(0o600)
        return receipt

    def test_expired_access_with_refresh_and_nested_files_are_never_archived(self) -> None:
        active = self._write_auth("active.json", self._auth(refresh=True, expired=True))
        nested = self.auth_dir / ".archive"
        nested.mkdir()
        (nested / "missing.json").write_text("{}", encoding="utf-8")

        document = local_cpa_maintenance.refresh_document(self.config, apply=True)

        self.assertTrue(active.is_file())
        self.assertTrue((nested / "missing.json").is_file())
        self.assertEqual(document["activeAuthFiles"], 1)
        self.assertEqual(document["eligibleForArchive"], 0)
        self.assertEqual(document["nestedAuthDirectoriesScanned"], 0)
        self.assertFalse(self.archive_dir.exists())

    def test_missing_tokens_are_archived_atomically_without_secret_output(self) -> None:
        missing = self._write_auth("missing.json", {"type": "codex", "label": "private-label"})

        document = local_cpa_maintenance.refresh_document(self.config, apply=True)

        self.assertFalse(missing.exists())
        self.assertEqual(document["archived"], 1)
        self.assertEqual(stat.S_IMODE(self.archive_dir.stat().st_mode), 0o700)
        manifest = json.loads((self.archive_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["entries"][0]["reason"], "missing-refresh-and-access-token")
        self.assertNotIn("private-label", json.dumps(document))
        self.assertNotIn("private-label", json.dumps(manifest))

    def test_confirmed_non_quota_runtime_failure_archives_exact_auth_digest(self) -> None:
        auth = self._write_auth("runtime.json", self._auth())
        receipt = self._receipt(auth)

        document = local_cpa_maintenance.refresh_document(self.config, apply=True)

        self.assertEqual(document["archived"], 1)
        self.assertFalse(auth.exists())
        self.assertFalse(receipt.exists())
        manifest = json.loads((self.archive_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["entries"][0]["reason"], "runtime-authentication_unauthorized")

    def test_weekly_quota_and_stale_digest_never_archive(self) -> None:
        weekly = self._write_auth("weekly.json", self._auth())
        stale = self._write_auth("stale.json", self._auth())
        self._receipt(weekly, weekly=True)
        self._receipt(stale, digest="0" * 64)

        document = local_cpa_maintenance.refresh_document(self.config, apply=True)

        self.assertTrue(weekly.is_file())
        self.assertTrue(stale.is_file())
        self.assertEqual(document["archived"], 0)
        self.assertEqual(document["weeklyQuotaArchived"], 0)
        self.assertEqual(document["rejectedFailureReceipts"], 1)
        self.assertEqual(document["staleFailureReceipts"], 1)

    def test_manifest_failure_restores_auth(self) -> None:
        auth = self._write_auth("missing.json", {"type": "codex"})
        with mock.patch.object(local_cpa_maintenance, "atomic_json", side_effect=OSError("fixture")):
            with self.assertRaisesRegex(
                local_cpa_maintenance.LocalCpaMaintenanceRejected,
                "credentials were restored",
            ):
                local_cpa_maintenance.refresh_document(self.config, apply=True)
        self.assertTrue(auth.is_file())

    def test_restore_requires_exact_archive_name(self) -> None:
        auth = self._write_auth("missing.json", {"type": "codex"})
        local_cpa_maintenance.refresh_document(self.config, apply=True)
        archive_name = next(
            entry.name
            for entry in self.archive_dir.glob("*.json")
            if entry.name != "manifest.json"
        )
        with self.assertRaisesRegex(local_cpa_maintenance.LocalCpaMaintenanceRejected, "confirmation"):
            local_cpa_maintenance.restore_run(self.config, [archive_name, "--confirm", "wrong.json"])
        self.assertFalse(auth.exists())
        with redirect_stdout(StringIO()):
            self.assertEqual(
                local_cpa_maintenance.restore_run(
                    self.config,
                    [archive_name, "--confirm", archive_name],
                ),
                0,
            )
        self.assertTrue(auth.is_file())

    def test_restore_rejects_missing_archive_and_manifest_path_escape(self) -> None:
        with self.assertRaisesRegex(
            local_cpa_maintenance.LocalCpaMaintenanceRejected,
            "archive directory",
        ):
            local_cpa_maintenance.restore_run(
                self.config,
                ["missing.json", "--confirm", "missing.json"],
            )

        self.archive_dir.mkdir(mode=0o700)
        (self.archive_dir / "manifest.json").write_text(
            json.dumps({
                "schema": local_cpa_maintenance.MANIFEST_SCHEMA,
                "entries": [{
                    "sourceName": "../outside.json",
                    "archiveName": "inside.json",
                }],
            }),
            encoding="utf-8",
        )
        (self.archive_dir / "inside.json").write_text("{}", encoding="utf-8")
        self.auth_dir.mkdir(mode=0o700)
        with self.assertRaisesRegex(
            local_cpa_maintenance.LocalCpaMaintenanceRejected,
            "manifest paths",
        ):
            local_cpa_maintenance.restore_run(
                self.config,
                ["inside.json", "--confirm", "inside.json"],
            )

    def test_codexx_api_refresh_compatibility_dispatches_to_maintenance(self) -> None:
        with mock.patch.object(LocalConfig, "load", return_value=self.config), mock.patch.object(
            local_cpa_maintenance,
            "refresh_run",
            return_value=0,
        ) as refresh:
            self.assertEqual(codexx_cli.main(["api", "refresh", "--apply"]), 0)
        refresh.assert_called_once_with(self.config, ["--apply"])


if __name__ == "__main__":
    unittest.main()
