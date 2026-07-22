from __future__ import annotations

import base64
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.importer import ImportRejected, import_records, normalize, read_limited  # noqa: E402


def record(suffix: str = "one") -> dict:
    return {
        "type": "codex",
        "email": "%s@example.test" % suffix,
        "access_token": "access.%s.value" % suffix,
        "refresh_token": "refresh.%s.value" % suffix,
        "id_token": "id.%s.value" % suffix,
        "account_id": "account-%s" % suffix,
    }


def agent_record(suffix: str = "one", seed_byte: int = 1) -> dict:
    prefix = bytes.fromhex("302e020100300506032b657004220420")
    return {
        "auth_mode": "agentIdentity",
        "agent_runtime_id": "runtime-%s" % suffix,
        "agent_private_key": base64.b64encode(prefix + bytes([seed_byte]) * 32).decode("ascii"),
        "task_id": "task-from-another-gateway",
        "id_token": "synthetic.%s.unsigned" % suffix,
        "chatgpt_account_id": "account-%s" % suffix,
        "chatgpt_user_id": "user-%s" % suffix,
        "workspace_id": "workspace-%s" % suffix,
        "email": "%s@example.test" % suffix,
        "plan_type": "plus",
    }


class ImportNormalizationTests(unittest.TestCase):
    def test_flat_record(self) -> None:
        values = normalize(json.dumps(record()).encode())
        self.assertEqual(values[0]["type"], "codex")
        self.assertEqual(values[0]["account_id"], "account-one")

    def test_accounts_and_result_accounts(self) -> None:
        for source in (
            {"accounts": [record()]},
            {"result": {"accounts": [record()]}},
            {"payload": {"accounts": [record()]}},
        ):
            with self.subTest(source=source):
                self.assertEqual(len(normalize(json.dumps(source).encode())), 1)

    def test_sub2api_credentials_and_bundle(self) -> None:
        sub2api = {"name": "named@example.test", "credentials": record()}
        bundle = {"type": "codexx-cliproxy-auth-bundle", "files": [{"data": record()}]}
        self.assertEqual(normalize(json.dumps(sub2api).encode())[0]["email"], "one@example.test")
        self.assertEqual(len(normalize(json.dumps(bundle).encode())), 1)

    def test_openai_oauth_export_wrapper(self) -> None:
        source = {
            "type": "oauth",
            "platform": "openai",
            "credentials": {
                "email": "oauth@example.test",
                "access_token": "access.oauth.value",
                "id_token": "id.oauth.value",
                "chatgpt_account_id": "account-oauth",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        }
        values = normalize(("卡密导出\n" + json.dumps(source)).encode("utf-8"))
        self.assertEqual(values[0]["type"], "codex")
        self.assertEqual(values[0]["account_id"], "account-oauth")
        self.assertEqual(values[0]["expired"], "2030-01-01T00:00:00Z")

    def test_tokenless_agent_identity_sub2api_export_is_normalized_without_gateway_state(self) -> None:
        source = {
            "type": "sub2api-data",
            "version": 1,
            "accounts": [
                {
                    "name": "one@example.test",
                    "platform": "openai",
                    "type": "oauth",
                    "credentials": agent_record("one", 1),
                    "extra": {"source": "sub2api"},
                },
                {
                    "name": "two@example.test",
                    "platform": "openai",
                    "type": "oauth",
                    "credentials": agent_record("two", 2),
                    "extra": {"source": "sub2api"},
                },
            ],
        }

        values = normalize(json.dumps(source).encode())

        self.assertEqual(len(values), 2)
        self.assertEqual(values[0]["auth_mode"], "agentIdentity")
        self.assertEqual(values[0]["auth_kind"], "oauth")
        self.assertEqual(values[0]["agent_runtime_id"], "runtime-one")
        self.assertFalse(values[0]["websockets"])
        for discarded in ("access_token", "refresh_token", "id_token", "task_id"):
            self.assertNotIn(discarded, values[0])

    def test_invalid_agent_identity_key_is_rejected_without_secret_output(self) -> None:
        credential = agent_record()
        secret = "private-but-invalid-key"
        credential["agent_private_key"] = secret

        with self.assertRaises(ImportRejected) as captured:
            normalize(json.dumps({"accounts": [{"credentials": credential}]}).encode())

        self.assertEqual(captured.exception.code, "credential_invalid")
        self.assertNotIn(secret, str(captured.exception))

    def test_non_openai_oauth_export_remains_rejected(self) -> None:
        source = {
            "type": "oauth",
            "platform": "another-provider",
            "credentials": {"access_token": "access.other.value"},
        }
        with self.assertRaises(ImportRejected) as captured:
            normalize(json.dumps(source).encode())
        self.assertEqual(captured.exception.code, "wrong_provider")

    def test_directory_envelope_and_deduplication(self) -> None:
        content = json.dumps(record())
        envelope = {
            "schema": "cloudx.import-source.v1",
            "files": [{"name": "a.json", "content": content}, {"name": "b.json", "content": content}],
        }
        self.assertEqual(len(normalize(json.dumps(envelope).encode())), 1)

    def test_missing_token_error_never_contains_source_value(self) -> None:
        secret = "never-print-this"
        with self.assertRaises(ImportRejected) as captured:
            normalize(json.dumps({"email": secret}).encode())
        self.assertNotIn(secret, str(captured.exception))

    def test_raw_card_header_remains_supported(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def read(self):
                return json.dumps(
                    {"access_token": "access.card.value", "refresh_token": "rt.new.value", "id_token": "id.card.value"}
                ).encode()

        text = "卡密导出\ncard@example.test--------app_client----rt.old.value\n"
        values = normalize(text.encode("utf-8"), opener=lambda *args, **kwargs: Response())
        self.assertEqual(values[0]["email"], "card@example.test")

    def test_size_limit(self) -> None:
        with self.assertRaises(ImportRejected) as captured:
            read_limited(io.BytesIO(b"x" * 9), limit=8)
        self.assertEqual(captured.exception.code, "source_too_large")


class ImportTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.auth = self.root / "auth"
        self.lock = self.root / "run/import.lock"
        self.raw = json.dumps(record()).encode()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_dry_run_has_no_write(self) -> None:
        result = import_records(self.raw, self.auth, self.lock, dry_run=True, force=False)
        self.assertEqual(result.written, 1)
        self.assertEqual(list(self.auth.glob("*.json")), [])

    def test_write_is_private_and_idempotent(self) -> None:
        result = import_records(self.raw, self.auth, self.lock, dry_run=False, force=False)
        self.assertEqual(result.written, 1)
        target = next(self.auth.glob("*.json"))
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        repeated = import_records(self.raw, self.auth, self.lock, dry_run=False, force=False)
        self.assertEqual(repeated.written, 0)
        self.assertEqual(repeated.skipped, 1)

    def test_unsafe_target_is_rejected(self) -> None:
        first = import_records(self.raw, self.auth, self.lock, dry_run=False, force=False)
        self.assertEqual(first.written, 1)
        target = next(self.auth.glob("*.json"))
        target.unlink()
        os.symlink(self.root / "elsewhere", target)
        with self.assertRaises(ImportRejected) as captured:
            import_records(self.raw, self.auth, self.lock, dry_run=False, force=True)
        self.assertEqual(captured.exception.code, "unsafe_target")

    def test_agent_identity_requires_live_capability_before_creating_target_state(self) -> None:
        raw = json.dumps({"accounts": [{"credentials": agent_record()}]}).encode()

        with self.assertRaises(ImportRejected) as captured:
            import_records(raw, self.auth, self.lock, dry_run=True, force=False)

        self.assertEqual(captured.exception.code, "external_capability_missing")
        self.assertFalse(self.auth.exists())
        self.assertNotIn(agent_record()["agent_private_key"], str(captured.exception))

    def test_agent_identity_write_is_private_distinct_and_idempotent_after_attestation(self) -> None:
        raw = json.dumps({
            "accounts": [
                {"credentials": agent_record("one", 1)},
                {"credentials": agent_record("two", 2)},
            ]
        }).encode()
        checked = []

        first = import_records(
            raw,
            self.auth,
            self.lock,
            dry_run=False,
            force=False,
            capability_checker=lambda capability: checked.append(capability) or "",
        )

        self.assertEqual((first.written, first.skipped), (2, 0))
        self.assertEqual(checked, ["codex-agent-identity-v1"])
        targets = sorted(self.auth.glob("*.json"))
        self.assertEqual(len(targets), 2)
        for target in targets:
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            document = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(document["auth_mode"], "agentIdentity")
            self.assertNotIn("task_id", document)
            self.assertNotIn("id_token", document)

        repeated = import_records(
            raw,
            self.auth,
            self.lock,
            dry_run=False,
            force=False,
            capability_checker=lambda unused_capability: "",
        )
        self.assertEqual((repeated.written, repeated.skipped), (0, 2))


if __name__ == "__main__":
    unittest.main()
