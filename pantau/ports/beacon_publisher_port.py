"""BeaconPublisherPort — capability for publishing the endpoint beacon."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pantau.domain.beacon import Beacon


@runtime_checkable
class BeaconPublisherPort(Protocol):
    async def publish(self, beacon: Beacon) -> None: ...
