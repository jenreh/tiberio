"""Mock thermostat adapter — logs operations, records calls, no real FRITZ!Box connection."""

from __future__ import annotations

import logging

from tiberio.domain.models import ADAPTER_FRITZ, Device, LiveThermostat
from tiberio.ports.listable_port import BackendListResult

log = logging.getLogger(__name__)


class MockThermostatAdapter:
    """Stub implementation of TemperatureControllablePort and ListablePort for testing."""

    adapter_name = ADAPTER_FRITZ

    def __init__(self) -> None:
        self._temperatures: dict[str, float] = {}
        self._current_temperatures: dict[str, float] = {}
        self.set_temperature_calls: list[tuple[Device, float]] = []
        self._devices: list[LiveThermostat] = []

    async def set_temperature(self, device: Device, celsius: float) -> None:
        log.info(
            "MockThermostat: set_temperature device=%s celsius=%.1f", device.id, celsius
        )
        self._temperatures[device.id] = celsius
        self.set_temperature_calls.append((device, celsius))

    async def get_temperature(self, device: Device) -> float:
        temp = self._temperatures.get(device.id, 20.0)
        log.info("MockThermostat: get_temperature device=%s -> %.1f", device.id, temp)
        return temp

    async def get_current_temperature(self, device: Device) -> float:
        temp = self._current_temperatures.get(device.id, 21.5)
        log.info(
            "MockThermostat: get_current_temperature device=%s -> %.1f",
            device.id,
            temp,
        )
        return temp

    async def list_backend(self) -> BackendListResult:
        log.info("MockThermostat: list_backend devices=%d", len(self._devices))
        return BackendListResult(
            status="ok",
            data={"devices": [d.model_dump() for d in self._devices]},
        )
