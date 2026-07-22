from __future__ import annotations

import base64
import contextlib
import io
import json
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import promote_cloud_agent_identity_batch as promotion  # noqa: E402


REQUEST_SHA = "a" * 64


def agent_record(seed: int = 1) -> dict:
    prefix = bytes.fromhex("302e020100300506032b657004220420")
    return {
        "type": "codex",
        "auth_kind": "oauth",
        "auth_mode": "agentIdentity",
        "disabled": False,
        "websockets": False,
        "agent_runtime_id": "runtime-%d" % seed,
        "agent_private_key": base64.b64encode(prefix + bytes([seed]) * 32).decode("ascii"),
    }


class CloudAgentIdentityPromotionTests(unittest.TestCase):
    def test_plan_is_non_authorizing_and_exact(self) -> None:
        document = promotion.plan(REQUEST_SHA, 1, 10)
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["requiredCpaVersion"], "7.2.71-cloudx-policy.7")
        self.assertEqual(
            document["requiredCpaSha256"],
            "0a3b146dc607bf58aa648d0b80f4df3d81737103799593cbae501e843f7e8d80",
        )
        self.assertEqual(document["activeAfter"], 11)
        self.assertEqual(document["cohortCanaryRequests"], 10)
        self.assertTrue(document["baselineTemporarilyHeldForCohortCanary"])
        self.assertTrue(document["manualRecoveryPreparedBeforeMutation"])
        self.assertFalse(document["rawCredentialStored"])
        self.assertFalse(document["serviceRestarted"])

    @mock.patch("promote_cloud_agent_identity_batch._apply")
    def test_wrong_confirmation_reads_no_input(self, apply_call: mock.Mock) -> None:
        stream = mock.Mock()
        with self.assertRaisesRegex(promotion.Rejected, "confirmation"):
            promotion.main([
                "--expected-request-sha256", REQUEST_SHA,
                "--expected-active-before", "1",
                "--expected-new", "10",
                "--apply",
                "--confirm", "wrong",
            ], stream=stream)
        stream.read.assert_not_called()
        apply_call.assert_not_called()

    def test_input_is_hash_bound_and_bounded(self) -> None:
        raw = b"credential"
        digest = __import__("hashlib").sha256(raw).hexdigest()
        self.assertEqual(promotion.read_input(io.BytesIO(raw), digest), raw)
        with self.assertRaisesRegex(promotion.Rejected, "confirmed request"):
            promotion.read_input(io.BytesIO(raw), REQUEST_SHA)

    def test_agent_record_validation_is_private_and_strict(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = pathlib.Path(value) / "agent.json"
            path.write_text(json.dumps(agent_record()), encoding="utf-8")
            path.chmod(0o600)
            fingerprint = promotion._agent_fingerprint(path)
            self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")
            document = agent_record()
            document["access_token"] = "SECRET-TOKEN-SENTINEL"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(promotion.Rejected) as caught:
                promotion._agent_fingerprint(path)
            self.assertNotIn("SECRET-TOKEN-SENTINEL", str(caught.exception))

    def test_promoted_records_must_be_distinct_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            one = root / "one.json"
            two = root / "two.json"
            for path in (one, two):
                path.write_text(json.dumps(agent_record()), encoding="utf-8")
                path.chmod(0o600)
            uid = one.stat().st_uid
            gid = one.stat().st_gid
            with self.assertRaisesRegex(promotion.Rejected, "not distinct"):
                promotion._validate_promoted([one, two], 2, uid, gid)

    @mock.patch("promote_cloud_agent_identity_batch._recover_existing")
    def test_recovery_requires_exact_confirmation_without_stdin(self, recover: mock.Mock) -> None:
        transaction = "20260722T120000Z-abcdef12"
        stream = mock.Mock()
        with self.assertRaisesRegex(promotion.Rejected, "confirmation"):
            promotion.main(["--recover", transaction, "--apply", "--confirm", "wrong"], stream=stream)
        stream.read.assert_not_called()
        recover.assert_not_called()

    def test_unexpected_apply_failure_runs_automatic_recovery(self) -> None:
        transaction = pathlib.Path("/tmp/20260722T120000Z-abcdef12")
        baseline = {
            "sidecar": {},
            "binary": pathlib.Path("/tmp/cpa"),
            "activeMap": {"baseline.json": "b" * 64},
            "cliproxyUid": 1,
            "cliproxyGid": 1,
            "service": {"MainPID": "1", "NRestarts": "0"},
        }
        lock = contextlib.nullcontext()
        with (
            mock.patch("promote_cloud_agent_identity_batch._transaction_lock", return_value=lock),
            mock.patch("promote_cloud_agent_identity_batch._preflight", return_value=baseline),
            mock.patch("promote_cloud_agent_identity_batch._prepare_transaction", return_value=transaction),
            mock.patch("promote_cloud_agent_identity_batch._attestation_copy", return_value=pathlib.Path("/tmp/attestation")),
            mock.patch("promote_cloud_agent_identity_batch._signed_import", side_effect=OSError("fixture")),
            mock.patch("promote_cloud_agent_identity_batch._rollback", return_value={"status": "recovered"}) as rollback,
            mock.patch("promote_cloud_agent_identity_batch._cleanup_attestation"),
            mock.patch.object(promotion.base, "atomic_json"),
        ):
            with self.assertRaises(promotion.Rejected) as caught:
                promotion._apply(b"credential", REQUEST_SHA, 1, 10, "127.0.0.1", 8317)
        self.assertEqual(caught.exception.code, "transaction_error")
        self.assertTrue(caught.exception.result["baselineRestored"])
        rollback.assert_called_once()

    def test_script_remains_executable_and_below_governance_limit(self) -> None:
        path = ROOT / "scripts/promote_cloud_agent_identity_batch.py"
        self.assertTrue(stat.S_IMODE(path.stat().st_mode) & stat.S_IXUSR)
        self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 800)


if __name__ == "__main__":
    unittest.main()
