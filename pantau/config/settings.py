"""Application settings via pydantic-settings (reads from os.environ; .env loaded by dotenv at startup)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved at import time so the default is CWD-independent.
# pantau/config/settings.py → pantau/config → pantau → project root
_PROJECT_ROOT = Path(__file__).parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="PANTAU_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # Server
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8080
    debug: bool = False

    devices_config_path: Path = _PROJECT_ROOT / "config" / "devices.yaml"

    # Logging / observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        """Accept lowercase env values; reject unknown levels at construction."""
        return value.upper() if isinstance(value, str) else value

    # AWS / S3 beacon
    aws_region: str = "eu-central-1"
    s3_beacon_bucket: str = "pantau-alexa-beacon"
    s3_beacon_key: str = "endpoint.json"
    public_base_url: str = ""  # current tunnel URL announced via the beacon
    beacon_enabled: bool = False
    beacon_update_interval_seconds: int = 300

    # Security — shared secret between Lambda and home server (HMAC).
    # When set, /alexa/directive requires X-Pantau-Timestamp/-Signature headers.
    shared_secret: SecretStr = SecretStr("")  # must be set via env in prod
    hmac_tolerance_seconds: int = 300  # replay-protection window
    max_directive_body_bytes: int = 65536  # /alexa/directive request-body cap

    # JWT signing
    jwt_secret: SecretStr = SecretStr("")  # must be set via env in prod
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # User store
    users_db_path: Path = Path("pantau_users.db")

    # Rate limiting — login and token endpoints (per client IP / username)
    rate_limit_max_attempts: int = 10
    rate_limit_window_seconds: int = 60

    # OAuth — set DEV_MODE=true to skip redirect_uri allowlist checks locally.
    # In production both settings must be provided; omitting them blocks all auth requests.
    dev_mode: bool = False
    oauth_allowed_redirect_uris: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
