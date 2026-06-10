"""RangeControllablePort — capability for devices with a position range (e.g. blinds)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.models import Device


@runtime_checkable
class RangeControllablePort(Protocol):
    async def set_range(self, device: Device, value: int) -> None: ...

    async def adjust_range(self, device: Device, delta: int) -> int: ...

    async def get_range(self, device: Device) -> int: ...
