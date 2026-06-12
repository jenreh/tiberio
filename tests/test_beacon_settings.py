"""Beacon settings — defaults and env overrides."""

from __future__ import annotations

import pytest

from pantau.config.settings import Settings


def test_beacon_settings_defaults() -> None:
    settings = Settings()
    assert settings.public_base_url == ""
    assert settings.beacon_enabled is False
    assert settings.beacon_update_interval_seconds == 300


def test_beacon_settings_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANTAU_PUBLIC_BASE_URL", "https://tunnel.example.com")
    monkeypatch.setenv("PANTAU_BEACON_ENABLED", "true")
    monkeypatch.setenv("PANTAU_BEACON_UPDATE_INTERVAL_SECONDS", "60")

    settings = Settings()

    assert settings.public_base_url == "https://tunnel.example.com"
    assert settings.beacon_enabled is True
    assert settings.beacon_update_interval_seconds == 60
