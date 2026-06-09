"""Tests for GET/POST /oauth/authorize — login form and auth code issuance."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.interfaces.oauth.conftest import (
    DEVICES_YAML,
    TEST_CLIENT_ID,
    TEST_PASSWORD,
    TEST_REDIRECT_URI,
    TEST_USERNAME,
    make_pkce_pair,
)

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.jwt_service import JwtService
from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.api.app import create_app
from pantau.composition import build_oauth_test_container
from pantau.config.settings import Settings


class TestAuthorizeGet:
    def test_returns_200_with_html(self, client: TestClient) -> None:
        _, challenge = make_pkce_pair()
        resp = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": TEST_REDIRECT_URI,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "random-state",
            },
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_login_form_contains_hidden_fields(self, client: TestClient) -> None:
        _, challenge = make_pkce_pair()
        resp = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": TEST_REDIRECT_URI,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "my-state",
            },
        )
        html = resp.text
        assert TEST_REDIRECT_URI in html
        assert TEST_CLIENT_ID in html
        assert challenge in html
        assert "my-state" in html

    def test_unsupported_response_type_returns_400(self, client: TestClient) -> None:
        _, challenge = make_pkce_pair()
        resp = client.get(
            "/oauth/authorize",
            params={
                "response_type": "token",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": TEST_REDIRECT_URI,
                "code_challenge": challenge,
            },
        )
        assert resp.status_code == 400

    def test_login_form_has_username_and_password_inputs(
        self, client: TestClient
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": TEST_REDIRECT_URI,
                "code_challenge": challenge,
            },
        )
        assert 'name="username"' in resp.text
        assert 'name="password"' in resp.text


class TestAuthorizePost:
    def test_valid_credentials_redirects_with_code(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        resp = client.post(
            "/oauth/authorize",
            data={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
            },
        )
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith(TEST_REDIRECT_URI)
        assert "code=" in location
        assert "state=xyz" in location

    def test_invalid_password_returns_401(
        self, client: TestClient, registered_user: dict
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = client.post(
            "/oauth/authorize",
            data={
                "username": TEST_USERNAME,
                "password": "wrong-password",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "",
            },
        )
        assert resp.status_code == 401
        assert "text/html" in resp.headers["content-type"]

    def test_unknown_username_returns_401(self, client: TestClient) -> None:
        _, challenge = make_pkce_pair()
        resp = client.post(
            "/oauth/authorize",
            data={
                "username": "nobody",
                "password": "any-password",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "",
            },
        )
        assert resp.status_code == 401

    def test_login_failure_re_renders_form_with_error(
        self, client: TestClient, registered_user: dict
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = client.post(
            "/oauth/authorize",
            data={
                "username": TEST_USERNAME,
                "password": "bad",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "",
            },
        )
        assert "Ungültiger" in resp.text or "Passwort" in resp.text

    def test_no_state_param_redirect_omits_state(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        resp = client.post(
            "/oauth/authorize",
            data={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "",
            },
        )
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "state=" not in location


class TestRedirectUriAllowlist:
    """Fail-closed behaviour when the redirect_uri allowlist is not configured."""

    @pytest.fixture
    async def unconfigured_client(self, tmp_path: Path) -> TestClient:
        cfg = tmp_path / "devices.yaml"
        cfg.write_text(DEVICES_YAML, encoding="utf-8")
        store = SqliteUserStore(":memory:")
        await store.start()
        jwt_svc = JwtService(Settings(jwt_secret="test-secret"))
        auth_codes = AuthCodeStore()
        container = build_oauth_test_container(cfg, store, jwt_svc, auth_codes)
        # dev_mode=False (default) + empty allowlist → fail-closed
        settings = Settings(
            jwt_secret="test-secret",
            dev_mode=False,
            oauth_allowed_redirect_uris=[],
        )
        app = create_app(settings=settings, container=container)
        return TestClient(app, follow_redirects=False)

    def test_get_returns_503_when_allowlist_empty_and_dev_mode_off(
        self, unconfigured_client: TestClient
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = unconfigured_client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": TEST_REDIRECT_URI,
                "code_challenge": challenge,
            },
        )
        assert resp.status_code == 503

    def test_post_returns_503_when_allowlist_empty_and_dev_mode_off(
        self, unconfigured_client: TestClient
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = unconfigured_client.post(
            "/oauth/authorize",
            data={
                "username": TEST_USERNAME,
                "password": "any",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "",
            },
        )
        assert resp.status_code == 503

    def test_get_returns_400_when_uri_not_in_allowlist(
        self, client: TestClient
    ) -> None:
        _, challenge = make_pkce_pair()
        resp = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": TEST_CLIENT_ID,
                "redirect_uri": "https://evil.example.com/callback",
                "code_challenge": challenge,
            },
        )
        assert resp.status_code == 400
