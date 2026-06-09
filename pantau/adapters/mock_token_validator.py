"""Adapter: mock token validator for tests.

Accepts any non-empty token; returns fixed claims. Used by build_test_container
so existing directive router tests work without real JWTs.
"""

from __future__ import annotations

from pantau.ports.token_validator_port import TokenClaims


class MockTokenValidator:
    """Validates any non-empty token — for tests only."""

    def validate(self, token: str) -> TokenClaims:
        if not token:
            raise ValueError("Empty token")
        return TokenClaims(user_id="test-user", scope="alexa")
