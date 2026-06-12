"""Tests for the Alexa Smart-Home directive proxy Lambda."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

from tests.lambdas.conftest import FakeBoto3, FakeS3Client, make_s3_error

SECRET = "topsecret"


def _directive_event() -> dict[str, Any]:
    return {
        "directive": {
            "header": {
                "namespace": "Alexa.PowerController",
                "name": "TurnOn",
                "messageId": "msg-1",
                "correlationToken": "corr-1",
                "payloadVersion": "3",
            },
            "endpoint": {
                "scope": {"type": "BearerToken", "token": "user-token"},
                "endpointId": "tv-livingroom",
            },
            "payload": {},
        }
    }


class FakeHTTPResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture
def captured_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> list[urllib.request.Request]:
    captured: list[urllib.request.Request] = []
    upstream = json.dumps({"event": {"header": {"name": "Response"}}}).encode()

    def fake_urlopen(
        request: urllib.request.Request, timeout: float = 0.0
    ) -> FakeHTTPResponse:
        captured.append(request)
        assert timeout > 0
        return FakeHTTPResponse(upstream)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def _verify_hmac_like_server(
    request: urllib.request.Request, secret: str, tolerance_seconds: int = 300
) -> None:
    """Re-implements the verification from interfaces/alexa/directive_router."""
    timestamp_header = request.get_header("X-pantau-timestamp")
    signature = request.get_header("X-pantau-signature")
    assert timestamp_header, "Missing HMAC timestamp header"
    assert signature, "Missing HMAC signature header"
    timestamp = int(timestamp_header)
    assert abs(time.time() - timestamp) <= tolerance_seconds
    raw_body = request.data
    assert isinstance(raw_body, bytes)
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(expected, signature)


@pytest.mark.usefixtures("beacon_env", "patched_beacon_boto3")
class TestDirectiveForwarding:
    def test_forwards_directive_with_valid_hmac(
        self,
        directive_handler: Any,
        captured_requests: list[urllib.request.Request],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PANTAU_SHARED_SECRET", SECRET)
        event = _directive_event()

        result = directive_handler.handler(event, None)

        assert result == {"event": {"header": {"name": "Response"}}}
        request = captured_requests[0]
        assert request.full_url == "https://home.example.net/alexa/directive"
        assert request.get_method() == "POST"
        assert isinstance(request.data, bytes)
        assert json.loads(request.data) == event
        assert request.get_header("Content-type") == "application/json"
        _verify_hmac_like_server(request, SECRET)

    def test_no_hmac_headers_without_secret(
        self,
        directive_handler: Any,
        captured_requests: list[urllib.request.Request],
    ) -> None:
        directive_handler.handler(_directive_event(), None)

        request = captured_requests[0]
        assert request.get_header("X-pantau-timestamp") is None
        assert request.get_header("X-pantau-signature") is None

    def test_etag_cache_uses_conditional_get(
        self,
        directive_handler: Any,
        captured_requests: list[urllib.request.Request],
        fake_s3: FakeS3Client,
    ) -> None:
        directive_handler.handler(_directive_event(), None)
        directive_handler.handler(_directive_event(), None)

        assert len(fake_s3.calls) == 2
        assert "IfNoneMatch" not in fake_s3.calls[0]
        assert fake_s3.calls[1]["IfNoneMatch"] == fake_s3.etag
        # The 304 path must still resolve the cached base_url.
        assert len(captured_requests) == 2
        assert captured_requests[1].full_url.startswith("https://home.example.net")

    def test_lambda_signature_accepted_by_real_server_verifier(
        self,
        directive_handler: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Round-trip: headers built by the Lambda must pass the actual
        verifier in pantau.interfaces.alexa.directive_router — pins both
        canonicalization schemes against silent drift."""
        from types import SimpleNamespace  # noqa: PLC0415

        from pantau.interfaces.alexa.directive_router import (  # noqa: PLC0415
            _require_valid_hmac,
        )

        monkeypatch.setenv("PANTAU_SHARED_SECRET", SECRET)
        body = json.dumps(_directive_event()).encode("utf-8")

        headers = directive_handler._build_headers(body)

        # Stub request: the verifier only calls request.headers.get(...).
        request: Any = SimpleNamespace(headers=headers)
        # Must not raise HTTPException(401).
        _require_valid_hmac(request, body, SECRET, tolerance_seconds=300)

    def test_warm_container_forwards_to_rotated_base_url(
        self,
        directive_handler: Any,
        captured_requests: list[urllib.request.Request],
        fake_s3: FakeS3Client,
    ) -> None:
        """When the beacon object changes (new ETag, new base_url), the next
        invocation of a warm container must forward to the NEW URL."""
        directive_handler.handler(_directive_event(), None)
        assert captured_requests[0].full_url.startswith("https://home.example.net")

        fake_s3.body = (
            b'{"base_url": "https://rotated.example.net", '
            b'"updated_at": "2026-06-12T00:00:00Z", "health": "ok"}'
        )
        fake_s3.etag = '"etag-2"'

        directive_handler.handler(_directive_event(), None)

        assert captured_requests[1].full_url == (
            "https://rotated.example.net/alexa/directive"
        )

    def test_secret_fetched_once_from_ssm(
        self,
        directive_handler: Any,
        captured_requests: list[urllib.request.Request],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ssm_calls: list[dict[str, Any]] = []

        class FakeSSM:
            def get_parameter(self, **kwargs: Any) -> dict[str, Any]:
                ssm_calls.append(kwargs)
                return {"Parameter": {"Value": "ssm-secret"}}

        monkeypatch.setenv("PANTAU_SHARED_SECRET_SSM_PARAM", "/pantau/secret")
        monkeypatch.setattr(directive_handler, "boto3", FakeBoto3(ssm=FakeSSM()))

        directive_handler.handler(_directive_event(), None)
        directive_handler.handler(_directive_event(), None)

        assert len(ssm_calls) == 1
        assert ssm_calls[0] == {"Name": "/pantau/secret", "WithDecryption": True}
        for request in captured_requests:
            _verify_hmac_like_server(request, "ssm-secret")


@pytest.mark.usefixtures("beacon_env", "patched_beacon_boto3")
class TestDirectiveErrorMapping:
    def _assert_bridge_unreachable(self, result: dict[str, Any]) -> None:
        header = result["event"]["header"]
        assert header["namespace"] == "Alexa"
        assert header["name"] == "ErrorResponse"
        assert header["payloadVersion"] == "3"
        assert header["messageId"]
        assert header["correlationToken"] == "corr-1"
        assert result["event"]["endpoint"] == {"endpointId": "tv-livingroom"}
        payload = result["event"]["payload"]
        assert payload["type"] == "BRIDGE_UNREACHABLE"
        assert payload["message"]

    def test_s3_failure_maps_to_bridge_unreachable(
        self, directive_handler: Any, fake_s3: FakeS3Client
    ) -> None:
        fake_s3.error = make_s3_error()

        result = directive_handler.handler(_directive_event(), None)

        self._assert_bridge_unreachable(result)

    def test_invalid_beacon_json_maps_to_bridge_unreachable(
        self, directive_handler: Any, fake_s3: FakeS3Client
    ) -> None:
        fake_s3.body = b"{not json"

        result = directive_handler.handler(_directive_event(), None)

        self._assert_bridge_unreachable(result)

    def test_non_https_beacon_url_maps_to_bridge_unreachable(
        self, directive_handler: Any, fake_s3: FakeS3Client
    ) -> None:
        fake_s3.body = b'{"base_url": "ftp://home.example.net"}'

        result = directive_handler.handler(_directive_event(), None)

        self._assert_bridge_unreachable(result)

    def test_home_server_failure_maps_to_bridge_unreachable(
        self, directive_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(request: urllib.request.Request, timeout: float = 0.0) -> None:
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", fail)

        result = directive_handler.handler(_directive_event(), None)

        self._assert_bridge_unreachable(result)

    def test_error_response_without_endpoint(
        self, directive_handler: Any, fake_s3: FakeS3Client
    ) -> None:
        fake_s3.error = make_s3_error()
        event = {
            "directive": {
                "header": {"namespace": "Alexa.Discovery", "name": "Discover"},
                "payload": {"scope": {"type": "BearerToken", "token": "t"}},
            }
        }

        result = directive_handler.handler(event, None)

        assert result["event"]["payload"]["type"] == "BRIDGE_UNREACHABLE"
        assert "endpoint" not in result["event"]
        assert "correlationToken" not in result["event"]["header"]
