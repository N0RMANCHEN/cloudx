from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_sweep  # noqa: E402


class CpaSweepTests(unittest.TestCase):
    def test_trigger_is_fresh_strict_and_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            now = datetime.now(timezone.utc)
            path = root / cpa_sweep.TRIGGER_NAME
            path.write_text(json.dumps({
                "schema": cpa_sweep.TRIGGER_SCHEMA,
                "reason": "auth_unavailable",
                "observedAt": now.isoformat(),
            }), encoding="utf-8")

            trigger, status = cpa_sweep.load_trigger(root, now=now)
            self.assertEqual(status, "accepted")
            self.assertIsNotNone(trigger)
            path.write_text(json.dumps({
                "schema": cpa_sweep.TRIGGER_SCHEMA,
                "reason": "auth_unavailable",
                "observedAt": (now + timedelta(seconds=1)).isoformat(),
            }), encoding="utf-8")
            self.assertFalse(cpa_sweep.consume_trigger(trigger))  # type: ignore[arg-type]
            self.assertTrue(path.exists())

    def test_stale_or_symlink_trigger_never_authorizes_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            now = datetime.now(timezone.utc)
            path = root / cpa_sweep.TRIGGER_NAME
            path.write_text(json.dumps({
                "schema": cpa_sweep.TRIGGER_SCHEMA,
                "reason": "auth_unavailable",
                "observedAt": (now - timedelta(hours=1)).isoformat(),
            }), encoding="utf-8")
            self.assertEqual(cpa_sweep.load_trigger(root, now=now), (None, "stale"))

            path.unlink()
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            path.symlink_to(outside)
            self.assertEqual(cpa_sweep.load_trigger(root, now=now), (None, "rejected"))

    def test_pool_observation_contains_only_aggregate_state(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            (root / cpa_sweep.POOL_NAME).write_text(json.dumps({
                "schema": cpa_sweep.POOL_SCHEMA,
                "state": "available",
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }), encoding="utf-8")
            observation = cpa_sweep.load_pool_observation(root)
            self.assertEqual(observation["state"], "available")  # type: ignore[index]
            self.assertEqual(set(observation), {"state", "observed_at"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
