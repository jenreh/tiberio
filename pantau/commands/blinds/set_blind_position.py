"""Use-case: set the position of a roller blind."""

from __future__ import annotations

import logging

from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import Percentage
from pantau.ports.blind_port import BlindPort
from pantau.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)


class SetBlindPositionCommand:
    def __init__(self, registry: DeviceRegistryPort, blind: BlindPort) -> None:
        self._registry = registry
        self._blind = blind

    async def execute(self, endpoint_id: str, percent: int) -> None:
        device = self._registry.find_blind(endpoint_id)
        if device is None:
            raise DeviceNotFoundError(endpoint_id)

        position = Percentage(value=percent)
        # invert=True flips the axis so that 100% Alexa == 0% HomeKit (closed)
        actual = (100 - position.value) if device.invert else position.value

        log.info(
            "SetBlindPosition: endpoint=%s entity=%s percent=%d actual=%d invert=%s",
            endpoint_id,
            device.homekit_entity_id,
            percent,
            actual,
            device.invert,
        )
        await self._blind.set_position(device.homekit_entity_id, actual)
