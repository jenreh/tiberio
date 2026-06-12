"""Startup validation: insecure secrets and beacon misconfiguration fail fast."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from pantau.api.app import create_app
from pantau.config.settings import Settings

DEVICES_YAML = """
tv:
  watch_activity: "TV"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "ard"
      friendly_name: "ARD"
      channel_number: "1"
blinds: []
thermostats: []
"""


@pytest.fixture
def devices_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")
    return cfg


def test_empty_jwt_secret_without_dev_mode_fails_fast(devices_config: Path) -> None:
    settings = Settings(devices_config_path=devices_config, dev_mode=False)
    with pytest.raises(RuntimeError, match="PANTAU_JWT_SECRET"):
        create_app(settings=settings)


def test_empty_jwt_secret_with_dev_mode_boots(devices_config: Path) -> None:
    settings = Settings(devices_config_path=devices_config, dev_mode=True)
    app = create_app(settings=settings)
    assert app is not None


def test_short_jwt_secret_without_dev_mode_fails_fast(devices_config: Path) -> None:
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=False,
        jwt_secret=SecretStr("short"),
    )
    with pytest.raises(RuntimeError, match="32"):
        create_app(settings=settings)


def test_strong_jwt_secret_without_dev_mode_boots(devices_config: Path) -> None:
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=False,
        jwt_secret=SecretStr("x" * 32),
    )
    app = create_app(settings=settings)
    assert app is not None


def test_beacon_enabled_without_public_base_url_fails_fast(
    devices_config: Path,
) -> None:
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=True,
        beacon_enabled=True,
        public_base_url="",
    )
    with pytest.raises(RuntimeError, match="PANTAU_PUBLIC_BASE_URL"):
        create_app(settings=settings)


def test_beacon_with_http_url_without_dev_mode_fails_fast(
    devices_config: Path,
) -> None:
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=False,
        jwt_secret=SecretStr("x" * 32),
        beacon_enabled=True,
        public_base_url="http://tunnel.example.com",
    )
    with pytest.raises(RuntimeError, match="https://"):
        create_app(settings=settings)


def test_beacon_with_http_url_in_dev_mode_boots(
    devices_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Stub boto3 — an enabled beacon wires the real S3 adapter, and client
    # construction must not touch the host's AWS credential chain in tests.
    import pantau.adapters.s3_beacon_publisher as s3_module  # noqa: PLC0415

    class _FakeBoto3:
        @staticmethod
        def client(
            service_name: str,  # noqa: ARG004
            region_name: str | None = None,  # noqa: ARG004
        ) -> object:
            return object()

    monkeypatch.setattr(s3_module, "boto3", _FakeBoto3)
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=True,
        beacon_enabled=True,
        public_base_url="http://localhost:8080",
    )
    app = create_app(settings=settings)
    assert app is not None


def test_beacon_disabled_ignores_empty_public_base_url(devices_config: Path) -> None:
    settings = Settings(
        devices_config_path=devices_config,
        dev_mode=True,
        beacon_enabled=False,
        public_base_url="",
    )
    app = create_app(settings=settings)
    assert app is not None
