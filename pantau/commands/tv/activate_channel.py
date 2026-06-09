"""Use-case: activate a TV channel (ensure activity, then set channel)."""

from __future__ import annotations

import logging

from pantau.domain.errors import DeviceNotFoundError
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.tv_port import TvPort

log = logging.getLogger(__name__)


class ActivateChannelCommand:
    def __init__(self, registry: DeviceRegistryPort, tv: TvPort) -> None:
        self._registry = registry
        self._tv = tv

    async def execute(self, endpoint_id: str) -> None:
        registry = self._registry.get_registry()
        channel = self._registry.find_channel(endpoint_id)
        if channel is None:
            raise DeviceNotFoundError(endpoint_id)

        log.info(
            "ActivateChannel: endpoint=%s channel=%s activity=%s",
            endpoint_id,
            channel.channel_number,
            registry.tv.watch_activity,
        )
        await self._tv.ensure_activity(registry.tv.watch_activity)
        await self._tv.set_channel(channel.channel_number)
