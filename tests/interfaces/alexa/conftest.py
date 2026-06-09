"""Shared fixtures for Alexa interface tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pantau.api.app import create_app
from pantau.composition import build_test_container

DEVICES_YAML = """
tv:
  watch_activity: "Fernseher"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "zdf"
      friendly_name: "ZDF"
      channel_number: "2"
    - id: "ard"
      friendly_name: "ARD"
      channel_number: "1"
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
def devices_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")
    return cfg


@pytest.fixture
def client(devices_config: Path) -> TestClient:
    container = build_test_container(devices_config)
    app = create_app(container=container)
    return TestClient(app)


def directive(
    namespace: str,
    name: str,
    endpoint_id: str = "test-endpoint",
    payload: dict | None = None,
    correlation_token: str = "test-correlation-token",  # noqa: S107
    bearer_token: str = "test-bearer-token",  # noqa: S107
    instance: str | None = None,
) -> dict:
    """Build a minimal but valid Alexa directive request body."""
    header: dict = {
        "namespace": namespace,
        "name": name,
        "messageId": "test-message-id",
        "correlationToken": correlation_token,
        "payloadVersion": "3",
    }
    if instance is not None:
        header["instance"] = instance

    return {
        "directive": {
            "header": header,
            "endpoint": {
                "scope": {"type": "BearerToken", "token": bearer_token},
                "endpointId": endpoint_id,
                "cookie": {},
            },
            "payload": payload or {},
        }
    }


def discovery_directive(bearer_token: str = "test-bearer-token") -> dict:  # noqa: S107
    """Build a minimal Alexa.Discovery.Discover directive."""
    return {
        "directive": {
            "header": {
                "namespace": "Alexa.Discovery",
                "name": "Discover",
                "messageId": "test-message-id",
                "payloadVersion": "3",
            },
            "payload": {"scope": {"type": "BearerToken", "token": bearer_token}},
        }
    }
