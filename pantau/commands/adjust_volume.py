"""Command: adjust volume by a relative delta on a device."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.ports.volume_port import VolumeControllablePort

log = logging.getLogger(__name__)


class AdjustVolumeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, delta: int) -> int:
        """Adjust volume by delta steps; returns the new assumed level."""
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        adapter = self._resolver.resolve(device, VolumeControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "AdjustVolume: endpoint=%s delta=%d adapter=%s",
            endpoint_id,
            delta,
            device.adapter,
        )
        return await adapter.adjust_volume(device, delta)
