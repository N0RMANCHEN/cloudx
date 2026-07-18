from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_health  # noqa: E402


def runtime(**overrides: object) -> cpa_health.CpaRuntime:
    defaults = {
        "quarantine": mock.Mock(return_value={}),
        "refresh": mock.Mock(return_value={"actions": []}),
        "scan": mock.Mock(return_value=[]),
        "contexts": mock.Mock(return_value=[]),
        "payload_auth": mock.Mock(return_value={"tokens": {}}),
        "probe": mock.Mock(return_value=None),
        "transport": mock.Mock(return_value={"status": "reachable", "exit_code": 401}),
    }
    defaults.update(overrides)
    return cpa_health.CpaRuntime(**defaults)


class CpaHealthTests(unittest.TestCase):
    def test_probe_summary_is_aggregate_only(self) -> None:
        summary = cpa_health.summarize_probes(
            [
                {"status": "ready", "remaining_percents": [80, 70]},
                {"status": "warning", "remaining_percents": [10, 60]},
                {"status": "limited", "remaining_percents": [0, 50]},
                None,
            ],
            warning_available_accounts=1,
            checked_at="2026-07-15T09:00:00+00:00",
        )

        self.assertEqual(summary["state"], "healthy")
        self.assertEqual(summary["available"], 2)
        self.assertEqual(summary["limited"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["zero_quota"], 1)
        self.assertNotIn("token", json.dumps(summary))

    def test_all_failed_probes_fail_closed(self) -> None:
        summary = cpa_health.summarize_probes(
            [None, {"status": "login"}],
            warning_available_accounts=3,
            checked_at="2026-07-15T09:00:00+00:00",
        )
        self.assertEqual(summary["state"], "probe_error")
        self.assertEqual(summary["failed"], 2)

    def test_private_state_is_atomic_while_public_output_hides_paths(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            state_path = pathlib.Path(value) / "state/state.json"
            private = {
                "state": "low_capacity",
                "total": 2,
                "archived_files": ["account-secret.json"],
                "archive_candidates": {"/secret/account-secret.json": {"failure_count": 1}},
            }
            cpa_health.save_state(state_path, private)

            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(state_path.parent.stat().st_mode), 0o700)
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), private)
            public = cpa_health.public_summary(private)
            encoded = json.dumps(public)
            self.assertNotIn("account-secret", encoded)
            self.assertEqual(public["archived_count"], 1)
            self.assertEqual(public["pending_archive_candidates"], 1)

    def test_permanent_probe_failure_archives_immediately_with_digest_binding(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            account = pathlib.Path(value) / "account.json"
            account.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(account.read_bytes()).hexdigest()
            quarantine = mock.Mock(return_value={"moved_from": str(account)})
            active_runtime = runtime(
                quarantine=quarantine,
                scan=mock.Mock(return_value=[{"path": str(account)}]),
            )
            config = cpa_health.cloudx_config(
                pathlib.Path(value),
                pathlib.Path(value) / "archive",
                failure_confirmations=2,
            )

            archived, stale = cpa_health.archive_permanent_probe_failures(
                active_runtime,
                config,
                [{
                    "path": str(account),
                    "auth_sha256": digest,
                    "reason": "deactivated_workspace",
                }],
            )
            self.assertEqual((archived, stale), (["account.json"], 0))
            quarantine.assert_called_once()

            quarantine.reset_mock()
            account.write_text("changed", encoding="utf-8")
            archived, stale = cpa_health.archive_permanent_probe_failures(
                active_runtime,
                config,
                [{
                    "path": str(account),
                    "auth_sha256": digest,
                    "reason": "deactivated_workspace",
                }],
            )
            self.assertEqual((archived, stale), ([], 1))
            quarantine.assert_not_called()

    def test_incident_probe_uses_adaptive_high_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            contexts = []
            for index in range(33):
                path = root / ("account-%d.json" % index)
                path.write_text("{}", encoding="utf-8")
                contexts.append({
                    "path": path,
                    "state_key": str(index),
                    "payload": {"access_token": "token-%d" % index},
                })
            active = 0
            maximum = 0
            order = []
            lock = threading.Lock()
            first_wave = threading.Barrier(32)

            def probe(unused_config: object, account: dict, **unused_kwargs: object) -> dict:
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                    order.append(account["name"])
                if int(account["name"]) < 32:
                    first_wave.wait(timeout=3)
                with lock:
                    active -= 1
                return {"status": "ready", "remaining_percents": [80]}

            active_runtime = runtime(
                contexts=mock.Mock(return_value=contexts),
                payload_auth=lambda payload: payload,
                probe=probe,
            )
            summary, candidates = cpa_health.probe_accounts(
                active_runtime,
                cpa_health.cloudx_config(root, root / "archive", failure_confirmations=1),
                warning_available_accounts=1,
                probe_concurrency=32,
            )

            self.assertEqual(maximum, 32)
            self.assertEqual(len(order), 33)
            self.assertEqual(summary["probe_concurrency"], 32)
            self.assertEqual(summary["unique_probe_credentials"], 33)
            self.assertEqual(summary["probe_gate"], "reachable")
            self.assertEqual(candidates, [])

    def test_incident_probe_deduplicates_identical_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text("{}", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")
            payload = {"access_token": "same-token", "account_id": "same-account"}
            contexts = [
                {"path": first, "state_key": "first", "payload": payload},
                {"path": second, "state_key": "second", "payload": payload},
            ]
            probe = mock.Mock(return_value={
                "status": "invalid",
                "failure_reason": "deactivated_workspace",
                "permanent_auth_failure": True,
                "weekly_quota": False,
            })

            summary, candidates = cpa_health.probe_accounts(
                runtime(
                    contexts=mock.Mock(return_value=contexts),
                    payload_auth=lambda item: item,
                    probe=probe,
                ),
                cpa_health.cloudx_config(root, root / "archive", failure_confirmations=1),
                warning_available_accounts=1,
            )

            self.assertEqual(probe.call_count, 1)
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["unique_probe_credentials"], 1)
            self.assertEqual(summary["probe_concurrency"], 1)
            self.assertEqual({pathlib.Path(item["path"]).name for item in candidates}, {"first.json", "second.json"})

    def test_transport_or_provider_failure_skips_every_account_probe(self) -> None:
        active_runtime = runtime(
            contexts=mock.Mock(return_value=[{"path": "/tmp/one.json", "payload": {}}]),
            transport=mock.Mock(return_value={"status": "transport_error"}),
        )
        summary, candidates = cpa_health.probe_accounts(
            active_runtime,
            cpa_health.cloudx_config(pathlib.Path("/tmp"), pathlib.Path("/tmp/archive"), failure_confirmations=1),
            warning_available_accounts=1,
        )

        self.assertEqual(summary["probe_gate"], "transport_error")
        self.assertEqual(candidates, [])
        active_runtime.probe.assert_not_called()

    def test_mixed_bundle_never_archives_the_shared_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            account = pathlib.Path(value) / "bundle.json"
            account.write_text("{}", encoding="utf-8")
            contexts = [
                {"path": account, "state_key": "invalid", "payload": {"access_token": "invalid"}},
                {"path": account, "state_key": "ready", "payload": {"access_token": "ready"}},
            ]

            def probe(unused_config: object, selected: dict, **unused_kwargs: object) -> dict:
                if selected["name"] == "invalid":
                    return {
                        "status": "invalid",
                        "failure_reason": "deactivated_workspace",
                        "permanent_auth_failure": True,
                        "weekly_quota": False,
                    }
                return {"status": "ready", "remaining_percents": [80]}

            summary, candidates = cpa_health.probe_accounts(
                runtime(
                    contexts=mock.Mock(return_value=contexts),
                    payload_auth=lambda payload: payload,
                    probe=probe,
                ),
                cpa_health.cloudx_config(account.parent, account.parent / "archive", failure_confirmations=1),
                warning_available_accounts=1,
            )

            self.assertEqual(summary["total"], 2)
            self.assertEqual(candidates, [])

    def test_confirmed_runtime_auth_failure_archives_but_weekly_quota_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            auth_dir = root / "auth"
            failure_dir = root / "failures"
            auth_dir.mkdir()
            failure_dir.mkdir()
            account = auth_dir / "account.json"
            account.write_text('{"access_token":"sanitized"}', encoding="utf-8")
            digest = hashlib.sha256(account.read_bytes()).hexdigest()
            record = {"path": str(account)}
            quarantine = mock.Mock(return_value={"moved_from": str(account)})
            active_runtime = runtime(
                quarantine=quarantine,
                scan=mock.Mock(return_value=[record]),
            )
            config = cpa_health.cloudx_config(auth_dir, root / "archive", failure_confirmations=3)
            receipt = {
                "schema": cpa_health.FAILURE_RECEIPT_SCHEMA,
                "authFile": account.name,
                "authSha256": digest,
                "reason": "authentication_unauthorized",
                "failureCount": 1,
                "permanentAuthFailure": True,
                "weeklyQuota": False,
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }
            receipt_path = failure_dir / "accepted.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            archived, rejected, stale = cpa_health.archive_runtime_failures(
                active_runtime,
                config,
                failure_dir,
            )

            self.assertEqual((archived, rejected, stale), (["account.json"], 0, 0))
            self.assertFalse(receipt_path.exists())
            quarantine.assert_called_once_with(
                config,
                record,
                reason="runtime-authentication_unauthorized",
                moved_at=mock.ANY,
            )

            weekly = dict(receipt, weeklyQuota=True)
            (failure_dir / "weekly.json").write_text(json.dumps(weekly), encoding="utf-8")
            quarantine.reset_mock()
            archived, rejected, stale = cpa_health.archive_runtime_failures(
                active_runtime,
                config,
                failure_dir,
            )
            self.assertEqual((archived, rejected, stale), ([], 1, 0))
            quarantine.assert_not_called()

    def test_runtime_failure_receipt_is_bound_to_current_auth_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            auth_dir = root / "auth"
            failure_dir = root / "failures"
            auth_dir.mkdir()
            failure_dir.mkdir()
            account = auth_dir / "account.json"
            account.write_text("{}", encoding="utf-8")
            receipt = {
                "schema": cpa_health.FAILURE_RECEIPT_SCHEMA,
                "authFile": account.name,
                "authSha256": "0" * 64,
                "reason": "refresh_invalid_grant",
                "failureCount": 2,
                "permanentAuthFailure": True,
                "weeklyQuota": False,
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }
            (failure_dir / "stale.json").write_text(json.dumps(receipt), encoding="utf-8")
            active_runtime = runtime(scan=mock.Mock(return_value=[{"path": str(account)}]))
            config = cpa_health.cloudx_config(auth_dir, root / "archive", failure_confirmations=3)

            archived, rejected, stale = cpa_health.archive_runtime_failures(
                active_runtime,
                config,
                failure_dir,
            )

            self.assertEqual((archived, rejected, stale), ([], 0, 1))
            active_runtime.quarantine.assert_not_called()

    def test_runtime_failure_receipt_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            auth_dir = root / "auth"
            failure_dir = root / "failures"
            auth_dir.mkdir()
            failure_dir.mkdir()
            account = auth_dir / "account.json"
            account.write_text("{}", encoding="utf-8")
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (failure_dir / "receipt.json").symlink_to(outside)
            active_runtime = runtime(scan=mock.Mock(return_value=[{"path": str(account)}]))
            config = cpa_health.cloudx_config(auth_dir, root / "archive", failure_confirmations=3)

            archived, rejected, stale = cpa_health.archive_runtime_failures(
                active_runtime,
                config,
                failure_dir,
            )

            self.assertEqual((archived, rejected, stale), ([], 1, 0))
            active_runtime.quarantine.assert_not_called()

    def test_check_mode_does_not_write_or_quarantine(self) -> None:
        active_runtime = runtime(
            contexts=mock.Mock(return_value=[{"state_key": "one", "payload": {}}]),
            probe=mock.Mock(return_value={"status": "ready", "remaining_percents": [80]}),
        )
        with tempfile.TemporaryDirectory() as value:
            state_dir = pathlib.Path(value) / "state"
            args = argparse.Namespace(
                check=True,
                auth_dir=pathlib.Path(value) / "auth",
                archive_dir=pathlib.Path(value) / "archive",
                state_dir=state_dir,
                warning_available_accounts=3,
                failure_confirmations=3,
                proxy_url="",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            self.assertFalse(state_dir.exists())
            self.assertEqual(json.loads(output.getvalue())["total"], 1)
            active_runtime.refresh.assert_not_called()
            active_runtime.quarantine.assert_not_called()

    def test_runtime_failure_only_mode_archives_without_network_or_full_refresh(self) -> None:
        active_runtime = runtime()
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            args = argparse.Namespace(
                check=False,
                runtime_failures_only=True,
                auth_dir=root / "auth",
                archive_dir=root / "archive",
                state_dir=root / "state",
                failure_dir=root / "failures",
                warning_available_accounts=3,
                failure_confirmations=1,
                probe_concurrency=2,
                proxy_url="",
            )
            output = StringIO()
            with mock.patch.object(
                cpa_health,
                "archive_runtime_failures",
                return_value=(["account.json"], 0, 0),
            ), redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            document = json.loads(output.getvalue())
            self.assertEqual(document["archived_count"], 1)
            self.assertEqual(document["network_probes"], 0)
            active_runtime.refresh.assert_not_called()
            active_runtime.transport.assert_not_called()
            active_runtime.probe.assert_not_called()

    def test_automatic_maintenance_does_not_probe_without_pool_failure_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            account = root / "auth/account.json"
            account.parent.mkdir()
            account.write_text("{}", encoding="utf-8")
            active_runtime = runtime(
                contexts=mock.Mock(return_value=[{"path": account, "state_key": "one", "payload": {}}]),
            )
            args = argparse.Namespace(
                check=False,
                sweep_if_triggered=True,
                runtime_failures_only=False,
                auth_dir=account.parent,
                archive_dir=root / "archive",
                state_dir=root / "state",
                failure_dir=root / "failures",
                sweep_dir=root / "sweeps",
                warning_available_accounts=3,
                failure_confirmations=1,
                probe_concurrency=32,
                proxy_url="",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            document = json.loads(output.getvalue())
            self.assertFalse(document["sweep_triggered"])
            self.assertEqual(document["sweep_trigger_status"], "absent")
            self.assertEqual(document["probe_concurrency"], 0)
            active_runtime.transport.assert_not_called()
            active_runtime.probe.assert_not_called()

    def test_pool_unavailable_trigger_runs_fast_sweep_and_archives_permanent_account(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            auth_dir = root / "auth"
            sweep_dir = root / "sweeps"
            auth_dir.mkdir()
            sweep_dir.mkdir()
            account = auth_dir / "account.json"
            account.write_text("{}", encoding="utf-8")
            (sweep_dir / "trigger.json").write_text(json.dumps({
                "schema": "cloudx.cpa-sweep-trigger.v1",
                "reason": "auth_unavailable",
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }), encoding="utf-8")
            quarantine = mock.Mock(return_value={"moved_from": str(account)})
            active_runtime = runtime(
                quarantine=quarantine,
                scan=mock.Mock(return_value=[{"path": str(account)}]),
                contexts=mock.Mock(return_value=[{"path": account, "state_key": "one", "payload": {}}]),
                probe=mock.Mock(return_value={
                    "status": "invalid",
                    "failure_reason": "deactivated_workspace",
                    "permanent_auth_failure": True,
                    "weekly_quota": False,
                }),
            )
            args = argparse.Namespace(
                check=False,
                sweep_if_triggered=True,
                runtime_failures_only=False,
                auth_dir=auth_dir,
                archive_dir=root / "archive",
                state_dir=root / "state",
                failure_dir=root / "failures",
                sweep_dir=sweep_dir,
                warning_available_accounts=3,
                failure_confirmations=1,
                probe_concurrency=32,
                proxy_url="",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            document = json.loads(output.getvalue())
            self.assertTrue(document["sweep_triggered"])
            self.assertEqual(document["sweep_trigger_status"], "consumed")
            self.assertEqual(document["probe_concurrency"], 1)
            self.assertEqual(document["probe_failure_archived_count"], 1)
            self.assertFalse((sweep_dir / "trigger.json").exists())
            quarantine.assert_called_once()

    def test_infrastructure_failure_retains_sweep_trigger_without_account_probe(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            auth_dir = root / "auth"
            sweep_dir = root / "sweeps"
            auth_dir.mkdir()
            sweep_dir.mkdir()
            account = auth_dir / "account.json"
            account.write_text("{}", encoding="utf-8")
            (sweep_dir / "trigger.json").write_text(json.dumps({
                "schema": "cloudx.cpa-sweep-trigger.v1",
                "reason": "auth_unavailable",
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }), encoding="utf-8")
            active_runtime = runtime(
                contexts=mock.Mock(return_value=[{"path": account, "state_key": "one", "payload": {}}]),
                transport=mock.Mock(return_value={"status": "provider_error"}),
            )
            args = argparse.Namespace(
                check=False,
                sweep_if_triggered=True,
                runtime_failures_only=False,
                auth_dir=auth_dir,
                archive_dir=root / "archive",
                state_dir=root / "state",
                failure_dir=root / "failures",
                sweep_dir=sweep_dir,
                warning_available_accounts=3,
                failure_confirmations=1,
                probe_concurrency=32,
                proxy_url="",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            document = json.loads(output.getvalue())
            self.assertEqual(document["probe_gate"], "provider_error")
            self.assertEqual(document["sweep_trigger_status"], "retained")
            self.assertTrue((sweep_dir / "trigger.json").exists())
            active_runtime.probe.assert_not_called()

    def test_full_network_probe_does_not_hold_the_archive_lock(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            account = root / "auth/account.json"
            account.parent.mkdir()
            account.write_text("{}", encoding="utf-8")
            probe_started = threading.Event()
            finish_probe = threading.Event()
            lock_acquired = threading.Event()
            failures = []

            def probe(unused_config: object, unused_account: dict, **unused_kwargs: object) -> dict:
                probe_started.set()
                if not finish_probe.wait(timeout=3):
                    raise RuntimeError("probe release timed out")
                return {"status": "ready", "remaining_percents": [80]}

            active_runtime = runtime(
                contexts=mock.Mock(return_value=[{"path": account, "state_key": "one", "payload": {}}]),
                probe=probe,
            )
            args = argparse.Namespace(
                check=False,
                runtime_failures_only=False,
                auth_dir=account.parent,
                archive_dir=root / "archive",
                state_dir=root / "state",
                failure_dir=root / "failures",
                warning_available_accounts=3,
                failure_confirmations=1,
                probe_concurrency=2,
                proxy_url="",
            )

            def run_health() -> None:
                try:
                    cpa_health.run(args, runtime=active_runtime)
                except Exception as exc:  # pragma: no cover - asserted below
                    failures.append(exc)

            def take_lock() -> None:
                with cpa_health.monitor_lock(args.state_dir):
                    lock_acquired.set()

            with mock.patch.object(cpa_health, "emit_json"):
                health = threading.Thread(target=run_health)
                health.start()
                self.assertTrue(probe_started.wait(timeout=2))
                contender = threading.Thread(target=take_lock)
                contender.start()
                acquired_during_probe = lock_acquired.wait(timeout=1)
                finish_probe.set()
                health.join(timeout=3)
                contender.join(timeout=3)

            self.assertTrue(acquired_during_probe)
            self.assertFalse(health.is_alive())
            self.assertEqual(failures, [])

    def test_default_runtime_uses_only_native_cloudx_modules(self) -> None:
        active_runtime = cpa_health.native_runtime()
        for callback in (
            active_runtime.quarantine,
            active_runtime.refresh,
            active_runtime.scan,
            active_runtime.contexts,
            active_runtime.payload_auth,
            active_runtime.probe,
            active_runtime.transport,
        ):
            self.assertTrue(callback.__module__.startswith("cloudx_cloud.cpa_"))

    def test_restore_requires_exact_confirmation_and_redacts_filename(self) -> None:
        args = argparse.Namespace(
            selector="private-account.json",
            confirm="different.json",
            auth_dir=pathlib.Path("/tmp/auth"),
            archive_dir=pathlib.Path("/tmp/archive"),
        )
        with self.assertRaisesRegex(cpa_health.CpaHealthUnavailable, "confirmation"):
            cpa_health.restore_run(args)

        args.confirm = args.selector
        output = StringIO()
        with mock.patch.object(cpa_health.cpa_auth, "restore_quarantined_auth", return_value={}), redirect_stdout(output):
            self.assertEqual(cpa_health.restore_run(args), 0)
        rendered = output.getvalue()
        self.assertNotIn("private-account", rendered)
        self.assertEqual(json.loads(rendered)["restored_count"], 1)


if __name__ == "__main__":
    unittest.main()
