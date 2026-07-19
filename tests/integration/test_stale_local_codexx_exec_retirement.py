from __future__ import annotations

import json
import pathlib
import signal
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import retire_stale_local_codexx_exec as retirement  # noqa: E402


class StaleLocalCodexxExecRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = pathlib.Path("/Users/tester")
        self.parent = retirement.Process(
            pid=101,
            ppid=1,
            pgid=101,
            started_at=1,
            tty="??",
            state="S",
            cpu=0.0,
            command="/python /Users/tester/.local/bin/codexx.py exec",
        )
        self.child = retirement.Process(
            pid=102,
            ppid=101,
            pgid=101,
            started_at=1,
            tty="??",
            state="R",
            cpu=99.0,
            command="/opt/homebrew/bin/codex",
        )
        self.cpa = retirement.Process(
            pid=200,
            ppid=1,
            pgid=200,
            started_at=1,
            tty="??",
            state="S",
            cpu=0.0,
            command="/Users/tester/.local/bin/cli-proxy-api",
        )
        self.processes = [self.parent, self.child, self.cpa]
        self.target = retirement.Target(self.parent, self.child)
        self.contract = retirement._stable_contract([self.target], self.cpa.pid)
        self.digest = retirement._digest(self.contract)

    def _decision(self) -> dict[str, object]:
        return {
            "schema": "cloudx.stale-local-codexx-exec-decision.v1",
            "status": "retirement-ready",
            "decisionDigest": self.digest,
            "targetCount": 1,
            "targetPids": [101],
            "childPids": [102],
            "minimumAgeSeconds": retirement.MIN_AGE_SECONDS,
            "stdioRevoked": True,
            "networkSockets": 0,
            "minimumObservedCpuPercent": retirement.MIN_CPU_PERCENT,
            "localCpaPid": 200,
            "localCpaChanged": False,
            "irreversibleProcessTerminationRequired": True,
            "contract": self.contract,
        }

    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(retirement, "decision") as decision, redirect_stdout(output):
            self.assertEqual(retirement.main([]), 0)
        decision.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/stale-local-codexx-exec-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertEqual(document["confirmation"], retirement.CONFIRMATION)
        self.assertFalse(any(document["authorization"].values()))
        self.assertFalse(document["automaticAction"])

    def test_check_reports_bound_decision_without_private_commands(self) -> None:
        output = StringIO()
        with mock.patch.object(retirement, "decision", return_value=self._decision()), redirect_stdout(output):
            self.assertEqual(retirement.main(["--check"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "retirement-ready")
        self.assertEqual(document["decisionDigest"], self.digest)
        self.assertNotIn("contract", document)

    def test_apply_requires_confirmation_before_process_inspection(self) -> None:
        with mock.patch.object(retirement, "decision") as decision:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                retirement.main([
                    "--apply",
                    "--confirm",
                    "wrong",
                    "--decision-digest",
                    self.digest,
                ])
        decision.assert_not_called()

    def test_success_sends_only_sigterm_and_preserves_cpa(self) -> None:
        output = StringIO()
        after = [self.cpa]
        with mock.patch.object(retirement, "decision", return_value=self._decision()), mock.patch.object(
            retirement, "user_home", return_value=self.home
        ), mock.patch.object(
            retirement, "_processes", side_effect=[self.processes, after]
        ), mock.patch.object(
            retirement, "_targets", return_value=[self.target]
        ), mock.patch.object(
            retirement, "_terminate"
        ) as terminate, mock.patch.object(
            retirement, "_local_cpa", return_value=200
        ), redirect_stdout(output):
            self.assertEqual(retirement.main([
                "--apply",
                "--confirm",
                retirement.CONFIRMATION,
                "--decision-digest",
                self.digest,
            ]), 0)
        terminate.assert_called_once_with([self.target])
        document = json.loads(output.getvalue())
        self.assertEqual(document["signal"], "SIGTERM")
        self.assertFalse(document["sigkillSent"])
        self.assertFalse(document["localCpaChanged"])

    def test_apply_rejects_changed_decision(self) -> None:
        document = self._decision()
        document["decisionDigest"] = "sha256:" + "0" * 64
        with mock.patch.object(retirement, "decision", return_value=document):
            with self.assertRaisesRegex(RuntimeError, "changed"):
                retirement.main([
                    "--apply",
                    "--confirm",
                    retirement.CONFIRMATION,
                    "--decision-digest",
                    self.digest,
                ])

    def test_terminate_never_escalates_to_sigkill(self) -> None:
        alive = {101, 102}

        def killpg(pgid: int, sent: signal.Signals) -> None:
            self.assertEqual(pgid, 101)
            self.assertEqual(sent, signal.SIGTERM)
            alive.clear()

        with mock.patch.object(retirement.os, "killpg", side_effect=killpg), mock.patch.object(
            retirement, "_alive", side_effect=lambda pid: pid in alive
        ):
            retirement._terminate([self.target])


if __name__ == "__main__":
    unittest.main()
