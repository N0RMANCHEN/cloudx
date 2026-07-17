from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import local_cpa_import  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


class _Response:
    def __init__(self, document: dict[str, object]):
        self.payload = json.dumps(document).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, unused_type: object, unused_value: object, unused_traceback: object) -> None:
        return None

    def read(self, unused_limit: int = -1) -> bytes:
        return self.payload


class LocalCpaImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name) / "home"
        self.home.mkdir()
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
        )
        self.auth_dir = self.home / ".cli-proxy-api"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _auth(email: str, suffix: str) -> dict[str, object]:
        return {
            "type": "codex",
            "email": email,
            "access_token": "header.%s.signature" % suffix,
            "refresh_token": "rt.%s.signature" % suffix,
            "id_token": "id.%s.signature" % suffix,
            "account_id": "account-%s" % suffix,
        }

    def _source(self, name: str, value: object) -> pathlib.Path:
        path = pathlib.Path(self.temp.name) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_flat_import_is_private_verified_and_idempotent(self) -> None:
        source = self._source("one.json", self._auth("one@example.com", "one"))
        first = local_cpa_import.import_path(self.config, source)
        self.assertEqual((first.written_files, first.verified_files, first.unchanged_files), (1, 1, 0))
        target = self.auth_dir / "codex-one-example.com.json"
        self.assertTrue(target.is_file())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["account_id"], "account-one")
        second = local_cpa_import.import_path(self.config, source)
        self.assertEqual((second.written_files, second.verified_files, second.unchanged_files), (0, 0, 1))
        self.assertEqual(second.skipped_items, 1)

    def test_directory_supports_sub2api_concatenated_json_and_deduplication(self) -> None:
        directory = pathlib.Path(self.temp.name) / "inputs"
        directory.mkdir()
        (directory / "accounts.json").write_text(
            json.dumps({
                "accounts": [
                    {
                        "name": "one@example.com",
                        "type": "openai",
                        "credentials": self._auth("one@example.com", "one"),
                    },
                    {"name": "two@example.com", "credentials": self._auth("two@example.com", "two")},
                ]
            }),
            encoding="utf-8",
        )
        (directory / "more.ndjson").write_text(
            json.dumps(self._auth("one@example.com", "one"))
            + "\n"
            + json.dumps(self._auth("three@example.com", "three")),
            encoding="utf-8",
        )
        (directory / "notes.txt").write_text("not a credential", encoding="utf-8")
        result = local_cpa_import.import_path(self.config, directory)
        self.assertEqual(result.discovered_files, 3)
        self.assertEqual(result.ignored_files, 1)
        self.assertEqual(result.parsed_objects, 4)
        self.assertEqual(result.duplicate_objects, 1)
        self.assertEqual(result.written_files, 3)
        self.assertEqual(result.verified_files, 3)

    def test_bundle_and_json_array_formats_are_preserved(self) -> None:
        bundle = self._source("bundle.json", {
            "type": local_cpa_import.CLIPROXY_AUTH_BUNDLE_TYPE,
            "files": [
                {"relative_path": "one.json", "data": self._auth("one@example.com", "one")},
                {"relative_path": "two.json", "data": self._auth("two@example.com", "two")},
            ],
        })
        result = local_cpa_import.import_path(self.config, bundle)
        self.assertEqual((result.parsed_objects, result.written_files), (2, 2))
        array = self._source("array.json", [
            self._auth("three@example.com", "three"),
            self._auth("four@example.com", "four"),
        ])
        result = local_cpa_import.import_path(self.config, array)
        self.assertEqual((result.parsed_objects, result.written_files), (2, 2))

    def test_dry_run_has_no_filesystem_or_refresh_side_effect(self) -> None:
        source = self._source("one.json", self._auth("one@example.com", "one"))
        result = local_cpa_import.import_path(self.config, source, dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.written_files, 1)
        self.assertFalse(self.auth_dir.exists())
        card = pathlib.Path(self.temp.name) / "card.txt"
        card.write_text("one@example.com--------app_client----rt.refresh.signature\n", encoding="utf-8")
        opener = mock.Mock(side_effect=AssertionError("dry-run must not refresh"))
        result = local_cpa_import.import_path(self.config, card, dry_run=True, url_opener=opener)
        self.assertEqual(result.written_files, 1)
        opener.assert_not_called()

    def test_raw_card_apply_refreshes_without_exposing_the_refresh_token(self) -> None:
        card = pathlib.Path(self.temp.name) / "card.txt"
        secret = "rt.private.signature"
        card.write_text("one@example.com--------app_client----%s\n" % secret, encoding="utf-8")
        opener = mock.Mock(return_value=_Response({
            "access_token": "header.payload.signature",
            "refresh_token": "rt.rotated.signature",
            "id_token": "id.payload.signature",
        }))
        result = local_cpa_import.import_path(self.config, card, url_opener=opener)
        self.assertEqual((result.written_files, result.verified_files), (1, 1))
        target = self.auth_dir / "codex-one-example.com.json"
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["refresh_token"], "rt.rotated.signature")
        request = opener.call_args.args[0]
        self.assertNotIn(secret, str(request.headers))

    def test_conflict_requires_force_false_and_default_force_overwrites_atomically(self) -> None:
        first = self._source("first.json", self._auth("one@example.com", "one"))
        second = self._source("second.json", self._auth("one@example.com", "two"))
        local_cpa_import.import_path(self.config, first)
        with self.assertRaisesRegex(local_cpa_import.LocalImportError, "already exists") as caught:
            local_cpa_import.import_path(self.config, second, force=False)
        self.assertEqual(caught.exception.code, "target_conflict")
        target = self.auth_dir / "codex-one-example.com.json"
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["account_id"], "account-one")
        local_cpa_import.import_path(self.config, second)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["account_id"], "account-two")

    def test_partial_write_failure_rolls_back_every_new_auth_file(self) -> None:
        source = self._source("array.json", [
            self._auth("one@example.com", "one"),
            self._auth("two@example.com", "two"),
        ])
        real_atomic_write = local_cpa_import.atomic_write
        calls = 0

        def fail_second(path: pathlib.Path, payload: bytes, mode: int = 0o600) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated write failure")
            real_atomic_write(path, payload, mode)

        with mock.patch("cloudx_local.local_cpa_import.atomic_write", side_effect=fail_second):
            with self.assertRaises(local_cpa_import.LocalImportError) as caught:
                local_cpa_import.import_path(self.config, source)
        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(list(self.auth_dir.glob("*.json")), [])

    def test_symlink_and_oversized_sources_fail_closed(self) -> None:
        source = self._source("one.json", self._auth("one@example.com", "one"))
        link = pathlib.Path(self.temp.name) / "linked.json"
        link.symlink_to(source)
        with self.assertRaises(local_cpa_import.LocalImportError) as caught:
            local_cpa_import.import_path(self.config, link)
        self.assertEqual(caught.exception.code, "source_unsafe")
        oversized = pathlib.Path(self.temp.name) / "large.json"
        with oversized.open("wb") as handle:
            handle.truncate(local_cpa_import.MAX_SOURCE_BYTES + 1)
        with self.assertRaises(local_cpa_import.LocalImportError) as caught:
            local_cpa_import.import_path(self.config, oversized)
        self.assertEqual(caught.exception.code, "source_too_large")

    def test_auth_directory_cannot_enter_cloudx_release_or_state(self) -> None:
        source = self._source("one.json", self._auth("one@example.com", "one"))
        for forbidden in (
            self.home / ".local/lib/cloudx/releases/auth",
            self.config.state_dir / "auth",
        ):
            config = replace(self.config, local_cpa_auth_dir=forbidden)
            with self.assertRaises(local_cpa_import.LocalImportError) as caught:
                local_cpa_import.import_path(config, source)
            self.assertEqual(caught.exception.code, "target_unsafe")

    def test_config_load_accepts_explicit_external_local_cpa_auth_directory(self) -> None:
        config_path = self.home / ".config/cloudx/config.json"
        config_path.parent.mkdir(parents=True)
        expected = self.home / "external-cpa-auth"
        config_path.write_text(json.dumps({"localCpa": {"authDir": str(expected)}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {
            "CLOUDX_USER_HOME": str(self.home),
            "CLOUDX_CONFIG": str(config_path),
        }, clear=False):
            loaded = LocalConfig.load()
        self.assertEqual(loaded.local_cpa_auth_dir, expected)


if __name__ == "__main__":
    unittest.main()
