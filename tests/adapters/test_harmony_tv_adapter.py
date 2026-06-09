"""Tests for HarmonyTvAdapter using an injected fake service factory."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from harmonyhub.exceptions import HubUnavailableError, ProtocolError
from harmonyhub.models import ActivityStatus, ChannelResult, CommandResult

from pantau.adapters.harmony_tv_adapter import HarmonyTvAdapter
from pantau.domain.errors import DeviceUnavailableError


class FakeHub:
    """In-process stand-in for HarmonyHubClient."""

    def __init__(
        self,
        *,
        current_activity_label: str | None = "PowerOff",
        channel_success: bool = True,
        mute_success: bool = True,
        raise_on_operation: Exception | None = None,
        raise_on_connect: Exception | None = None,
    ) -> None:
        self._current = ActivityStatus(
            activity_id="-1", activity_label=current_activity_label
        )
        self._channel_success = channel_success
        self._mute_success = mute_success
        self._raise_on_operation = raise_on_operation
        self._raise_on_connect = raise_on_connect
        self.connect_count = 0
        self.close_count = 0
        self.started_activities: list[str] = []
        self.set_channel_calls: list[str] = []
        self.send_key_calls: list[str] = []

    async def connect(self) -> None:
        self.connect_count += 1
        if self._raise_on_connect:
            raise self._raise_on_connect

    async def close(self) -> None:
        self.close_count += 1

    async def get_current_activity(self) -> ActivityStatus:
        if self._raise_on_operation:
            raise self._raise_on_operation
        return self._current

    async def start_activity(self, name: str) -> ActivityStatus:
        self.started_activities.append(name)
        self._current = ActivityStatus(activity_id="100", activity_label=name)
        return self._current

    async def set_channel(self, channel: str) -> ChannelResult:
        if self._raise_on_operation:
            raise self._raise_on_operation
        self.set_channel_calls.append(channel)
        return ChannelResult(
            channel=channel,
            method="digits_then_enter",
            success=self._channel_success,
            error=None if self._channel_success else "channel error",
        )

    async def send_key(self, key: str) -> CommandResult:
        if self._raise_on_operation:
            raise self._raise_on_operation
        self.send_key_calls.append(key)
        return CommandResult(
            device_id="1001",
            command=key,
            success=self._mute_success,
            error=None if self._mute_success else "send_key error",
        )


class FakeService:
    """Async context manager that wraps FakeHub as .client."""

    def __init__(self, hub: FakeHub) -> None:
        self.client = hub

    async def __aenter__(self) -> FakeService:
        await self.client.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.close()


def _make_factory(hub: FakeHub) -> Callable[[], FakeService]:
    def factory() -> FakeService:
        return FakeService(hub)

    return factory


def _adapter(hub: FakeHub) -> HarmonyTvAdapter:
    return HarmonyTvAdapter(service_factory=_make_factory(hub))


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start_is_a_noop(self) -> None:
        hub = FakeHub()
        await _adapter(hub).start()
        assert hub.connect_count == 0

    async def test_stop_is_a_noop(self) -> None:
        hub = FakeHub()
        await _adapter(hub).stop()
        assert hub.close_count == 0

    async def test_each_operation_opens_and_closes_service(self) -> None:
        hub = FakeHub()
        await _adapter(hub).get_current_activity()
        assert hub.connect_count == 1
        assert hub.close_count == 1

    async def test_connect_error_raises_device_unavailable(self) -> None:
        hub = FakeHub(raise_on_connect=HubUnavailableError("timeout"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).get_current_activity()


# ---------------------------------------------------------------------------
# ensure_activity
# ---------------------------------------------------------------------------


class TestEnsureActivity:
    async def test_starts_activity_when_different(self) -> None:
        hub = FakeHub(current_activity_label="PowerOff")
        await _adapter(hub).ensure_activity("Fernseher")
        assert hub.started_activities == ["Fernseher"]

    async def test_skips_start_when_already_active(self) -> None:
        hub = FakeHub(current_activity_label="Fernseher")
        await _adapter(hub).ensure_activity("Fernseher")
        assert hub.started_activities == []

    async def test_hub_unavailable_raises_device_unavailable(self) -> None:
        hub = FakeHub(raise_on_operation=HubUnavailableError("timeout"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).ensure_activity("Fernseher")

    async def test_protocol_error_raises_device_unavailable(self) -> None:
        hub = FakeHub(raise_on_operation=ProtocolError("ws error"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).ensure_activity("Fernseher")


# ---------------------------------------------------------------------------
# set_channel
# ---------------------------------------------------------------------------


class TestSetChannel:
    async def test_sends_channel_number(self) -> None:
        hub = FakeHub()
        await _adapter(hub).set_channel("2")
        assert hub.set_channel_calls == ["2"]

    async def test_failed_result_raises_unavailable(self) -> None:
        hub = FakeHub(channel_success=False)
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).set_channel("2")

    async def test_hub_error_raises_unavailable(self) -> None:
        hub = FakeHub(raise_on_operation=HubUnavailableError("disconnected"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).set_channel("2")


# ---------------------------------------------------------------------------
# toggle_mute
# ---------------------------------------------------------------------------


class TestToggleMute:
    async def test_sends_mute_key(self) -> None:
        hub = FakeHub()
        await _adapter(hub).toggle_mute()
        assert hub.send_key_calls == ["mute"]

    async def test_failed_result_raises_unavailable(self) -> None:
        hub = FakeHub(mute_success=False)
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).toggle_mute()


# ---------------------------------------------------------------------------
# get_current_activity
# ---------------------------------------------------------------------------


class TestGetCurrentActivity:
    async def test_returns_activity_label(self) -> None:
        hub = FakeHub(current_activity_label="Fernseher")
        label = await _adapter(hub).get_current_activity()
        assert label == "Fernseher"

    async def test_returns_none_for_power_off(self) -> None:
        hub = FakeHub(current_activity_label=None)
        label = await _adapter(hub).get_current_activity()
        assert label is None
