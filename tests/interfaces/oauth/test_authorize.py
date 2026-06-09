"""Tests for GET/POST /oauth/authorize — login form and auth code issuance."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.interfaces.oauth.conftest import (
    TEST_CLIENT_ID,
    TEST_PASSWORD,
    TEST_REDIRECT_URI,
    TEST_USERNAME,
    make_pkce_pair,
)


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
