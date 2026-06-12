"""PublishBeaconUseCase — builds a Beacon and hands it to the publisher port."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pantau.adapters.mock_beacon_publisher import MockBeaconPublisher
from pantau.application.publish_beacon import PublishBeaconUseCase
from pantau.domain.beacon import Beacon

_FIXED_NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return _FIXED_NOW


async def test_execute_publishes_beacon_with_base_url_and_clock() -> None:
    publisher = MockBeaconPublisher()
    use_case = PublishBeaconUseCase(
        publisher, base_url="https://tunnel.example.com", clock=_fixed_clock
    )

    beacon = await use_case.execute()

    assert publisher.published == [beacon]
    assert beacon.base_url == "https://tunnel.example.com"
    assert beacon.updated_at == "2026-06-11T12:00:00+00:00"
    assert beacon.health == "ok"


async def test_execute_default_clock_produces_iso8601_utc() -> None:
    publisher = MockBeaconPublisher()
    use_case = PublishBeaconUseCase(publisher, base_url="https://x.example")

    beacon = await use_case.execute()

    parsed = datetime.fromisoformat(beacon.updated_at)
    assert parsed.tzinfo is not None


def test_beacon_is_frozen() -> None:
    beacon = Beacon(
        base_url="https://x.example", updated_at="2026-06-11T12:00:00+00:00"
    )
    with pytest.raises(Exception, match="frozen"):
        beacon.base_url = "https://other.example"  # type: ignore[misc]
