"""Tests for request-ID and security-header middleware."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from pantau.api.app import create_app
from pantau.api.logging_setup import request_id_var
from pantau.api.middleware import RequestIdMiddleware
from pantau.config.settings import Settings

DEVICES_YAML = """
tv:
  watch_activity: "TV"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "zdf"
      friendly_name: "ZDF"
      channel_number: "2"
blinds: []
thermostats: []
"""


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    config = tmp_path / "devices.yaml"
    config.write_text(DEVICES_YAML, encoding="utf-8")
    app = create_app(settings=Settings(devices_config_path=config, dev_mode=True))
    return TestClient(app)


class TestRequestIdMiddleware:
    def test_echoes_provided_request_id(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"X-Request-ID": "my-id-123"})
        assert resp.headers["X-Request-ID"] == "my-id-123"

    def test_generates_uuid_when_absent(self, client: TestClient) -> None:
        resp = client.get("/health")
        # raises ValueError if not a valid UUID
        uuid.UUID(resp.headers["X-Request-ID"])

    def test_rejects_unsafe_incoming_id(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"X-Request-ID": "bad id !! injection"})
        generated = resp.headers["X-Request-ID"]
        assert generated != "bad id !! injection"
        uuid.UUID(generated)

    def test_rejects_overlong_incoming_id(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"X-Request-ID": "a" * 200})
        uuid.UUID(resp.headers["X-Request-ID"])

    def test_contextvar_set_during_request_and_reset_after(self) -> None:
        captured: dict[str, str] = {}

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            captured["request_id"] = request_id_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        test_client = TestClient(RequestIdMiddleware(app))  # type: ignore[arg-type]
        test_client.get("/", headers={"X-Request-ID": "ctx-1"})
        assert captured["request_id"] == "ctx-1"
        assert request_id_var.get() == "-"


class TestSecurityHeaders:
    def test_nosniff_on_all_responses(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_oauth_html_pages_get_no_store_and_frame_deny(
        self, client: TestClient
    ) -> None:
        resp = client.get(
            "/oauth/authorize",
            params={
                "redirect_uri": "https://example.com/cb",
                "client_id": "alexa",
                "code_challenge": "x" * 43,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.headers["Pragma"] == "no-cache"
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_oauth_token_response_gets_no_store(self, client: TestClient) -> None:
        resp = client.post("/oauth/token", data={"grant_type": "bogus"})
        assert resp.headers["Cache-Control"] == "no-store"

    def test_non_oauth_routes_not_forced_no_store(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.headers.get("Cache-Control") != "no-store"
