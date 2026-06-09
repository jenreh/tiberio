"""Use-case: set the target temperature of a thermostat."""

from __future__ import annotations

import logging

from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import Temperature
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.thermostat_port import ThermostatPort

log = logging.getLogger(__name__)


class SetThermostatTemperatureCommand:
    def __init__(
        self,
        registry: DeviceRegistryPort,
        thermostat: ThermostatPort,
    ) -> None:
        self._registry = registry
        self._thermostat = thermostat

    async def execute(self, endpoint_id: str, celsius: float) -> None:
        device = self._registry.find_thermostat(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)

        temp = Temperature.from_float(celsius)
        if not (device.min_celsius <= temp.celsius <= device.max_celsius):
            msg = (
                f"Temperature {temp.celsius}°C is outside the device range "
                f"{device.min_celsius}–{device.max_celsius}°C"
            )
            raise ValueError(msg)

        log.info(
            "SetThermostatTemperature: endpoint=%s fritz_name=%s celsius=%.1f",
            endpoint_id,
            device.fritz_name,
            temp.celsius,
        )
        await self._thermostat.set_temperature(device.fritz_name, temp.celsius)
