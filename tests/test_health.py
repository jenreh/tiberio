"""Tests for the /health endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pantau.api.app import create_app
from pantau.config.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    config = tmp_path / "devices.yaml"
    config.write_text(
        """
tv:
  watch_activity: "TV"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "ard"
      friendly_name: "ARD"
      channel_number: "1"
    - id: "zdf"
      friendly_name: "ZDF"
      channel_number: "2"
blinds:
  - id: "kueche-rollo"
    friendly_name: "Rollo Küche"
    homekit_entity_id: "cover.kueche"
thermostats:
  - id: "wohnzimmer-heizung"
    friendly_name: "Heizung Wohnzimmer"
    fritz_name: "Wohnzimmer"
""",
        encoding="utf-8",
    )
    return Settings(devices_config_path=config)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings=settings)
    return TestClient(app)


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_status_ok(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_health_reports_device_counts(client: TestClient) -> None:
    body = client.get("/health").json()
    devices = body["devices"]
    assert devices["channels"] == 2
    assert devices["blinds"] == 1
    assert devices["thermostats"] == 1
