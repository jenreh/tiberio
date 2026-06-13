"""Use-case: return all configured devices for Alexa discovery."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tiberio.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)

CapabilityKind = Literal["power", "speaker", "range", "thermostat"]


class DiscoveredDevice(BaseModel):
    """Minimal device descriptor used by Phase 3 to build Alexa Discovery responses.

    A device may expose several capabilities (e.g. the TV audio endpoint is both
    a speaker and powerable). The first entry is the *primary* capability and
    drives the Alexa display category.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    capabilities: tuple[CapabilityKind, ...]


class DiscoverDevicesCommand:
    def __init__(self, registry: DeviceRegistryPort) -> None:
        self._registry = registry

    async def execute(self) -> list[DiscoveredDevice]:
        registry = self._registry.get_registry()

        channels = [
            DiscoveredDevice(id=ch.id, name=ch.name, capabilities=("power",))
            for ch in (registry.tv.channels if registry.tv else ())
        ]
        audio = (
            [
                DiscoveredDevice(
                    id=registry.tv.audio.id,
                    name=registry.tv.audio.name,
                    capabilities=("speaker", "power"),
                )
            ]
            if registry.tv
            else []
        )
        blinds = [
            DiscoveredDevice(id=b.id, name=b.name, capabilities=("range",))
            for b in registry.blinds
        ]
        thermostats = [
            DiscoveredDevice(id=t.id, name=t.name, capabilities=("thermostat",))
            for t in registry.thermostats
        ]

        devices = channels + audio + blinds + thermostats
        log.info("DiscoverDevices: %d devices found", len(devices))
        return devices
