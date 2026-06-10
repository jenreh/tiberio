"""Port: volume control capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.models import Device


@runtime_checkable
class VolumeControllablePort(Protocol):
    async def set_volume(self, device: Device, level: int) -> None: ...

    async def adjust_volume(self, device: Device, delta: int) -> int:
        """Adjust volume by delta steps; returns the new assumed level."""
        ...

    async def get_volume(self, device: Device) -> int:
        """Return the current (assumed) volume level."""
        ...
