"""Tests: bearer-token validation on POST /alexa/directive.

Uses the real JwtService so we verify the full validation path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.interfaces.alexa.conftest import DEVICES_YAML, directive, discovery_directive

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.jwt_service import JwtService
from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.api.app import create_app
from pantau.composition import build_oauth_test_container
from pantau.config.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="auth-test-secret", jwt_access_token_expire_minutes=60)


@pytest.fixture
def jwt_service(settings: Settings) -> JwtService:
    return JwtService(settings)


@pytest.fixture
async def auth_client(
    tmp_path: Path, settings: Settings, jwt_service: JwtService
) -> TestClient:
    """App wired with real JwtService for the directive endpoint."""
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")

    store = SqliteUserStore(tmp_path / "test.db")
    await store.start()
    auth_codes = AuthCodeStore()

    container = build_oauth_test_container(cfg, store, jwt_service, auth_codes)
    app = create_app(settings=settings, container=container)
    client = TestClient(app)
    yield client
    await store.stop()


class TestDirectiveBearerValidation:
    def test_valid_token_allows_directive(
        self, auth_client: TestClient, jwt_service: JwtService
    ) -> None:
        token, _ = jwt_service.issue_access_token("user-1")
        resp = auth_client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.PowerController", "TurnOn", endpoint_id="zdf", bearer_token=token
            ),
        )
        assert resp.status_code == 200

    def test_missing_token_returns_401(self, auth_client: TestClient) -> None:
        body = {
            "directive": {
                "header": {
                    "namespace": "Alexa.PowerController",
                    "name": "TurnOn",
                    "messageId": "msg-1",
                    "payloadVersion": "3",
                },
                "endpoint": {
                    "endpointId": "zdf",
                    "cookie": {},
                },
                "payload": {},
            }
        }
        resp = auth_client.post("/alexa/directive", json=body)
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.PowerController",
                "TurnOn",
                endpoint_id="zdf",
                bearer_token="invalid-token",
            ),
        )
        assert resp.status_code == 401

    def test_discovery_directive_with_valid_token(
        self, auth_client: TestClient, jwt_service: JwtService
    ) -> None:
        token, _ = jwt_service.issue_access_token("user-1")
        resp = auth_client.post(
            "/alexa/directive", json=discovery_directive(bearer_token=token)
        )
        assert resp.status_code == 200

    def test_discovery_directive_with_invalid_token_returns_401(
        self, auth_client: TestClient
    ) -> None:
        resp = auth_client.post(
            "/alexa/directive", json=discovery_directive(bearer_token="bad-token")
        )
        assert resp.status_code == 401
