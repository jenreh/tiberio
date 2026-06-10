"""Command: set thermostat temperature on a device."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceCapabilityError, DeviceNotFoundError
from pantau.domain.models import Thermostat
from pantau.domain.values import Temperature
from pantau.ports.temperature_port import TemperatureControllablePort

log = logging.getLogger(__name__)


class SetTemperatureCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, celsius: float) -> None:
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        if not isinstance(device, Thermostat):
            raise DeviceCapabilityError(endpoint_id, "TemperatureControllable")
        temp = Temperature.from_float(celsius)
        if not (device.min_celsius <= temp.celsius <= device.max_celsius):
            raise ValueError(
                f"Temperature {temp.celsius}°C is outside the valid range "
                f"{device.min_celsius}–{device.max_celsius}°C"
            )
        adapter = self._resolver.resolve(device, TemperatureControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "SetTemperature: endpoint=%s celsius=%.1f adapter=%s",
            endpoint_id,
            temp.celsius,
            device.adapter,
        )
        await adapter.set_temperature(device, temp.celsius)
