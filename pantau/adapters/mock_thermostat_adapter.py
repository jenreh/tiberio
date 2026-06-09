"""Mock thermostat adapter — logs operations, records calls, no real FRITZ!Box connection."""

from __future__ import annotations

import logging

from pantau.domain.models import FritzDevice

log = logging.getLogger(__name__)


class MockThermostatAdapter:
    """Stub implementation of ThermostatPort for development and testing."""

    def __init__(self) -> None:
        self._temperatures: dict[str, float] = {}
        self.set_temperature_calls: list[tuple[str, float]] = []
        self._fritz_devices: list[FritzDevice] = []

    async def set_temperature(self, fritz_name: str, celsius: float) -> None:
        log.info(
            "MockThermostat: set_temperature name=%s celsius=%.1f", fritz_name, celsius
        )
        self._temperatures[fritz_name] = celsius
        self.set_temperature_calls.append((fritz_name, celsius))

    async def get_temperature(self, fritz_name: str) -> float:
        temp = self._temperatures.get(fritz_name, 20.0)
        log.info("MockThermostat: get_temperature name=%s -> %.1f", fritz_name, temp)
        return temp

    async def list_devices(self) -> list[FritzDevice]:
        log.info("MockThermostat: list_devices count=%d", len(self._fritz_devices))
        return list(self._fritz_devices)
