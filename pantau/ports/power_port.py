"""PowerablePort — capability for devices that can be powered on/off."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.models import Device


@runtime_checkable
class PowerablePort(Protocol):
    async def turn_on(self, device: Device) -> None: ...

    async def turn_off(self, device: Device) -> None: ...
