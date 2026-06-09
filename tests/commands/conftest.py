"""Shared fixtures for command tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pantau.adapters.yaml_device_registry import YamlDeviceRegistry

DEVICES_YAML = """
tv:
  harmony_host: "192.168.1.50"
  watch_activity: "Fernseher"
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
    invert: false
  - id: "wohnzimmer-rollo"
    friendly_name: "Rollo Wohnzimmer"
    homekit_entity_id: "cover.wohnzimmer"
    invert: true
thermostats:
  - id: "wohnzimmer-heizung"
    friendly_name: "Heizung Wohnzimmer"
    fritz_name: "Wohnzimmer"
    min_celsius: 16.0
    max_celsius: 24.0
"""


@pytest.fixture
def registry(tmp_path: Path) -> YamlDeviceRegistry:
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")
    return YamlDeviceRegistry(cfg)
