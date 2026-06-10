"""Command: turn on a device by resolving its adapter via device.adapter."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.ports.power_port import PowerablePort

log = logging.getLogger(__name__)


class TurnOnCommand(DeviceCommand):
    async def execute(self, endpoint_id: str) -> None:
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        adapter = self._resolver.resolve(device, PowerablePort)  # type: ignore[type-abstract]
        log.debug("TurnOn: endpoint=%s adapter=%s", endpoint_id, device.adapter)
        await adapter.turn_on(device)
