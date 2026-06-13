"""TemperatureControllablePort — capability for devices with temperature control."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tiberio.domain.models import Device


@runtime_checkable
class TemperatureControllablePort(Protocol):
    async def set_temperature(self, device: Device, celsius: float) -> None: ...

    async def get_temperature(self, device: Device) -> float:
        """Return the target setpoint in °C."""
        ...

    async def get_current_temperature(self, device: Device) -> float:
        """Return the measured current temperature in °C."""
        ...
