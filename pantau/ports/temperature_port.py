"""TemperatureControllablePort — capability for devices with temperature control."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.models import Device


@runtime_checkable
class TemperatureControllablePort(Protocol):
    async def set_temperature(self, device: Device, celsius: float) -> None: ...

    async def get_temperature(self, device: Device) -> float: ...
