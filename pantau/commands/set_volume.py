"""Command: set absolute volume on a device."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import Percentage
from pantau.ports.volume_port import VolumeControllablePort

log = logging.getLogger(__name__)


class SetVolumeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, level: int) -> None:
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        Percentage(value=level)  # validates 0–100
        adapter = self._resolver.resolve(device, VolumeControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "SetVolume: endpoint=%s level=%d adapter=%s",
            endpoint_id,
            level,
            device.adapter,
        )
        await adapter.set_volume(device, level)
