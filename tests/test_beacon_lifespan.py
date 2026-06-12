"""Lifespan beacon wiring — startup publish, periodic task, clean shutdown."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pantau.adapters.mock_beacon_publisher import MockBeaconPublisher
from pantau.api.app import _beacon_loop, create_app
from pantau.application.publish_beacon import BeaconPublisher
from pantau.composition import build_test_container
from pantau.config.settings import Settings
from pantau.domain.beacon import Beacon

DEVICES_YAML = """
tv:
  watch_activity: "TV"
  audio:
    id: "tv-audio"
    friendly_name: "Fernseher"
  channels: []
blinds: []
thermostats: []
"""


class FailingBeaconPublisher:
    async def publish(self, beacon: Beacon) -> None:
        raise RuntimeError("s3 unreachable")


@pytest.fixture
def devices_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "devices.yaml"
    cfg.write_text(DEVICES_YAML, encoding="utf-8")
    return cfg


def test_beacon_enabled_publishes_once_at_startup(devices_config: Path) -> None:
    container = build_test_container(devices_config)
    publisher = MockBeaconPublisher()
    container.register(
        BeaconPublisher,
        BeaconPublisher(publisher, base_url="https://tunnel.example.com"),
    )
    settings = Settings(
        dev_mode=True,
        beacon_enabled=True,
        public_base_url="https://tunnel.example.com",
    )

    app = create_app(settings=settings, container=container)
    with TestClient(app):
        assert len(publisher.published) == 1
        assert publisher.published[0].base_url == "https://tunnel.example.com"


def test_beacon_disabled_by_default_publishes_nothing(devices_config: Path) -> None:
    container = build_test_container(devices_config)
    publisher = MockBeaconPublisher()
    container.register(BeaconPublisher, BeaconPublisher(publisher, base_url="x"))

    app = create_app(settings=Settings(dev_mode=True), container=container)
    with TestClient(app):
        assert publisher.published == []


def test_beacon_publish_failure_does_not_crash_startup(
    devices_config: Path, caplog: pytest.LogCaptureFixture
) -> None:
    container = build_test_container(devices_config)
    container.register(
        BeaconPublisher,
        BeaconPublisher(FailingBeaconPublisher(), base_url="x"),
    )
    settings = Settings(
        dev_mode=True,
        beacon_enabled=True,
        public_base_url="https://tunnel.example.com",
    )

    app = create_app(settings=settings, container=container)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert any("Beacon publish failed" in r.message for r in caplog.records)


async def test_beacon_loop_publishes_periodically_and_cancels_cleanly() -> None:
    publisher = MockBeaconPublisher()
    use_case = BeaconPublisher(publisher, base_url="https://t.example")

    task = asyncio.create_task(_beacon_loop(use_case, interval_seconds=0))
    while len(publisher.published) < 2:  # noqa: ASYNC110
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(publisher.published) >= 2


async def test_beacon_loop_keeps_running_after_publish_failure() -> None:
    publisher = MockBeaconPublisher()
    fail_once = FailingBeaconPublisher()

    class FlakyPublisher:
        def __init__(self) -> None:
            self.calls = 0

        async def publish(self, beacon: Beacon) -> None:
            self.calls += 1
            if self.calls == 1:
                await fail_once.publish(beacon)
            await publisher.publish(beacon)

    flaky = FlakyPublisher()
    use_case = BeaconPublisher(flaky, base_url="https://t.example")

    task = asyncio.create_task(_beacon_loop(use_case, interval_seconds=0))
    while flaky.calls < 2:  # noqa: ASYNC110
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert flaky.calls >= 2
    assert len(publisher.published) >= 1
