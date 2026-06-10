"""MuteControllablePort — capability for devices with mute control."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.models import Device


@runtime_checkable
class MuteControllablePort(Protocol):
    async def set_mute(self, device: Device, muted: bool) -> None: ...

    async def get_mute(self, device: Device) -> bool:
        """Return the current (assumed) mute state."""
        ...
