"""Mock beacon publisher — records published beacons, no AWS access."""

from __future__ import annotations

import logging

from pantau.domain.beacon import Beacon

log = logging.getLogger(__name__)


class MockBeaconPublisher:
    """Stub implementation of BeaconPublisherPort for tests and local dev."""

    def __init__(self) -> None:
        self.published: list[Beacon] = []

    async def publish(self, beacon: Beacon) -> None:
        log.debug("MockBeacon: publish base_url=%s", beacon.base_url)
        self.published.append(beacon)
