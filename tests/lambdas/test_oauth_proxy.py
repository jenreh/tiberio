"""Tests for the OAuth catch-all proxy Lambda (API Gateway HTTP API v2)."""

from __future__ import annotations

import base64
import email.message
import io
import urllib.error
import urllib.request
from typing import Any

import pytest

from tests.lambdas.conftest import FakeS3Client, make_s3_error


def _event(
    method: str = "GET",
    path: str = "/oauth/authorize",
    query: str = "",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    is_base64: bool = False,
    cookies: list[str] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": query,
        "headers": headers or {"host": "abc123.execute-api.eu-central-1.amazonaws.com"},
        "requestContext": {"http": {"method": method, "path": path}},
        "isBase64Encoded": is_base64,
    }
    if body is not None:
        event["body"] = body
    if cookies is not None:
        event["cookies"] = cookies
    return event


class FakeUpstreamResponse:
    def __init__(
        self, status: int, headers: list[tuple[str, str]], body: bytes
    ) -> None:
        self.status = status
        self.headers = email.message.Message()
        for name, value in headers:
            self.headers[name] = value
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeUpstreamResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float = 0.0) -> Any:
        self.requests.append(request)
        assert timeout > 0
        if self.error is not None:
            raise self.error
        return self.response


def _install_opener(
    monkeypatch: pytest.MonkeyPatch, oauth_handler: Any, opener: FakeOpener
) -> None:
    monkeypatch.setattr(oauth_handler, "_opener", opener)


@pytest.mark.usefixtures("beacon_env", "patched_beacon_boto3")
class TestOAuthProxy:
    def test_get_passthrough_with_query(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(
            FakeUpstreamResponse(
                200,
                [("Content-Type", "text/html; charset=utf-8"), ("X-Custom", "1")],
                b"<html>login</html>",
            )
        )
        _install_opener(monkeypatch, oauth_handler, opener)
        event = _event(query="client_id=alexa&state=xyz")

        result = oauth_handler.handler(event, None)

        request = opener.requests[0]
        assert request.full_url == (
            "https://home.example.net/oauth/authorize?client_id=alexa&state=xyz"
        )
        assert request.get_method() == "GET"
        assert result["statusCode"] == 200
        assert result["isBase64Encoded"] is False
        assert result["body"] == "<html>login</html>"
        assert result["headers"]["Content-Type"] == "text/html; charset=utf-8"
        assert result["headers"]["X-Custom"] == "1"

    def test_host_and_hop_by_hop_headers_dropped(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(FakeUpstreamResponse(200, [], b""))
        _install_opener(monkeypatch, oauth_handler, opener)
        event = _event(
            headers={
                "host": "abc123.execute-api.eu-central-1.amazonaws.com",
                "connection": "keep-alive",
                "transfer-encoding": "chunked",
                "content-length": "0",
                "accept": "text/html",
            }
        )

        oauth_handler.handler(event, None)

        request = opener.requests[0]
        assert request.get_header("Host") is None
        assert request.get_header("Connection") is None
        assert request.get_header("Transfer-encoding") is None
        assert request.get_header("Content-length") is None
        assert request.get_header("Accept") == "text/html"

    def test_request_cookies_forwarded_as_cookie_header(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(FakeUpstreamResponse(200, [], b""))
        _install_opener(monkeypatch, oauth_handler, opener)

        oauth_handler.handler(_event(cookies=["session=abc", "csrf=def"]), None)

        assert opener.requests[0].get_header("Cookie") == "session=abc; csrf=def"

    def test_redirect_and_set_cookie_pass_through_unfollowed(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        headers = email.message.Message()
        headers["Location"] = "https://home.example.net/oauth/login?next=%2Fauthorize"
        headers["Set-Cookie"] = "session=abc; Path=/; HttpOnly"
        headers["Set-Cookie"] = "csrf=def; Path=/"
        error = urllib.error.HTTPError(
            "https://home.example.net/oauth/authorize",
            302,
            "Found",
            headers,
            io.BytesIO(b""),
        )
        opener = FakeOpener(error=error)
        _install_opener(monkeypatch, oauth_handler, opener)

        result = oauth_handler.handler(_event(), None)

        assert result["statusCode"] == 302
        assert result["headers"]["Location"] == (
            "https://home.example.net/oauth/login?next=%2Fauthorize"
        )
        assert result["cookies"] == [
            "session=abc; Path=/; HttpOnly",
            "csrf=def; Path=/",
        ]
        assert "Set-Cookie" not in result["headers"]

    def test_redirect_handler_never_follows(self, oauth_handler: Any) -> None:
        no_redirect = oauth_handler._NoRedirectHandler()
        request = urllib.request.Request("https://home.example.net/oauth/a")
        result = no_redirect.redirect_request(
            request, None, 302, "Found", {}, "https://elsewhere.example/"
        )
        assert result is None

    def test_base64_request_body_decoded_before_forwarding(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(
            FakeUpstreamResponse(
                200, [("Content-Type", "application/json")], b'{"ok": true}'
            )
        )
        _install_opener(monkeypatch, oauth_handler, opener)
        raw = b"grant_type=authorization_code&code=xyz"
        event = _event(
            method="POST",
            path="/oauth/token",
            headers={"content-type": "application/x-www-form-urlencoded"},
            body=base64.b64encode(raw).decode("ascii"),
            is_base64=True,
        )

        result = oauth_handler.handler(event, None)

        request = opener.requests[0]
        assert request.get_method() == "POST"
        assert request.data == raw
        assert result["statusCode"] == 200
        assert result["body"] == '{"ok": true}'

    def test_plain_text_request_body_forwarded(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(FakeUpstreamResponse(200, [], b""))
        _install_opener(monkeypatch, oauth_handler, opener)
        event = _event(method="POST", path="/oauth/token", body="a=1&b=2")

        oauth_handler.handler(event, None)

        assert opener.requests[0].data == b"a=1&b=2"

    def test_binary_response_is_base64_encoded(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        png = b"\x89PNG\r\n\x1a\n\x00binary"
        opener = FakeOpener(
            FakeUpstreamResponse(200, [("Content-Type", "image/png")], png)
        )
        _install_opener(monkeypatch, oauth_handler, opener)

        result = oauth_handler.handler(_event(path="/oauth/logo.png"), None)

        assert result["isBase64Encoded"] is True
        assert base64.b64decode(result["body"]) == png

    def test_textual_content_type_with_non_utf8_body_falls_back_to_base64(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = b"\xff\xfe<html>broken</html>"
        opener = FakeOpener(
            FakeUpstreamResponse(200, [("Content-Type", "text/html")], body)
        )
        _install_opener(monkeypatch, oauth_handler, opener)

        result = oauth_handler.handler(_event(), None)

        assert result["isBase64Encoded"] is True
        assert base64.b64decode(result["body"]) == body

    def test_missing_content_type_with_binary_body_falls_back_to_base64(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # _looks_textual("") is True, so this combination relies on the
        # UnicodeDecodeError fallback as well.
        body = b"\x00\x01\xff\xfe"
        opener = FakeOpener(FakeUpstreamResponse(200, [], body))
        _install_opener(monkeypatch, oauth_handler, opener)

        result = oauth_handler.handler(_event(), None)

        assert result["isBase64Encoded"] is True
        assert base64.b64decode(result["body"]) == body

    def test_invalid_beacon_json_returns_502(
        self, oauth_handler: Any, fake_s3: FakeS3Client
    ) -> None:
        fake_s3.body = b"{not json"

        result = oauth_handler.handler(_event(), None)

        assert result["statusCode"] == 502
        assert result["isBase64Encoded"] is False

    def test_beacon_failure_returns_502(
        self,
        oauth_handler: Any,
        fake_s3: FakeS3Client,
    ) -> None:
        fake_s3.error = make_s3_error()

        result = oauth_handler.handler(_event(), None)

        assert result["statusCode"] == 502
        assert result["isBase64Encoded"] is False

    def test_upstream_connection_failure_returns_502(
        self, oauth_handler: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = FakeOpener(error=urllib.error.URLError("connection refused"))
        _install_opener(monkeypatch, oauth_handler, opener)

        result = oauth_handler.handler(_event(), None)

        assert result["statusCode"] == 502
