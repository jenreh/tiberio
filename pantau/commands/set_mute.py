"""Command: set mute state on a device by resolving its adapter via device.adapter."""

from __future__ import annotations

import logging

from pantau.commands._base import DeviceCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.ports.mute_port import MuteControllablePort

log = logging.getLogger(__name__)


class SetMuteCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, mute: bool) -> None:
        device = self._registry.find_device(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)
        adapter = self._resolver.resolve(device, MuteControllablePort)  # type: ignore[type-abstract]
        log.debug(
            "SetMute: endpoint=%s mute=%s adapter=%s", endpoint_id, mute, device.adapter
        )
        await adapter.set_mute(device, mute)
