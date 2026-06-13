"""Tests for the YAML device registry adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from tiberio.adapters.yaml_device_registry import YamlDeviceRegistry
from tiberio.domain.models import Thermostat, TvAudio, TvChannel, WindowBlind


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
    aliases: ["den Fernseher", "TV"]
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


def test_channel_watch_activity_populated(registry: YamlDeviceRegistry) -> None:
    device = registry.find_device("zdf")
    assert isinstance(device, TvChannel)
    assert device.watch_activity == "Fernseher"
    assert device.channel_number == "2"


def test_channel_aliases(registry: YamlDeviceRegistry) -> None:
    device = registry.find_device("zdf")
    assert isinstance(device, TvChannel)
    assert "ZDF" in device.aliases


def test_find_device_channel_not_found(registry: YamlDeviceRegistry) -> None:
    assert registry.find_device("unknown") is None


def test_loads_blinds(registry: YamlDeviceRegistry) -> None:
    blinds = registry.get_registry().blinds
    assert len(blinds) == 1
    assert blinds[0].external_id == "cover.kueche"


def test_find_device_blind(registry: YamlDeviceRegistry) -> None:
    device = registry.find_device("kueche-rollo")
    assert isinstance(device, WindowBlind)
    assert device.name == "Rollo Küche"
    assert device.external_id == "cover.kueche"


def test_loads_thermostats(registry: YamlDeviceRegistry) -> None:
    thermostats = registry.get_registry().thermostats
    assert len(thermostats) == 1
    assert thermostats[0].external_id == "Wohnzimmer"


def test_find_device_thermostat(registry: YamlDeviceRegistry) -> None:
    device = registry.find_device("wohnzimmer-heizung")
    assert isinstance(device, Thermostat)
    assert device.min_celsius == 16.0
    assert device.max_celsius == 24.0


def test_find_device_thermostat_not_found(registry: YamlDeviceRegistry) -> None:
    assert registry.find_device("unknown") is None


def test_find_device_audio(registry: YamlDeviceRegistry) -> None:
    device = registry.find_device("tv-audio")
    assert device is not None
    assert device.id == "tv-audio"
    assert device.adapter == "harmony"
    assert device.aliases == ("den Fernseher", "TV")
    assert isinstance(device, TvAudio)
    assert device.watch_activity == "Fernseher"


def test_duplicate_device_ids_raise_value_error(tmp_path: Path) -> None:
    config = tmp_path / "devices.yaml"
    config.write_text(
        """
tv:
  watch_activity: "TV"
  audio:
    id: "doppelt"
    friendly_name: "Fernseher"
  channels: []
blinds:
  - id: "doppelt"
    friendly_name: "Rollo"
    homekit_entity_id: "cover.x"
thermostats: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="doppelt"):
        YamlDeviceRegistry(config)
