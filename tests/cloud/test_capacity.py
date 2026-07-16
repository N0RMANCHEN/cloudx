from __future__ import annotations

import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.capacity import classify_capacity  # noqa: E402
from cloudx_cloud.cli import main  # noqa: E402
from cloudx_cloud.gateway import GatewayProbe  # noqa: E402


def health(**changes: object) -> dict:
    document = {
        "schema": "cloudx.health.v1",
        "cloudxVersion": "0.1.15",
        "protocolVersion": 1,
        "gatewayStatus": "healthy",
        "importStatus": "ready",
        "accountCounts": {"total": 5, "available": 3, "limited": 1, "unavailable": 1},
        "checkedAt": "2026-07-16T00:00:00Z",
        "freshness": {"state": "fresh", "ageSeconds": 0},
        "accountNames": ["must-not-be-copied"],
    }
    document.update(changes)
    return document


class CapacityTests(unittest.TestCase):
    def test_capacity_states_are_distinct_and_secret_free(self) -> None:
        cases = (
            (health(), GatewayProbe("healthy", 200, "ok"), 1, 1, "healthy_capacity"),
            (
                health(accountCounts={"total": 5, "available": 0, "limited": 3, "unavailable": 2}),
                GatewayProbe("healthy", 200, "ok"),
                1,
                1,
                "exhausted_capacity",
            ),
            (
                health(freshness={"state": "unknown", "ageSeconds": 0}),
                GatewayProbe("healthy", 200, "ok"),
                1,
                1,
                "unknown_observation",
            ),
            (
                health(freshness={"state": "stale", "ageSeconds": 901}),
                GatewayProbe("healthy", 200, "ok"),
                1,
                1,
                "stale_contract",
            ),
            (health(), GatewayProbe("unavailable", None, "network"), 1, 1, "probe_failure"),
            (health(), GatewayProbe("healthy", 200, "ok"), 2, 3, "incompatible_producer"),
        )
        for document, gateway, minimum, maximum, expected in cases:
            with self.subTest(state=expected):
                result = classify_capacity(document, gateway, minimum, maximum)
                self.assertEqual(result["state"], expected)
                self.assertNotIn("must-not-be-copied", json.dumps(result))

    def test_unobserved_accounts_are_unknown_not_exhausted(self) -> None:
        document = health(accountCounts={"total": 5, "available": 0, "limited": 2, "unavailable": 1})
        result = classify_capacity(document, GatewayProbe("healthy", 200, "ok"), 1, 1)
        self.assertEqual(result["state"], "unknown_observation")
        self.assertEqual(result["reason"], "unobserved_accounts")
        self.assertEqual(result["unobservedAccounts"], 2)

    def test_probe_failure_precedes_stale_observation(self) -> None:
        document = health(freshness={"state": "stale", "ageSeconds": 901})
        result = classify_capacity(document, GatewayProbe("degraded", 401, "authentication"), 1, 1)
        self.assertEqual(result["state"], "probe_failure")
        self.assertEqual(result["reason"], "gateway_authentication_failed")

    def test_cli_emits_incompatible_capacity_without_runtime_write(self) -> None:
        observation = (health(), GatewayProbe("healthy", 200, "ok"))
        output = StringIO()
        with mock.patch("cloudx_cloud.capacity.observe_health", return_value=observation), mock.patch(
            "cloudx_cloud.cli.Config.from_environment", return_value=mock.Mock()
        ), redirect_stdout(output):
            self.assertEqual(
                main(["capacity", "--consumer-protocol-min", "2", "--consumer-protocol-max", "3"]),
                0,
            )
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.capacity.v1")
        self.assertEqual(document["state"], "incompatible_producer")

    def test_invalid_consumer_protocol_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "protocol range"):
            classify_capacity(health(), GatewayProbe("healthy", 200, "ok"), 3, 2)
        with self.assertRaisesRegex(ValueError, "protocol range"):
            classify_capacity(health(), GatewayProbe("healthy", 200, "ok"), True, 2)


if __name__ == "__main__":
    unittest.main()
