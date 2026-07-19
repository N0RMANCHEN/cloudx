from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import accept_cloud_cpa_failure_policy as wrapper  # noqa: E402
import cloud_cpa_failure_policy_transaction as transaction  # noqa: E402


class CloudCpaFailurePolicyWrapperTests(unittest.TestCase):
    @staticmethod
    def _completed(stdout: bytes = b"", returncode: int = 0) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")

    def test_default_plan_is_non_authorizing_and_offline(self) -> None:
        output = StringIO()
        with mock.patch.object(wrapper, "_tool_bytes") as tool, mock.patch.object(wrapper, "_quota_bundle") as quota, mock.patch.object(
            wrapper, "_ssh"
        ) as ssh, redirect_stdout(output):
            self.assertEqual(wrapper.main([]), 0)
        tool.assert_not_called()
        quota.assert_not_called()
        ssh.assert_not_called()
        document = json.loads(output.getvalue())
        self.assertEqual(document["confirmation"], wrapper.CONFIRMATION)
        self.assertEqual(document["businessConcurrencyMaximum"], 2)
        self.assertEqual(document["incidentProbeConcurrencyMinimum"], 3)
        self.assertEqual(document["requiredCloudCpaPolicyVersion"], "7.2.71-cloudx-policy.5")
        self.assertFalse(document["cpaRestartAuthorized"])
        self.assertFalse(document["automaticAction"])

    def test_apply_requires_exact_confirmation_before_tool_or_ssh(self) -> None:
        with mock.patch.object(wrapper, "_tool_bytes") as tool, mock.patch.object(wrapper, "_quota_bundle") as quota, mock.patch.object(wrapper, "_ssh") as ssh:
            with self.assertRaisesRegex(wrapper.AcceptanceRejected, "confirmation"):
                wrapper.main(["--apply", "--confirm", "wrong"])
        tool.assert_not_called()
        quota.assert_not_called()
        ssh.assert_not_called()

    def test_remote_tool_upload_is_digest_bound_and_root_only(self) -> None:
        raw = b"#!/usr/bin/env python3\nprint('safe')\n"
        digest = hashlib.sha256(raw).hexdigest()
        responses = [self._completed(), self._completed((digest + "\n").encode("ascii"))]
        with mock.patch.object(wrapper, "_tool_bytes", return_value=raw), mock.patch.object(
            wrapper, "_ssh", side_effect=responses
        ) as ssh:
            target = wrapper._install_remote_tool(wrapper.DEFAULT_SSH_HOST)
        self.assertIn(digest[:16], str(target))
        self.assertIn("0700", ssh.call_args_list[0].args[1])
        self.assertEqual(ssh.call_args_list[1].kwargs["input_bytes"], raw)

    def test_ssh_shell_quotes_python_code_as_one_remote_command(self) -> None:
        completed = self._completed(b"ok")
        with mock.patch.object(wrapper.subprocess, "run", return_value=completed) as run:
            result = wrapper._ssh("cloud", ["python3", "-c", "print('safe value')"])
        self.assertEqual(result.stdout, b"ok")
        remote = run.call_args.args[0][-1]
        self.assertIn("'print('\"'\"'safe value'\"'\"')'", remote)
        self.assertEqual(run.call_args.args[0].count("-c"), 0)

    def test_custom_cloud_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(wrapper.AcceptanceRejected, "fixed"):
            wrapper.main(["--ssh-host", "other"])

    def test_apply_streams_quota_bundle_only_after_confirmation(self) -> None:
        bundle = b'{"schema":"cloudx.cpa-quota-samples.v1","samples":[]}'
        accepted = json.dumps({"status": "accepted"}).encode("utf-8")
        with mock.patch.object(wrapper, "_quota_bundle", return_value=bundle), mock.patch.object(
            wrapper, "_install_remote_tool", return_value=pathlib.PurePosixPath("/private/tool.py")
        ), mock.patch.object(wrapper, "_ssh", return_value=self._completed(accepted)) as ssh, redirect_stdout(StringIO()):
            self.assertEqual(wrapper.main(["--apply", "--confirm", wrapper.CONFIRMATION]), 0)
        self.assertEqual(ssh.call_args.kwargs["input_bytes"], bundle)

    def test_quota_bundle_requires_three_distinct_samples(self) -> None:
        bundle = wrapper._encode_quota_samples([b'{"a":1}', b'{"a":2}', b'{"a":3}'])
        self.assertEqual(json.loads(bundle)["schema"], "cloudx.cpa-quota-samples.v1")
        with self.assertRaisesRegex(wrapper.AcceptanceRejected, "distinct"):
            wrapper._encode_quota_samples([b"same", b"same", b"other"])


class CloudCpaFailurePolicyTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.auth = self.root / "auth"
        self.archive = self.root / "archive"
        self.failure = self.root / "failure"
        self.sweep = self.root / "sweep"
        self.state = self.root / "state"
        self.transactions = self.root / "transactions"
        for path in (self.auth, self.archive, self.failure, self.sweep, self.state, self.transactions):
            path.mkdir(mode=0o700)
        self.patches = [
            mock.patch.object(transaction, "AUTH_DIR", self.auth),
            mock.patch.object(transaction, "ARCHIVE_DIR", self.archive),
            mock.patch.object(transaction, "FAILURE_DIR", self.failure),
            mock.patch.object(transaction, "SWEEP_DIR", self.sweep),
            mock.patch.object(transaction, "STATE_DIR", self.state),
            mock.patch.object(transaction, "TRANSACTION_ROOT", self.transactions),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def _archive_manifest(self, count: int = 45) -> None:
        entries = [{"source_relative": "old-%d.json" % index, "quarantine_name": "old-%d.json" % index} for index in range(count)]
        (self.archive / "manifest.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")

    def _transaction(self, *, phase: str = "limited-active") -> tuple[pathlib.Path, dict[str, object]]:
        root = self.transactions / "fixture"
        for name in ("hold/active", "hold/sweep", "staged", "evidence"):
            (root / name).mkdir(parents=True, mode=0o700)
        baseline = b"real-active-credential"
        pool = b'{"schema":"cloudx.cpa-pool-observation.v1","state":"available","observedAt":"2026-07-18T00:00:00Z"}\n'
        (root / "hold/active/active.json").write_bytes(baseline)
        (root / "hold/sweep/pool-state.json").write_bytes(pool)
        for index in range(1, 4):
            (self.auth / (transaction.CANARY_PREFIX + "%d.json" % index)).write_bytes(b"quota-%d" % index)
        (self.sweep / "pool-state.json").write_bytes(b'{"state":"unavailable"}\n')
        service = {"MainPID": 123, "NRestarts": 0, "ActiveState": "active", "SubState": "running"}
        manifest: dict[str, object] = {
            "schema": transaction.RESULT_SCHEMA,
            "transactionId": root.name,
            "phase": phase,
            "activeName": "active.json",
            "activeDigest": hashlib.sha256(baseline).hexdigest(),
            "sweep": {"pool-state.json": hashlib.sha256(pool).hexdigest()},
            "stateDigest": "0" * 64,
            "canaries": {transaction.CANARY_PREFIX + "%d.json" % index: "0" * 64 for index in range(1, 4)},
            "archiveCount": 45,
            "service": service,
            "cliproxyUid": os.getuid(),
            "cliproxyGid": os.getgid(),
            "rawCredentialTemporarilyStored": True,
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root, manifest

    def test_recovery_restores_active_credential_and_watcher_baseline(self) -> None:
        self._archive_manifest()
        root, manifest = self._transaction()
        with mock.patch.object(transaction, "_service_state", return_value=manifest["service"]), mock.patch.object(
            transaction, "_live_canary", return_value={"status": 200, "policy": 2}
        ), mock.patch.object(transaction.time, "sleep"), mock.patch.object(transaction.os, "chown"):
            result = transaction._recover(root)
        self.assertTrue(result["activeRestored"])
        self.assertEqual((self.auth / "active.json").read_bytes(), b"real-active-credential")
        self.assertFalse(any(path.name.startswith(transaction.CANARY_PREFIX) for path in self.auth.iterdir()))
        self.assertIn(b'"state":"available"', (self.sweep / "pool-state.json").read_bytes())
        self.assertEqual(json.loads((root / "manifest.json").read_text())["phase"], "recovered")
        self.assertTrue((root / "evidence/post-sweep-pool-state.json").is_file())

    def test_recovery_is_idempotent_after_success(self) -> None:
        self._archive_manifest()
        root, manifest = self._transaction(phase="recovered")
        shutil_target = self.auth / "active.json"
        shutil_target.write_bytes(b"real-active-credential")
        for path in list(self.auth.glob(transaction.CANARY_PREFIX + "*.json")):
            path.unlink()
        with mock.patch.object(transaction, "_service_state", return_value=manifest["service"]):
            result = transaction._recover(root)
        self.assertTrue(result["alreadyRecovered"])

    def test_real_quota_sweep_requires_zero_archive(self) -> None:
        root = self.transactions / "quota"
        (root / "evidence").mkdir(parents=True)
        source = self.root / "quota-source.json"
        source.write_text('{"type":"codex","access_token":"a.b.c"}', encoding="utf-8")
        signed = {
            "probe_gate": "reachable", "sweep_triggered": True, "sweep_trigger_status": "consumed",
            "probe_concurrency": 1, "limited": 1, "archived_count": 0,
        }
        with mock.patch.object(transaction, "_signed_health", return_value=signed):
            result = transaction._isolated_sweep(root, "quota", source)
        self.assertEqual(result["limited"], 1)
        self.assertEqual(result["archived"], 0)
        self.assertFalse((root / "isolated/quota").exists())

    def test_provisional_refreshable_401_remains_in_place(self) -> None:
        root = self.transactions / "provisional"
        (root / "evidence").mkdir(parents=True)
        signed = {
            "probe_gate": "reachable", "sweep_triggered": True, "sweep_trigger_status": "consumed",
            "probe_concurrency": 1, "failed": 1, "archived_count": 0,
        }
        with mock.patch.object(transaction, "_signed_health", return_value=signed):
            result = transaction._isolated_sweep(root, "provisional")
        self.assertTrue(result["provisional401"])
        self.assertEqual(result["archived"], 0)

    def test_permanent_401_archives_exactly_one_and_restores_digest(self) -> None:
        root = self.transactions / "permanent"
        (root / "evidence").mkdir(parents=True)

        def signed(arguments: list[str]) -> dict[str, object]:
            auth = root / "isolated/permanent/auth/permanent-canary.json"
            archive = root / "isolated/permanent/archive"
            if arguments[0] == "cpa-health":
                archived = archive / auth.name
                os.replace(auth, archived)
                (archive / "manifest.json").write_text(json.dumps({"entries": [{
                    "source_relative": auth.name, "quarantine_name": archived.name,
                }]}), encoding="utf-8")
                return {
                    "probe_gate": "reachable", "sweep_triggered": True, "sweep_trigger_status": "consumed",
                    "probe_concurrency": 1, "invalid": 1, "probe_failure_archived_count": 1,
                }
            os.replace(archive / auth.name, auth)
            (archive / "manifest.json").write_text('{"entries":[]}', encoding="utf-8")
            return {"status": "restored", "restored_count": 1}

        with mock.patch.object(transaction, "_signed_health", side_effect=signed):
            result = transaction._isolated_sweep(root, "permanent")
        self.assertEqual(result["permanentArchived"], 1)
        self.assertTrue(result["digestMatched"])
        self.assertEqual(result["restored"], 1)

    def test_natural_aggregate_requires_probe_concurrency_above_business_limit(self) -> None:
        self._archive_manifest()
        root = self.transactions / "aggregate"
        (root / "evidence").mkdir(parents=True)
        (root / "manifest.json").write_text(json.dumps({"stateDigest": "0" * 64}), encoding="utf-8")
        state = {
            "sweep_triggered": True, "sweep_trigger_status": "consumed", "probe_gate": "reachable",
            "probe_concurrency": 3, "limited": 3, "archived_count": 0,
            "probe_failure_archived_count": 0, "runtime_failure_archived_count": 0,
        }
        (self.state / "state.json").write_text(json.dumps(state), encoding="utf-8")
        response = (429, {"x-cpa-max-concurrent-api-requests": "2"}, b'{"error":{"code":"model_cooldown"}}')
        with mock.patch.object(transaction, "_models", return_value=["fixture-model"]), mock.patch.object(
            transaction, "_request", return_value=response
        ):
            result = transaction._natural_aggregate(root)
        self.assertEqual(result["businessPolicy"], 2)
        self.assertEqual(result["sweepProbeConcurrency"], 3)
        self.assertEqual(result["archived"], 0)
        self.assertTrue(result["aggregateTriggerObserved"])
        self.assertFalse(result["responseAuthUnavailableObserved"])

    def test_failed_live_phase_invokes_prebuilt_recovery(self) -> None:
        root = self.transactions / "failed"
        root.mkdir()
        baseline = {"service": {"MainPID": 1, "NRestarts": 0}}
        recovered = {"activeRestored": True}
        with mock.patch.object(transaction, "_transaction_lock", return_value=nullcontext()), mock.patch.object(
            transaction, "_preflight", return_value=baseline
        ), mock.patch.object(transaction, "_prepare_transaction", return_value=root), mock.patch.object(
            transaction, "_isolated_sweep", return_value={"limited": 1}
        ), mock.patch.object(transaction, "_activate_limited", side_effect=transaction.AcceptanceRejected("boom", "failed")), mock.patch.object(
            transaction, "_recover", return_value=recovered
        ) as recovery:
            with self.assertRaisesRegex(transaction.AcceptanceRejected, "restored"):
                transaction._remote_apply([b'{"a":1}', b'{"a":2}', b'{"a":3}'])
        recovery.assert_called_once_with(root)
        receipt = json.loads((root / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "failed-recovered")
        self.assertFalse(receipt["serviceRestarted"])

    def test_recovery_tool_self_test_is_executable(self) -> None:
        self.assertEqual(transaction._remote_self_test()["status"], "passed")

    def test_remote_quota_contract_is_bounded_distinct_and_exactly_three(self) -> None:
        samples = [b'{"sample":1}', b'{"sample":2}', b'{"sample":3}']
        raw = wrapper._encode_quota_samples(samples)
        self.assertEqual(transaction._quota_samples(raw), samples)
        duplicate = wrapper._encode_quota_samples([b'{"sample":1}', b'{"sample":2}', b'{"sample":3}'])
        document = json.loads(duplicate)
        document["samples"][2] = document["samples"][1]
        with self.assertRaisesRegex(transaction.AcceptanceRejected, "distinct"):
            transaction._quota_samples(json.dumps(document).encode("utf-8"))
        with self.assertRaisesRegex(transaction.AcceptanceRejected, "exactly three"):
            transaction._quota_samples(b'{"schema":"cloudx.cpa-quota-samples.v1","samples":[]}')


if __name__ == "__main__":
    unittest.main()
