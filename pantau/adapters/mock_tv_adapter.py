"""Mock TV adapter — logs operations, records calls, no real hardware connection."""

from __future__ import annotations

import logging

from pantau.domain.models import HarmonyActivity, HarmonyHubDevice

log = logging.getLogger(__name__)


class MockTvAdapter:
    """Stub implementation of TvPort for development and testing."""

    def __init__(self) -> None:
        self._current_activity: str | None = None
        self.ensure_activity_calls: list[str] = []
        self.set_channel_calls: list[str] = []
        self.toggle_mute_count: int = 0
        self._activities: list[HarmonyActivity] = []
        self._devices: list[HarmonyHubDevice] = []

    async def ensure_activity(self, activity_name: str) -> None:
        log.info("MockTV: ensure_activity=%s", activity_name)
        self._current_activity = activity_name
        self.ensure_activity_calls.append(activity_name)

    async def set_channel(self, channel_number: str) -> None:
        log.info("MockTV: set_channel=%s", channel_number)
        self.set_channel_calls.append(channel_number)

    async def toggle_mute(self) -> None:
        log.info("MockTV: toggle_mute")
        self.toggle_mute_count += 1

    async def get_current_activity(self) -> str | None:
        log.info("MockTV: get_current_activity -> %s", self._current_activity)
        return self._current_activity

    async def list_activities(self) -> list[HarmonyActivity]:
        log.info("MockTV: list_activities count=%d", len(self._activities))
        return list(self._activities)

    async def list_devices(self) -> list[HarmonyHubDevice]:
        log.info("MockTV: list_devices count=%d", len(self._devices))
        return list(self._devices)
