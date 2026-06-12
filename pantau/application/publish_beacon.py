"""PublishBeaconUseCase — announce the current public base URL via the beacon port."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from pantau.domain.beacon import Beacon
from pantau.ports.beacon_publisher_port import BeaconPublisherPort

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PublishBeaconUseCase:
    """Build a Beacon from the configured public base URL and publish it."""

    def __init__(
        self,
        publisher: BeaconPublisherPort,
        base_url: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._publisher = publisher
        self._base_url = base_url
        self._clock = clock

    async def execute(self) -> Beacon:
        beacon = Beacon(base_url=self._base_url, updated_at=self._clock().isoformat())
        await self._publisher.publish(beacon)
        log.info("Beacon published: base_url=%s", beacon.base_url)
        return beacon
