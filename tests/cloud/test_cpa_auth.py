from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_auth  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/cpa_auth/production-direct-sanitized.json"


def configured(root: pathlib.Path, *, confirmations: int = 3) -> dict:
    auth_dir = root / "auth"
    auth_dir.mkdir(mode=0o700)
    return {
        "cliproxy": {
            "account_name": "api",
            "auth_dir": str(auth_dir),
            "quarantine_dir": str(root / "archive"),
            "failure_confirmations": confirmations,
        }
    }


def install_fixture(config: dict, name: str = "account.json") -> pathlib.Path:
    path = pathlib.Path(config["cliproxy"]["auth_dir"]) / name
    path.write_bytes(FIXTURE.read_bytes())
    path.chmod(0o600)
    return path


class CpaAuthTests(unittest.TestCase):
    def test_sanitized_production_shape_builds_one_native_context(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            config = configured(pathlib.Path(value))
            path = install_fixture(config)

            contexts = cpa_auth.auth_contexts(config, "api")
            records = cpa_auth.scan_auth_records(config)

            self.assertEqual(len(contexts), 1)
            self.assertEqual(contexts[0]["path"], path)
            auth = cpa_auth.payload_auth(contexts[0]["payload"])
            self.assertTrue(auth["tokens"]["access_token"].startswith("header."))
            self.assertNotIn("refresh_token", auth["tokens"])
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["has_access_token"])
            self.assertFalse(records[0]["has_refresh_token"])

    def test_nested_tokens_and_sub2api_bundle_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            config = configured(pathlib.Path(value))
            auth_dir = pathlib.Path(config["cliproxy"]["auth_dir"])
            nested = {
                "type": "codex",
                "tokens": {
                    "access_token": "header.eyJleHAiOjQxMDI0NDQ4MDB9.signature",
                    "refresh_token": "refresh-sanitized",
                    "account_id": "nested-sanitized",
                },
            }
            bundle = {
                "accounts": [
                    {
                        "name": "first@example.invalid",
                        "credentials": {
                            "access_token": "header.eyJleHAiOjQxMDI0NDQ4MDB9.one",
                            "chatgpt_account_id": "bundle-one",
                        },
                    },
                    {
                        "name": "second@example.invalid",
                        "credentials": {
                            "access_token": "header.eyJleHAiOjQxMDI0NDQ4MDB9.two",
                            "account_id": "bundle-two",
                        },
                    },
                ]
            }
            (auth_dir / "nested.json").write_text(json.dumps(nested), encoding="utf-8")
            (auth_dir / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

            contexts = cpa_auth.auth_contexts(config, "api")
            self.assertEqual(len(contexts), 3)
            self.assertEqual(
                sorted(cpa_auth.auth_account_id(item["payload"]) for item in contexts),
                ["bundle-one", "bundle-two", "nested-sanitized"],
            )

    def test_symlink_and_oversized_files_are_not_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            config = configured(root)
            auth_dir = pathlib.Path(config["cliproxy"]["auth_dir"])
            outside = root / "outside.json"
            outside.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            (auth_dir / "linked.json").symlink_to(outside)
            (auth_dir / "large.json").write_bytes(b"{" + b"x" * cpa_auth.MAX_AUTH_FILE_BYTES + b"}")

            self.assertEqual(cpa_auth.auth_contexts(config, "api"), [])
            records = cpa_auth.scan_auth_records(config)
            self.assertEqual(
                sorted(record["reason"] for record in records),
                ["auth-file-too-large", "auth-file-unreadable"],
            )
            self.assertNotIn("account_sanitized", json.dumps(records))

    def test_quarantine_and_restore_are_atomic_private_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            config = configured(root)
            source = install_fixture(config)
            original = source.read_bytes()
            record = cpa_auth.scan_auth_records(config)[0]

            moved = cpa_auth.quarantine_auth_record(
                config,
                record,
                reason="confirmed-login-failure-without-refresh-token",
                moved_at="2026-07-15T10:00:00+00:00",
            )
            archive_path = pathlib.Path(moved["path"])
            manifest_path = archive_path.parent / "manifest.json"
            self.assertFalse(source.exists())
            self.assertEqual(stat.S_IMODE(archive_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o600)
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn("account@example.invalid", manifest_text)
            self.assertNotIn("account_sanitized", manifest_text)
            self.assertNotIn("header.", manifest_text)

            restored = cpa_auth.restore_quarantined_auth(config, archive_path.name)
            self.assertEqual(pathlib.Path(restored["restored"]), source)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(archive_path.exists())
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["entries"], [])

    def test_manifest_failure_rolls_the_credential_back(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            config = configured(root)
            source = install_fixture(config)
            record = cpa_auth.scan_auth_records(config)[0]

            with mock.patch.object(cpa_auth, "_atomic_write_json", side_effect=OSError("fixture failure")):
                with self.assertRaisesRegex(cpa_auth.CpaAuthRejected, "credential was restored"):
                    cpa_auth.quarantine_auth_record(
                        config,
                        record,
                        reason="invalid-auth-json",
                        moved_at="2026-07-15T10:00:00+00:00",
                    )

            self.assertTrue(source.is_file())
            archive_dir = pathlib.Path(config["cliproxy"]["quarantine_dir"])
            self.assertEqual(list(archive_dir.glob("*.json")), [])

    def test_static_invalid_record_is_quarantined_without_secret_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            config = configured(root)
            auth_dir = pathlib.Path(config["cliproxy"]["auth_dir"])
            invalid = auth_dir / "invalid.json"
            invalid.write_text("RAW-SECRET-NOT-JSON", encoding="utf-8")
            state_config = root / "state/codexx-monitor.toml"

            result = cpa_auth.refresh_auth_accounts(
                config,
                {"global_config_path": state_config},
                apply=True,
            )

            self.assertFalse(invalid.exists())
            self.assertEqual(result["actions"][0]["reason"], "invalid-auth-json")
            manifest = (root / "archive/manifest.json").read_text(encoding="utf-8")
            state = (root / "state/cliproxy-refresh.json").read_text(encoding="utf-8")
            self.assertNotIn("RAW-SECRET", manifest)
            self.assertNotIn("RAW-SECRET", state)
            self.assertEqual(stat.S_IMODE((root / "state/cliproxy-refresh.json").stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
