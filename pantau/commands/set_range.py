"""Command: set range value (e.g. blind position) on a device."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import Percentage
from pantau.ports.range_port import RangeControllablePort

log = logging.getLogger(__name__)


class SetRangeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, percent: int) -> None:
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        Percentage(value=percent)  # validates 0–100; raises ValueError if outside range
        adapter = self._resolver.resolve(device, RangeControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "SetRange: endpoint=%s percent=%d adapter=%s",
            endpoint_id,
            percent,
            device.adapter,
        )
        await adapter.set_range(device, percent)
