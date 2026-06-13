"""Tests for DiscoverDevicesCommand."""

from __future__ import annotations

from tiberio.adapters.yaml_device_registry import YamlDeviceRegistry
from tiberio.commands.discover_devices import DiscoverDevicesCommand


class TestDiscoverDevices:
    async def test_returns_all_channels_as_power(
        self, registry: YamlDeviceRegistry
    ) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        power_ids = {d.id for d in devices if "power" in d.capabilities}
        assert {"ard", "zdf"} <= power_ids

    async def test_returns_tv_audio_as_speaker(
        self, registry: YamlDeviceRegistry
    ) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        speaker = next(d for d in devices if "speaker" in d.capabilities)
        assert speaker.id == "tv-audio"
        assert speaker.name == "Fernseher"

    async def test_tv_audio_exposes_both_speaker_and_power(
        self, registry: YamlDeviceRegistry
    ) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        audio = next(d for d in devices if d.id == "tv-audio")
        assert "speaker" in audio.capabilities
        assert "power" in audio.capabilities

    async def test_returns_blinds_as_range(self, registry: YamlDeviceRegistry) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        range_ids = {d.id for d in devices if "range" in d.capabilities}
        assert range_ids == {"kueche-rollo", "wohnzimmer-rollo"}

    async def test_returns_thermostats_as_thermostat(
        self, registry: YamlDeviceRegistry
    ) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        thermo = next(d for d in devices if "thermostat" in d.capabilities)
        assert thermo.id == "wohnzimmer-heizung"

    async def test_total_device_count(self, registry: YamlDeviceRegistry) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        # 2 channels + 1 audio + 2 blinds + 1 thermostat = 6
        assert len(devices) == 6

    async def test_all_devices_have_names(self, registry: YamlDeviceRegistry) -> None:
        devices = await DiscoverDevicesCommand(registry).execute()
        assert all(d.name for d in devices)
