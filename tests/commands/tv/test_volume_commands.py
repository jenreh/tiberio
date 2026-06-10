"""Tests for volume commands: SetVolumeCommand and AdjustVolumeCommand."""

from __future__ import annotations

import pytest

from pantau.adapters.mock_tv_adapter import MockTvAdapter
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.commands.adjust_volume import AdjustVolumeCommand
from pantau.commands.set_volume import SetVolumeCommand
from pantau.composition import Container
from pantau.domain.errors import DeviceNotFoundError


def _container(adapter: MockTvAdapter, registry: YamlDeviceRegistry) -> Container:
    c = Container()
    c.register(type(adapter), adapter, adapter_name="harmony")
    return c


class TestSetVolumeCommand:
    @pytest.fixture
    def adapter(self) -> MockTvAdapter:
        return MockTvAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockTvAdapter
    ) -> SetVolumeCommand:
        return SetVolumeCommand(registry, _container(adapter, registry))  # type: ignore[arg-type]

    async def test_calls_adapter_with_device_and_level(
        self, command: SetVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", level=70)
        assert len(adapter.set_volume_calls) == 1
        device, level = adapter.set_volume_calls[0]
        assert device.id == "tv-audio"
        assert level == 70

    async def test_level_zero(
        self, command: SetVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", level=0)
        _, level = adapter.set_volume_calls[0]
        assert level == 0

    async def test_level_100(
        self, command: SetVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", level=100)
        _, level = adapter.set_volume_calls[0]
        assert level == 100

    async def test_level_above_100_raises(self, command: SetVolumeCommand) -> None:
        with pytest.raises(ValueError):
            await command.execute("tv-audio", level=101)

    async def test_level_below_0_raises(self, command: SetVolumeCommand) -> None:
        with pytest.raises(ValueError):
            await command.execute("tv-audio", level=-1)

    async def test_unknown_endpoint_raises(self, command: SetVolumeCommand) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("does-not-exist", level=50)


class TestAdjustVolumeCommand:
    @pytest.fixture
    def adapter(self) -> MockTvAdapter:
        return MockTvAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockTvAdapter
    ) -> AdjustVolumeCommand:
        return AdjustVolumeCommand(registry, _container(adapter, registry))  # type: ignore[arg-type]

    async def test_returns_new_volume_level(
        self, command: AdjustVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        adapter._assumed_volume = 40
        result = await command.execute("tv-audio", delta=10)
        assert result == 50

    async def test_negative_delta_decreases_volume(
        self, command: AdjustVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        adapter._assumed_volume = 60
        result = await command.execute("tv-audio", delta=-15)
        assert result == 45

    async def test_clamps_at_100(
        self, command: AdjustVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        adapter._assumed_volume = 95
        result = await command.execute("tv-audio", delta=20)
        assert result == 100

    async def test_clamps_at_0(
        self, command: AdjustVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        adapter._assumed_volume = 5
        result = await command.execute("tv-audio", delta=-20)
        assert result == 0

    async def test_records_call(
        self, command: AdjustVolumeCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", delta=5)
        assert len(adapter.adjust_volume_calls) == 1
        device, delta = adapter.adjust_volume_calls[0]
        assert device.id == "tv-audio"
        assert delta == 5

    async def test_unknown_endpoint_raises(self, command: AdjustVolumeCommand) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("does-not-exist", delta=10)
