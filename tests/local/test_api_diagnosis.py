from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local import api_diagnosis  # noqa: E402
from cloudx_local.api_failure import (  # noqa: E402
    CAUSE_ACCESS_DENIED,
    CAUSE_ACCOUNT_DEACTIVATED,
    CAUSE_LOGIN_REQUIRED,
    CAUSE_NO_USABLE_ACCOUNTS,
    CAUSE_QUOTA_EXHAUSTED,
    CAUSE_RATE_LIMITED,
    ApiResponseObserver,
    classify_http_failure,
)
from cloudx_local.config import LocalConfig  # noqa: E402
from cloudx_local.remote import RemoteEndpoint  # noqa: E402


def config(home: pathlib.Path) -> LocalConfig:
    return LocalConfig(
        home=home,
        config_path=home / "config.json",
        state_dir=home / "state",
        data_dir=home / "data",
        cache_dir=home / "cache",
        accounts_dir=home / "accounts",
        codex_binary="codex",
        ssh_binary="ssh",
        ssh_host="cloud",
        remote_helper="cloudx-remote",
        legacy_forward_host="gateway",
        legacy_forward_port=8317,
        legacy_api_key_command="legacy-key",
        broker_idle_seconds=3600,
        endpoint_timeout_seconds=2.0,
        endpoint_attempts=1,
        release_repository="repo",
    )


def error_body(error_type: str, message: str, **extra: object) -> bytes:
    error = {"type": error_type, "message": message, **extra}
    return json.dumps({"error": error}, separators=(",", ":")).encode("utf-8")


def write_log(
    directory: pathlib.Path,
    name: str,
    observed: datetime,
    status: int,
    body: bytes,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "\n".join(
            (
                "=== REQUEST INFO ===",
                "Timestamp: %s" % observed.isoformat(),
                "=== REQUEST BODY ===",
                '{"input":"private prompt mentioning account deactivated","api_key":"secret"}',
                "=== API RESPONSE ===",
                "Timestamp: %s" % observed.isoformat(),
                body.decode("utf-8"),
                "=== RESPONSE ===",
                "Status: %d" % status,
                "Content-Type: application/json",
                body.decode("utf-8"),
                "",
            )
        ),
        encoding="utf-8",
    )
    timestamp = observed.timestamp()
    os.utime(path, (timestamp, timestamp))


class ApiFailureClassifierTests(unittest.TestCase):
    def test_distinguishes_deactivation_quota_rate_limit_login_and_permission(self) -> None:
        cases = (
            (
                403,
                error_body("invalid_request_error", "Your account has been deactivated", code="account_deactivated"),
                CAUSE_ACCOUNT_DEACTIVATED,
            ),
            (
                429,
                error_body("usage_limit_reached", "The usage limit has been reached"),
                CAUSE_QUOTA_EXHAUSTED,
            ),
            (
                429,
                error_body("rate_limit_error", "Rate limit reached", code="rate_limit_exceeded"),
                CAUSE_RATE_LIMITED,
            ),
            (
                401,
                error_body("invalid_request_error", "Please sign in again", code="refresh_token_reused"),
                CAUSE_LOGIN_REQUIRED,
            ),
            (403, error_body("permission_error", "Model is not supported"), CAUSE_ACCESS_DENIED),
            (
                503,
                error_body("server_error", "auth_unavailable: no auth available", code="internal_server_error"),
                CAUSE_NO_USABLE_ACCOUNTS,
            ),
        )
        for status, body, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_http_failure(status, body).cause, expected)

    def test_usage_limit_reset_is_normalized_without_raw_error_text(self) -> None:
        observed = datetime(2026, 7, 17, 5, 0, tzinfo=timezone.utc)
        failure = classify_http_failure(
            429,
            error_body(
                "usage_limit_reached",
                "The usage limit has been reached",
                resets_in_seconds=60,
            ),
            observed_at=observed,
        )
        document = failure.as_observation("gateway_error_log")
        self.assertEqual(document["retryAt"], "2026-07-17T05:01:00Z")
        self.assertNotIn("message", document)

    def test_tunnel_observer_handles_split_http_response_without_mutating_bytes(self) -> None:
        observed = []
        observer = ApiResponseObserver(observed.append)
        observer.feed(b"HTTP/1.")
        observer.feed(b"1 429 Too Many Requests\r\nContent-Type: application/json\r\n\r\n")
        observer.feed(error_body("usage_limit_reached", "The usage limit has been reached"))
        observer.close()
        self.assertTrue(observed)
        self.assertEqual(observed[-1]["cause"], CAUSE_QUOTA_EXHAUSTED)
        self.assertEqual(observed[-1]["httpStatus"], 429)

    def test_successful_assistant_text_cannot_be_misclassified_as_an_api_failure(self) -> None:
        observed = []
        observer = ApiResponseObserver(observed.append)
        observer.feed(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n")
        observer.feed(
            b'data: {"type":"response.output_text.delta","delta":"account has been deactivated"}\n\n'
        )
        observer.close()
        self.assertEqual(observed, [])

    def test_server_status_waits_for_body_before_emitting_a_generic_failure(self) -> None:
        observed = []
        observer = ApiResponseObserver(observed.append)
        observer.feed(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n\r\n")
        self.assertEqual(observed, [])
        observer.feed(
            error_body(
                "server_error",
                "auth_unavailable: no auth available",
                code="internal_server_error",
            )
        )
        observer.close()
        self.assertEqual(observed[-1]["cause"], CAUSE_NO_USABLE_ACCOUNTS)

    def test_streamed_response_failed_event_is_classified_even_when_http_started_at_200(self) -> None:
        observed = []
        observer = ApiResponseObserver(observed.append)
        observer.feed(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n")
        observer.feed(
            b'data: {"type":"response.failed","response":{"error":{"type":"usage_limit_reached",'
            b'"message":"The usage limit has been reached"}}}\n\n'
        )
        observer.close()
        self.assertEqual(observed[-1]["cause"], CAUSE_QUOTA_EXHAUSTED)
        self.assertEqual(observed[-1]["httpStatus"], 200)


class ApiDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.config = config(self.home)
        self.logs = self.home / "logs"
        self.environment = mock.patch.dict(
            os.environ,
            {"CLOUDX_LOCAL_CPA_LOG_DIR": str(self.logs)},
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def prepare_profile(self, account: str = "api") -> None:
        profile = self.config.accounts_dir / account / ".codex"
        profile.mkdir(parents=True)
        (profile / "auth.json").write_text(
            json.dumps({"auth_mode": "apikey", "api_key": "private-gateway-key"}),
            encoding="utf-8",
        )
        (profile / "config.toml").write_text(
            'model_provider = "openai"\nopenai_base_url = "http://127.0.0.1:8317/v1"\n',
            encoding="utf-8",
        )

    def test_generic_no_auth_does_not_hide_recent_usage_limit_root_cause(self) -> None:
        now = datetime.now(timezone.utc)
        write_log(
            self.logs,
            "error-v1-responses-root.log",
            now - timedelta(minutes=2),
            429,
            error_body("usage_limit_reached", "The usage limit has been reached", resets_in_seconds=3600),
        )
        write_log(
            self.logs,
            "error-v1-responses-latest.log",
            now - timedelta(minutes=1),
            503,
            error_body("server_error", "auth_unavailable: no auth available", code="internal_server_error"),
        )
        observation = api_diagnosis.recent_local_observation(self.config, now=now)
        self.assertEqual(observation["cause"], CAUSE_QUOTA_EXHAUSTED)
        self.assertEqual(observation["maskedBy"], CAUSE_NO_USABLE_ACCOUNTS)
        serialized = json.dumps(observation)
        self.assertNotIn("private prompt", serialized)
        self.assertNotIn("secret", serialized)

    @mock.patch("cloudx_local.api_diagnosis.probe_endpoint", return_value=200)
    def test_local_human_output_explains_quota_is_not_deactivation(self, unused_probe: mock.Mock) -> None:
        self.prepare_profile()
        now = datetime.now(timezone.utc)
        write_log(
            self.logs,
            "error-v1-responses-quota.log",
            now,
            429,
            error_body("usage_limit_reached", "The usage limit has been reached"),
        )
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(api_diagnosis.run(self.config, ["api"]), 0)
        rendered = output.getvalue()
        self.assertIn("Cause: quota exhausted", rendered)
        self.assertIn("does not indicate account deactivation", rendered)
        self.assertNotIn("private-gateway-key", rendered)

    @mock.patch("cloudx_local.api_diagnosis.probe_endpoint", return_value=200)
    def test_json_contract_is_secret_free_and_machine_readable(self, unused_probe: mock.Mock) -> None:
        self.prepare_profile()
        write_log(
            self.logs,
            "error-v1-responses-deactivated.log",
            datetime.now(timezone.utc),
            403,
            error_body("invalid_request_error", "Your account has been deactivated", code="account_deactivated"),
        )
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(api_diagnosis.run(self.config, ["api", "--json"]), 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema"], "cloudx.api-diagnosis.v1")
        self.assertEqual(document["cause"], CAUSE_ACCOUNT_DEACTIVATED)
        self.assertEqual(document["confidence"], "exact")
        self.assertNotIn("private-gateway-key", output.getvalue())

    @mock.patch("cloudx_local.api_diagnosis.probe_endpoint", return_value=200)
    @mock.patch("cloudx_local.api_diagnosis.RemoteClient")
    @mock.patch("cloudx_local.api_diagnosis.BrokerClient")
    def test_cloud_diagnosis_uses_passive_broker_evidence(
        self,
        broker_class: mock.Mock,
        remote_class: mock.Mock,
        unused_probe: mock.Mock,
    ) -> None:
        observation = classify_http_failure(
            401,
            error_body("invalid_request_error", "Sign in again", code="refresh_token_reused"),
        ).as_observation("tunnel_observation")
        broker = broker_class.return_value
        broker.status.return_value = {"lastApiFailure": observation}
        lease = mock.MagicMock(port=24567)
        broker.acquire.return_value = lease
        remote_class.return_value.resolve_endpoint.return_value = RemoteEndpoint(
            "cloudx", "private-cloud-key", "gateway", 8317, {}
        )

        document = api_diagnosis.diagnose_cloud(self.config)

        self.assertEqual(document["target"], "cloud_gateway")
        self.assertEqual(document["cause"], CAUSE_LOGIN_REQUIRED)
        self.assertEqual(document["evidence"]["source"], "tunnel_observation")
        self.assertNotIn("private-cloud-key", json.dumps(document))


if __name__ == "__main__":
    unittest.main()
