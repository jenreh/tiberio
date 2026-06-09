"""Tests for heating commands: SetThermostatTemperatureCommand."""

from __future__ import annotations

import pytest

from pantau.adapters.mock_thermostat_adapter import MockThermostatAdapter
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.commands.heating.set_thermostat_temperature import (
    SetThermostatTemperatureCommand,
)
from pantau.domain.errors import DeviceNotFoundError


class TestSetThermostatTemperature:
    @pytest.fixture
    def adapter(self) -> MockThermostatAdapter:
        return MockThermostatAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockThermostatAdapter
    ) -> SetThermostatTemperatureCommand:
        return SetThermostatTemperatureCommand(registry, adapter)

    async def test_sets_temperature_on_adapter(
        self, command: SetThermostatTemperatureCommand, adapter: MockThermostatAdapter
    ) -> None:
        await command.execute("wohnzimmer-heizung", 22.0)
        assert adapter.set_temperature_calls == [("Wohnzimmer", 22.0)]

    async def test_rounds_to_half_degree(
        self, command: SetThermostatTemperatureCommand, adapter: MockThermostatAdapter
    ) -> None:
        await command.execute("wohnzimmer-heizung", 21.3)
        assert adapter.set_temperature_calls == [("Wohnzimmer", 21.5)]

    async def test_temperature_at_device_min(
        self, command: SetThermostatTemperatureCommand, adapter: MockThermostatAdapter
    ) -> None:
        await command.execute("wohnzimmer-heizung", 16.0)
        assert adapter.set_temperature_calls == [("Wohnzimmer", 16.0)]

    async def test_temperature_at_device_max(
        self, command: SetThermostatTemperatureCommand, adapter: MockThermostatAdapter
    ) -> None:
        await command.execute("wohnzimmer-heizung", 24.0)
        assert adapter.set_temperature_calls == [("Wohnzimmer", 24.0)]

    async def test_temperature_below_device_min_raises(
        self, command: SetThermostatTemperatureCommand
    ) -> None:
        with pytest.raises(ValueError, match="device range"):
            await command.execute("wohnzimmer-heizung", 15.0)

    async def test_temperature_above_device_max_raises(
        self, command: SetThermostatTemperatureCommand
    ) -> None:
        with pytest.raises(ValueError, match="device range"):
            await command.execute("wohnzimmer-heizung", 25.0)

    async def test_unknown_endpoint_raises(
        self, command: SetThermostatTemperatureCommand
    ) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("does-not-exist", 20.0)
