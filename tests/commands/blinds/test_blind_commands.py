"""Tests for blind commands: SetBlindPositionCommand."""

from __future__ import annotations

import pytest

from pantau.adapters.mock_blind_adapter import MockBlindAdapter
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.commands.blinds.set_blind_position import SetBlindPositionCommand
from pantau.domain.errors import DeviceNotFoundError


class TestSetBlindPosition:
    @pytest.fixture
    def adapter(self) -> MockBlindAdapter:
        return MockBlindAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockBlindAdapter
    ) -> SetBlindPositionCommand:
        return SetBlindPositionCommand(registry, adapter)

    async def test_sets_position_on_adapter(
        self, command: SetBlindPositionCommand, adapter: MockBlindAdapter
    ) -> None:
        await command.execute("kueche-rollo", 50)
        assert adapter.set_position_calls == [("cover.kueche", 50)]

    async def test_position_closed(
        self, command: SetBlindPositionCommand, adapter: MockBlindAdapter
    ) -> None:
        await command.execute("kueche-rollo", 0)
        assert adapter.set_position_calls == [("cover.kueche", 0)]

    async def test_position_open(
        self, command: SetBlindPositionCommand, adapter: MockBlindAdapter
    ) -> None:
        await command.execute("kueche-rollo", 100)
        assert adapter.set_position_calls == [("cover.kueche", 100)]

    async def test_invert_flips_position(
        self, command: SetBlindPositionCommand, adapter: MockBlindAdapter
    ) -> None:
        await command.execute("wohnzimmer-rollo", 30)
        assert adapter.set_position_calls == [("cover.wohnzimmer", 70)]

    async def test_invert_half_stays_half(
        self, command: SetBlindPositionCommand, adapter: MockBlindAdapter
    ) -> None:
        await command.execute("wohnzimmer-rollo", 50)
        assert adapter.set_position_calls == [("cover.wohnzimmer", 50)]

    async def test_invalid_percentage_raises(
        self, command: SetBlindPositionCommand
    ) -> None:
        with pytest.raises(ValueError):
            await command.execute("kueche-rollo", 101)

    async def test_unknown_endpoint_raises(
        self, command: SetBlindPositionCommand
    ) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("does-not-exist", 50)
