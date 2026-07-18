from __future__ import annotations

import base64
import io
import json
import pathlib
import sys
import unittest
import urllib.error


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud import cpa_quota  # noqa: E402


def jwt(expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": expires_at}, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return "header.%s.signature" % payload


def auth(expires_at: int = 4102444800, *, refresh: bool = False) -> dict:
    return {
        "auth_mode": "chatgpt",
        "tokens": {
            "access_token": jwt(expires_at),
            "account_id": "account-sanitized",
            "refresh_token": "refresh-sanitized" if refresh else "",
        },
    }


class Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, unused_type: object, unused_value: object, unused_traceback: object) -> None:
        return None

    def read(self, unused_limit: int = -1) -> bytes:
        return self.body


class CpaQuotaTests(unittest.TestCase):
    def test_ready_probe_normalizes_primary_and_secondary_windows(self) -> None:
        requests = []

        def opener(request: object, timeout: float) -> Response:
            requests.append((request, timeout))
            return Response({
                "rate_limit": {
                    "primary_window": {"used_percent": 20},
                    "secondary_window": {"remaining_percent": 70},
                }
            })

        probe = cpa_quota.probe_account_quota_http(
            {},
            {},
            auth_override=auth(),
            timeout_seconds=7,
            url_opener=opener,
        )

        self.assertEqual(probe["status"], "ready")
        self.assertEqual(probe["remaining_percents"], [80, 70])
        self.assertEqual(requests[0][1], 7)
        request = requests[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer %s" % auth()["tokens"]["access_token"])
        self.assertEqual(request.get_header("Chatgpt-account-id"), "account-sanitized")
        rendered = json.dumps(probe)
        self.assertNotIn("account-sanitized", rendered)
        self.assertNotIn(auth()["tokens"]["access_token"], rendered)

    def test_warning_and_limit_classification_match_the_legacy_contract(self) -> None:
        warning = cpa_quota.probe_account_quota_http(
            {},
            {},
            auth_override=auth(),
            url_opener=lambda request, timeout: Response({
                "primary_window": {"remaining_percent": 25},
                "secondary_window": {"remaining_percent": 80},
            }),
        )
        limited = cpa_quota.probe_account_quota_http(
            {},
            {},
            auth_override=auth(),
            url_opener=lambda request, timeout: Response({
                "rate_limit": {
                    "primary_window": {"remaining_percent": 60},
                    "secondary_window": {"remaining_percent": 0, "reset_at": 4102444800},
                }
            }),
        )

        self.assertEqual((warning["status"], warning["warning_window"]), ("warning", "5h"))
        self.assertEqual((limited["status"], limited["warning_window"]), ("limited", "7d"))
        self.assertEqual(limited["unavailable_until"], "2100-01-01T00:00:00+00:00")

    def test_http_401_requires_refresh_or_archives_immediately(self) -> None:
        def opener(request: object, timeout: float) -> Response:
            raise urllib.error.HTTPError(request.full_url, 401, "fixture", {}, None)

        refreshable = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(refresh=True), url_opener=opener
        )
        permanent = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(), url_opener=opener
        )

        self.assertEqual(refreshable["status"], "login")
        self.assertNotIn("permanent_auth_failure", refreshable)
        self.assertEqual(permanent["status"], "invalid")
        self.assertTrue(permanent["permanent_auth_failure"])
        self.assertEqual(permanent["failure_reason"], "authentication_unauthorized")

    def test_http_429_and_quota_body_are_never_permanent(self) -> None:
        for code, payload in (
            (429, {}),
            (402, {"error": {"code": "usage_limit_reached"}}),
        ):
            with self.subTest(code=code):
                def opener(request: object, timeout: float, status: int = code, body: object = payload) -> Response:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        status,
                        "fixture",
                        {},
                        io.BytesIO(json.dumps(body).encode("utf-8")),
                    )

                probe = cpa_quota.probe_account_quota_http(
                    {}, {}, auth_override=auth(), url_opener=opener
                )
                self.assertEqual(probe["status"], "limited")
                self.assertNotIn("permanent_auth_failure", probe)

    def test_deactivated_workspace_402_is_permanent_without_raw_body(self) -> None:
        body = {"error": {"code": "deactivated_workspace", "message": "private fixture"}}

        def opener(request: object, timeout: float) -> Response:
            raise urllib.error.HTTPError(
                request.full_url,
                402,
                "fixture",
                {},
                io.BytesIO(json.dumps(body).encode("utf-8")),
            )

        probe = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(), url_opener=opener
        )

        self.assertEqual(probe["status"], "invalid")
        self.assertEqual(probe["failure_reason"], "deactivated_workspace")
        self.assertTrue(probe["permanent_auth_failure"])
        self.assertFalse(probe["weekly_quota"])
        self.assertNotIn("private fixture", json.dumps(probe))

    def test_generic_endpoint_failure_falls_back_to_codex_usage(self) -> None:
        endpoints = []

        def opener(request: object, timeout: float) -> Response:
            endpoints.append(request.full_url)
            if len(endpoints) == 1:
                raise urllib.error.HTTPError(request.full_url, 500, "fixture", {}, None)
            return Response({"primary_window": {"remaining_percent": 90}})

        probe = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(), url_opener=opener
        )

        self.assertEqual(endpoints, [
            cpa_quota.USAGE_ENDPOINT_CHATGPT,
            cpa_quota.USAGE_ENDPOINT_CODEXAPI,
        ])
        self.assertEqual(probe["status"], "ready")

    def test_expired_or_unsupported_token_never_reaches_the_network(self) -> None:
        calls = []

        def opener(request: object, timeout: float) -> Response:
            calls.append(request)
            return Response({})

        refreshable = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(1, refresh=True), url_opener=opener
        )
        expired = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(1), url_opener=opener
        )
        unsupported = cpa_quota.probe_account_quota_http(
            {},
            {},
            auth_override={"tokens": {"access_token": "not-a-jwt"}},
            url_opener=opener,
        )

        self.assertEqual(refreshable["status"], "login")
        self.assertEqual(expired["status"], "invalid")
        self.assertTrue(expired["permanent_auth_failure"])
        self.assertIsNone(unsupported)
        self.assertEqual(calls, [])

    def test_transport_gate_blocks_provider_or_network_outage(self) -> None:
        def provider_error(request: object, timeout: float) -> Response:
            raise urllib.error.HTTPError(request.full_url, 503, "fixture", {}, None)

        def transport_error(request: object, timeout: float) -> Response:
            raise OSError("fixture")

        self.assertEqual(
            cpa_quota.probe_transport_http({}, url_opener=provider_error)["status"],
            "provider_error",
        )
        self.assertEqual(
            cpa_quota.probe_transport_http({}, url_opener=transport_error)["status"],
            "transport_error",
        )

    def test_explicit_proxy_url_is_validated(self) -> None:
        self.assertIsNotNone(cpa_quota.url_opener_for_proxy("http://127.0.0.1:7890"))
        for value in (
            "socks5://127.0.0.1:7890",
            "http://user:secret@127.0.0.1:7890",
            "http://127.0.0.1:99999",
            "relative",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cpa_quota.url_opener_for_proxy(value)

    def test_oversized_or_malformed_responses_fail_without_payload_output(self) -> None:
        class Oversized(Response):
            def read(self, unused_limit: int = -1) -> bytes:
                return b"x" * (cpa_quota.MAX_USAGE_RESPONSE_BYTES + 1)

        oversized = cpa_quota.probe_account_quota_http(
            {}, {}, auth_override=auth(), url_opener=lambda request, timeout: Oversized({})
        )
        malformed = cpa_quota.probe_account_quota_http(
            {},
            {},
            auth_override=auth(),
            url_opener=lambda request, timeout: Response("not-an-object"),
        )

        self.assertIsNone(oversized)
        self.assertIsNone(malformed)


if __name__ == "__main__":
    unittest.main()
