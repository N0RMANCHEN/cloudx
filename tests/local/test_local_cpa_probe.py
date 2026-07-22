from __future__ import annotations

import base64
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import local_cpa_probe  # noqa: E402


def token(index: int) -> str:
    payload = json.dumps({
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "index": index,
    }).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return "header.%s.signature-%d" % (encoded, index)


class LocalCpaProbeTests(unittest.TestCase):
    def test_agent_identity_is_not_sent_to_bearer_usage_probe(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            auth_dir = pathlib.Path(value)
            private_key = base64.b64encode(
                bytes.fromhex("302e020100300506032b657004220420") + bytes([9]) * 32
            ).decode("ascii")
            (auth_dir / "agent.json").write_text(json.dumps({
                "type": "codex",
                "auth_mode": "agentIdentity",
                "agent_runtime_id": "runtime-sanitized",
                "agent_private_key": private_key,
            }), encoding="utf-8")

            with mock.patch.object(local_cpa_probe, "transport_status") as transport:
                summary, candidates = local_cpa_probe.probe_all(
                    auth_dir,
                    "",
                    32,
                    opener=mock.Mock(),
                )

            self.assertEqual(summary, {
                "gate": "no_accounts",
                "total": 0,
                "concurrency": 0,
                "failed": 0,
            })
            self.assertEqual(candidates, [])
            transport.assert_not_called()

    def test_incident_sweep_uses_up_to_thirty_two_unique_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            auth_dir = pathlib.Path(value)
            for index in range(33):
                (auth_dir / ("account-%d.json" % index)).write_text(json.dumps({
                    "type": "codex",
                    "access_token": token(index),
                }), encoding="utf-8")
            active = 0
            maximum = 0
            lock = threading.Lock()
            first_wave = threading.Barrier(32)

            def probe(payload: dict, unused_opener: object) -> dict:
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                if int(json.loads(base64.urlsafe_b64decode(
                    payload["access_token"].split(".")[1] + "=="
                ))["index"]) < 32:
                    first_wave.wait(timeout=3)
                with lock:
                    active -= 1
                return {"status": "ready"}

            with mock.patch.object(local_cpa_probe, "transport_status", return_value="reachable"), mock.patch.object(
                local_cpa_probe,
                "_probe",
                side_effect=probe,
            ):
                summary, candidates = local_cpa_probe.probe_all(
                    auth_dir,
                    "",
                    32,
                    opener=mock.Mock(),
                )

            self.assertEqual(maximum, 32)
            self.assertEqual(summary["concurrency"], 32)
            self.assertEqual(summary["available"], 33)
            self.assertEqual(candidates, [])

    def test_identical_credentials_are_probed_once_but_both_files_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            auth_dir = pathlib.Path(value)
            payload = {"type": "codex", "access_token": token(1)}
            (auth_dir / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (auth_dir / "two.json").write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(local_cpa_probe, "transport_status", return_value="reachable"), mock.patch.object(
                local_cpa_probe,
                "_probe",
                return_value={
                    "status": "invalid",
                    "reason": "deactivated_workspace",
                    "permanent": True,
                    "weekly_quota": False,
                },
            ) as probe:
                summary, candidates = local_cpa_probe.probe_all(
                    auth_dir,
                    "",
                    32,
                    opener=mock.Mock(),
                )

            self.assertEqual(probe.call_count, 1)
            self.assertEqual(summary["uniqueCredentials"], 1)
            self.assertEqual(len(candidates), 2)

    def test_quota_and_refreshable_unauthorized_are_never_permanent(self) -> None:
        quota = local_cpa_probe._classified_failure(429, b'{"error":"weekly quota"}', False)
        refreshable = local_cpa_probe._classified_failure(401, b'{"error":"expired"}', True)
        permanent = local_cpa_probe._classified_failure(
            402,
            b'{"error":{"code":"deactivated_workspace"}}',
            False,
        )
        self.assertEqual(quota, {"status": "limited"})
        self.assertEqual(refreshable, {"status": "login"})
        self.assertTrue(permanent["permanent"])  # type: ignore[index]
        self.assertFalse(permanent["weekly_quota"])  # type: ignore[index]
        self.assertTrue(local_cpa_probe._rate_limited({
            "weekly_window": {"remaining_percent": 0},
        }))


if __name__ == "__main__":
    unittest.main()
