from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import stat
import sys
import tempfile
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

    def test_confirmed_login_failure_uses_reversible_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            account = pathlib.Path(value) / "account.json"
            account.write_text("{}", encoding="utf-8")
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

            archived, candidates = cpa_health.archive_confirmed_login_failures(
                active_runtime,
                config,
                [str(account)],
                {},
                confirmations=2,
            )
            self.assertEqual(archived, [])
            self.assertEqual(candidates[str(account)]["failure_count"], 1)
            archived, candidates = cpa_health.archive_confirmed_login_failures(
                active_runtime,
                config,
                [str(account)],
                {"archive_candidates": candidates},
                confirmations=2,
            )
            self.assertEqual(archived, ["account.json"])
            self.assertEqual(candidates, {})
            quarantine.assert_called_once()

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
                "failureCount": 2,
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
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cpa_health.run(args, runtime=active_runtime), 0)

            self.assertFalse(state_dir.exists())
            self.assertEqual(json.loads(output.getvalue())["total"], 1)
            active_runtime.refresh.assert_not_called()
            active_runtime.quarantine.assert_not_called()

    def test_default_runtime_uses_only_native_cloudx_modules(self) -> None:
        active_runtime = cpa_health.native_runtime()
        for callback in (
            active_runtime.quarantine,
            active_runtime.refresh,
            active_runtime.scan,
            active_runtime.contexts,
            active_runtime.payload_auth,
            active_runtime.probe,
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
