"""Application settings via pydantic-settings (env vars + .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved at import time so the default is CWD-independent.
# pantau/config/settings.py → pantau/config → pantau → project root
_PROJECT_ROOT = Path(__file__).parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # Server
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8080
    debug: bool = False

    # Device config path (override via PANTAU_DEVICES_CONFIG_PATH env var)
    devices_config_path: Path = _PROJECT_ROOT / "config" / "devices.yaml"

    # AWS / S3 beacon
    aws_region: str = "eu-central-1"
    s3_beacon_bucket: str = "pantau-alexa-beacon"
    s3_beacon_key: str = "endpoint.json"

    # Security — shared secret between Lambda and home server (HMAC)
    shared_secret: SecretStr = SecretStr("")  # must be set via env in prod

    # JWT signing
    jwt_secret: SecretStr = SecretStr("")  # must be set via env in prod
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # User store
    users_db_path: Path = Path("pantau_users.db")

    # OAuth — set DEV_MODE=true to skip redirect_uri allowlist checks locally.
    # In production both settings must be provided; omitting them blocks all auth requests.
    dev_mode: bool = False
    oauth_allowed_redirect_uris: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
