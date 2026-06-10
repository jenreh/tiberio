"""Command: adjust range value by a delta (e.g. blind position delta)."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.ports.range_port import RangeControllablePort

log = logging.getLogger(__name__)


class AdjustRangeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, delta: int) -> int:
        """Adjust the range by delta; returns the new position."""
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        adapter = self._resolver.resolve(device, RangeControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "AdjustRange: endpoint=%s delta=%d adapter=%s",
            endpoint_id,
            delta,
            device.adapter,
        )
        return await adapter.adjust_range(device, delta)
