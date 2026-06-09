"""Tests for the YAML device registry adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from pantau.adapters.yaml_device_registry import YamlDeviceRegistry


@pytest.fixture
def registry(tmp_path: Path) -> YamlDeviceRegistry:
    config = tmp_path / "devices.yaml"
    config.write_text(
        """
tv:

  watch_activity: "Fernseher"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels:
    - id: "ard"
      friendly_name: "ARD"
      aliases: ["ARD", "Erstes"]
      channel_number: "1"
    - id: "zdf"
      friendly_name: "ZDF"
      aliases: ["ZDF", "Zweites"]
      channel_number: "2"
blinds:
  - id: "kueche-rollo"
    friendly_name: "Rollo Küche"
    aliases: ["Küche"]
    homekit_entity_id: "cover.kueche"
    invert: false
thermostats:
  - id: "wohnzimmer-heizung"
    friendly_name: "Heizung Wohnzimmer"
    aliases: ["Wohnzimmer"]
    fritz_name: "Wohnzimmer"
    min_celsius: 16.0
    max_celsius: 24.0
""",
        encoding="utf-8",
    )
    return YamlDeviceRegistry(config)


def test_loads_tv_config(registry: YamlDeviceRegistry) -> None:
    tv = registry.get_registry().tv
    assert tv.watch_activity == "Fernseher"


def test_loads_channels(registry: YamlDeviceRegistry) -> None:
    channels = registry.get_registry().tv.channels
    assert len(channels) == 2
    ids = {c.id for c in channels}
    assert ids == {"ard", "zdf"}


def test_channel_aliases(registry: YamlDeviceRegistry) -> None:
    zdf = registry.find_channel("zdf")
    assert zdf is not None
    assert "ZDF" in zdf.aliases
    assert zdf.channel_number == "2"


def test_find_channel_not_found(registry: YamlDeviceRegistry) -> None:
    assert registry.find_channel("unknown") is None


def test_loads_blinds(registry: YamlDeviceRegistry) -> None:
    blinds = registry.get_registry().blinds
    assert len(blinds) == 1
    assert blinds[0].homekit_entity_id == "cover.kueche"


def test_find_blind(registry: YamlDeviceRegistry) -> None:
    blind = registry.find_blind("kueche-rollo")
    assert blind is not None
    assert blind.friendly_name == "Rollo Küche"


def test_loads_thermostats(registry: YamlDeviceRegistry) -> None:
    thermostats = registry.get_registry().thermostats
    assert len(thermostats) == 1
    assert thermostats[0].fritz_name == "Wohnzimmer"


def test_find_thermostat(registry: YamlDeviceRegistry) -> None:
    t = registry.find_thermostat("wohnzimmer-heizung")
    assert t is not None
    assert t.min_celsius == 16.0
    assert t.max_celsius == 24.0


def test_find_thermostat_not_found(registry: YamlDeviceRegistry) -> None:
    assert registry.find_thermostat("unknown") is None
