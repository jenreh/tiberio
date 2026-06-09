"""Use-case: return all configured devices for Alexa discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pantau.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)

CapabilityKind = Literal["power", "speaker", "range", "thermostat"]


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """Minimal device descriptor used by Phase 3 to build Alexa Discovery responses."""

    id: str
    friendly_name: str
    capability: CapabilityKind


class DiscoverDevicesCommand:
    def __init__(self, registry: DeviceRegistryPort) -> None:
        self._registry = registry

    async def execute(self) -> list[DiscoveredDevice]:
        registry = self._registry.get_registry()

        channels = [
            DiscoveredDevice(
                id=ch.id, friendly_name=ch.friendly_name, capability="power"
            )
            for ch in registry.tv.channels
        ]
        audio = [
            DiscoveredDevice(
                id=registry.tv.audio.id,
                friendly_name=registry.tv.audio.friendly_name,
                capability="speaker",
            )
        ]
        blinds = [
            DiscoveredDevice(id=b.id, friendly_name=b.friendly_name, capability="range")
            for b in registry.blinds
        ]
        thermostats = [
            DiscoveredDevice(
                id=t.id, friendly_name=t.friendly_name, capability="thermostat"
            )
            for t in registry.thermostats
        ]

        devices = channels + audio + blinds + thermostats
        log.info("DiscoverDevices: %d devices found", len(devices))
        return devices
