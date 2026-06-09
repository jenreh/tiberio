"""Tests for POST /oauth/token — code exchange, refresh, error paths."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.interfaces.oauth.conftest import (
    TEST_CLIENT_ID,
    TEST_PASSWORD,
    TEST_REDIRECT_URI,
    TEST_USERNAME,
    make_pkce_pair,
)


def _get_auth_code(
    client: TestClient,
    verifier: str,
    challenge: str,
    state: str = "",
) -> str:
    """Perform the authorize POST and extract the auth code from the redirect."""
    resp = client.post(
        "/oauth/authorize",
        data={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
            "redirect_uri": TEST_REDIRECT_URI,
            "client_id": TEST_CLIENT_ID,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        },
    )
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"
    location = resp.headers["location"]
    qs = parse_qs(urlparse(location).query)
    return qs["code"][0]


class TestCodeExchange:
    async def test_valid_exchange_returns_token_response(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "Bearer"
        assert "expires_in" in body
        assert "refresh_token" in body

    async def test_token_is_valid_jwt(
        self, client: TestClient, registered_user: dict, jwt_service
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        body = resp.json()
        claims = jwt_service.validate(body["access_token"])
        assert claims.user_id == registered_user["user_id"]
        assert claims.scope == "alexa"

    async def test_wrong_code_verifier_returns_invalid_grant(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": "wrong-verifier",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_wrong_redirect_uri_returns_invalid_grant(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://evil.example.com/callback",
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_unknown_code_returns_invalid_grant(
        self, client: TestClient, registered_user: dict
    ) -> None:
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "nonexistent-code",
                "code_verifier": "any-verifier",
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_code_cannot_be_reused(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        # First use — should succeed
        resp1 = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp1.status_code == 200

        # Second use — code was already redeemed
        resp2 = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"] == "invalid_grant"

    async def test_missing_fields_returns_invalid_request(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "authorization_code"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"

    async def test_wrong_client_id_returns_invalid_grant(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": "wrong-client",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_redirect_uri_mismatch_does_not_consume_code(
        self, client: TestClient, registered_user: dict
    ) -> None:
        """A failed redirect_uri check must not consume the code (client can retry)."""
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        # Submit with wrong redirect_uri — should fail but NOT consume the code
        bad = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://evil.example.com/callback",
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert bad.status_code == 400
        assert bad.json()["error"] == "invalid_grant"

        # Same code with correct redirect_uri must still work
        ok = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert ok.status_code == 200


class TestRefreshToken:
    async def test_valid_refresh_returns_new_tokens(
        self, client: TestClient, registered_user: dict
    ) -> None:
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)

        token_resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        old_refresh = token_resp.json()["refresh_token"]

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": old_refresh,
                "client_id": TEST_CLIENT_ID,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_refresh_rotates_token(
        self, client: TestClient, registered_user: dict
    ) -> None:
        """Old refresh token must be invalidated after use."""
        verifier, challenge = make_pkce_pair()
        code = _get_auth_code(client, verifier, challenge)
        token_resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": TEST_REDIRECT_URI,
                "client_id": TEST_CLIENT_ID,
            },
        )
        old_refresh = token_resp.json()["refresh_token"]

        # Use it once
        client.post(
            "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": old_refresh},
        )

        # Try to use old token again
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": old_refresh},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_invalid_refresh_token_returns_error(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": "bad-token"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    async def test_missing_refresh_token_returns_invalid_request(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "refresh_token"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"


class TestUnsupportedGrantType:
    async def test_unknown_grant_type_returns_error(self, client: TestClient) -> None:
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "implicit"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "unsupported_grant_type"
