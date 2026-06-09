"""Shared fixtures for OAuth interface tests."""

from __future__ import annotations

import base64
import hashlib
import secrets
from pathlib import Path

import bcrypt as _bcrypt
import pytest
from fastapi.testclient import TestClient

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.jwt_service import JwtService
from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.api.app import create_app
from pantau.composition import build_oauth_test_container
from pantau.config.settings import Settings

TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpassword123"  # noqa: S105
TEST_CLIENT_ID = "alexa"
TEST_REDIRECT_URI = "https://alexa.amazon.com/callback"

DEVICES_YAML = """
tv:
  harmony_host: "192.168.1.50"
  watch_activity: "Fernseher"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "zdf"
      friendly_name: "ZDF"
      channel_number: "2"
blinds:
  - id: "kueche-rollo"
    friendly_name: "Rollo Küche"
    homekit_entity_id: "cover.kueche"
    invert: false
thermostats:
  - id: "wohnzimmer-heizung"
    friendly_name: "Heizung Wohnzimmer"
    fritz_name: "Wohnzimmer"
    min_celsius: 16.0
    max_celsius: 24.0
"""


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="oauth-test-secret", jwt_access_token_expire_minutes=60)


@pytest.fixture
async def user_store(tmp_path: Path) -> SqliteUserStore:
    store = SqliteUserStore(tmp_path / "oauth_test.db")
    await store.start()
    yield store
    await store.stop()


@pytest.fixture
def jwt_service(settings: Settings) -> JwtService:
    return JwtService(settings)


@pytest.fixture
def auth_codes() -> AuthCodeStore:
    return AuthCodeStore()


@pytest.fixture
def devices_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")
    return cfg


@pytest.fixture
async def client(
    devices_config: Path,
    user_store: SqliteUserStore,
    jwt_service: JwtService,
    auth_codes: AuthCodeStore,
    settings: Settings,
) -> TestClient:
    container = build_oauth_test_container(
        devices_config, user_store, jwt_service, auth_codes
    )
    app = create_app(settings=settings, container=container)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
async def registered_user(user_store: SqliteUserStore) -> dict:
    """Create a test user and return its credentials."""
    hashed = _bcrypt.hashpw(TEST_PASSWORD.encode(), _bcrypt.gensalt()).decode()
    user = await user_store.create_user(TEST_USERNAME, hashed)
    return {"user_id": user.id, "username": TEST_USERNAME, "password": TEST_PASSWORD}


def make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256) pair."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
