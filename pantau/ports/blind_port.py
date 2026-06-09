"""Port: roller blind / window covering control."""

from __future__ import annotations

from typing import Protocol

from pantau.domain.models import HomeKitDevice


class BlindPort(Protocol):
    """Abstracts the HomeKit blind library (homekit-py)."""

    async def set_position(self, homekit_entity_id: str, percent: int) -> None:
        """Set the position of a blind (0 = closed, 100 = open)."""
        ...

    async def get_position(self, homekit_entity_id: str) -> int:
        """Return the current position percentage of a blind."""
        ...

    async def list_devices(self) -> list[HomeKitDevice]:
        """Return all paired HomeKit devices (equivalent to `homekit entities`)."""
        ...
