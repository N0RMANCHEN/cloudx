from __future__ import annotations

import json
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.cli import main  # noqa: E402
from cloudx_cloud.legacy_health_bridge import (  # noqa: E402
    LegacyHealthRejected,
    build_legacy_health,
    parse_formal_health,
    publish,
    read_formal_health,
    validate_legacy_health,
)


class LegacyHealthBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.formal = json.loads(
            (ROOT / "shared/contracts/examples/health.json").read_text(encoding="utf-8")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_example_is_the_exact_conservative_bridge_output(self) -> None:
        expected = json.loads(
            (ROOT / "shared/contracts/examples/legacy-health.json").read_text(encoding="utf-8")
        )
        document = build_legacy_health(
            self.formal,
            producer_revision="0000000",
        )
        self.assertEqual(document, expected)
        validate_legacy_health(document)
        self.assertEqual(document["gateway"]["processState"], "unknown")
        self.assertEqual(document["imports"]["state"], "unknown")
        self.assertEqual(document["imports"]["processState"], "unknown")
        self.assertEqual(document["generatedAt"], "2026-07-14T09:00:00+00:00")
        self.assertNotIn("api_key", json.dumps(document).casefold())

    def test_counts_preserve_unobserved_and_do_not_guess_unavailable_reason(self) -> None:
        self.formal["accountCounts"] = {
            "total": 10,
            "available": 2,
            "limited": 3,
            "unavailable": 1,
        }
        document = build_legacy_health(self.formal)
        accounts = document["capacity"]["accounts"]
        reasons = document["capacity"]["blockedReasons"]
        self.assertEqual(accounts, {
            "total": 10,
            "ready": 2,
            "warning": 0,
            "blocked": 4,
            "unknown": 4,
        })
        self.assertEqual(reasons, {"quota": 3, "login": 0, "cooldown": 0, "other": 1})
        self.assertEqual(document["capacity"]["state"], "degraded")
        self.assertTrue(document["capacity"]["available"])

    def test_unknown_freshness_stays_unobserved(self) -> None:
        self.formal["freshness"] = {"state": "unknown", "ageSeconds": 0}
        document = build_legacy_health(self.formal)
        self.assertIsNone(document["capacity"]["observedAt"])

    def test_formal_input_is_strict_bounded_and_non_symlinked(self) -> None:
        raw = json.dumps(self.formal).encode("utf-8")
        self.assertEqual(parse_formal_health(raw)["schema"], "cloudx.health.v1")
        modified = dict(self.formal)
        modified["taskId"] = "task-1"
        with self.assertRaises(LegacyHealthRejected):
            parse_formal_health(json.dumps(modified).encode("utf-8"))
        modified = dict(self.formal)
        modified["cloudxVersion"] = "invalid version"
        with self.assertRaisesRegex(LegacyHealthRejected, "cloudxVersion"):
            parse_formal_health(json.dumps(modified).encode("utf-8"))
        modified = dict(self.formal)
        modified["freshness"] = {"state": "stale", "ageSeconds": 10**30}
        with self.assertRaisesRegex(LegacyHealthRejected, "out of range"):
            build_legacy_health(modified)

        source = self.root / "health.json"
        source.write_bytes(raw)
        self.assertEqual(read_formal_health(source), raw)
        alias = self.root / "health-link.json"
        alias.symlink_to(source)
        with self.assertRaisesRegex(LegacyHealthRejected, "regular file"):
            read_formal_health(alias)
        source.write_bytes(b"x" * (64 * 1024 + 1))
        with self.assertRaisesRegex(LegacyHealthRejected, "size limit"):
            read_formal_health(source)

    def test_atomic_publication_is_mode_0644_and_preserves_old_file_on_failure(self) -> None:
        document = build_legacy_health(self.formal)
        destination = self.root / "state" / "health.json"
        publish(destination, document)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o644)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), document)
        before = destination.read_bytes()
        with mock.patch("cloudx_cloud.legacy_health_bridge.os.replace", side_effect=OSError("stop")):
            with self.assertRaises(OSError):
                publish(destination, document)
        self.assertEqual(destination.read_bytes(), before)
        self.assertEqual(list(destination.parent.glob(".cloudx-legacy-health-*")), [])

    def test_cli_emits_and_optionally_publishes_without_installing_anything(self) -> None:
        source = self.root / "formal.json"
        source.write_text(json.dumps(self.formal), encoding="utf-8")
        destination = self.root / "legacy.json"
        output = StringIO()
        with mock.patch.dict("os.environ", {"CLOUDX_BUILD_COMMIT": "abcdef0"}), redirect_stdout(output):
            self.assertEqual(main([
                "legacy-health-bridge",
                "--source",
                str(source),
                "--publish-to",
                str(destination),
            ]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["producer"]["revision"], "abcdef0")
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), document)

        errors = StringIO()
        with redirect_stderr(errors):
            self.assertEqual(main(["legacy-health-bridge", "--source", str(self.root / "missing")]), 1)
        self.assertIn("legacy-health-bridge", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
