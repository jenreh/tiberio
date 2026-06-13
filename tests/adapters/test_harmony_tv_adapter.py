"""Tests for HarmonyTvAdapter using an injected fake service factory."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from harmonyhub.exceptions import HubUnavailableError, ProtocolError
from harmonyhub.models import ActivityStatus, ChannelResult, CommandResult

from tiberio.adapters.harmony_tv_adapter import HarmonyTvAdapter
from tiberio.domain.errors import DeviceUnavailableError
from tiberio.domain.models import Device, TvAudio, TvChannel


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
        self.power_off_calls = 0

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

    async def power_off(self) -> ActivityStatus:
        if self._raise_on_operation:
            raise self._raise_on_operation
        self.power_off_calls += 1
        self._current = ActivityStatus(activity_id="-1", activity_label="PowerOff")
        return self._current


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
        hub = FakeHub(current_activity_label="Fernseher")
        await _adapter(hub).ensure_activity("Fernseher")
        assert hub.connect_count == 1
        assert hub.close_count == 1

    async def test_connect_error_raises_device_unavailable(self) -> None:
        hub = FakeHub(raise_on_connect=HubUnavailableError("timeout"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).ensure_activity("Fernseher")


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
# turn_on (PowerablePort)
# ---------------------------------------------------------------------------


def _channel(channel_number: str = "2", watch_activity: str = "Fernseher") -> TvChannel:
    return TvChannel(
        id="zdf",
        name="ZDF",
        adapter="harmony",
        channel_number=channel_number,
        watch_activity=watch_activity,
    )


def _audio(watch_activity: str = "Fernsehen") -> TvAudio:
    return TvAudio(
        id="tv-audio",
        name="Fernseher",
        adapter="harmony",
        watch_activity=watch_activity,
    )


class TestTurnOn:
    async def test_turn_on_channel_ensures_activity_and_sets_channel(self) -> None:
        hub = FakeHub(current_activity_label="PowerOff")
        await _adapter(hub).turn_on(_channel())
        assert hub.started_activities == ["Fernseher"]
        assert hub.set_channel_calls == ["2"]

    async def test_turn_on_channel_skips_activity_if_already_active(self) -> None:
        hub = FakeHub(current_activity_label="Fernseher")
        await _adapter(hub).turn_on(_channel())
        assert hub.started_activities == []
        assert hub.set_channel_calls == ["2"]

    async def test_turn_on_audio_starts_watch_activity(self) -> None:
        hub = FakeHub(current_activity_label="PowerOff")
        await _adapter(hub).turn_on(_audio())
        assert hub.started_activities == ["Fernsehen"]
        assert hub.set_channel_calls == []

    async def test_turn_on_audio_skips_activity_if_already_active(self) -> None:
        hub = FakeHub(current_activity_label="Fernsehen")
        await _adapter(hub).turn_on(_audio())
        assert hub.started_activities == []
        assert hub.set_channel_calls == []

    async def test_turn_on_unknown_device_is_noop(self) -> None:
        hub = FakeHub()
        device = Device(id="x", name="X", adapter="harmony")
        await _adapter(hub).turn_on(device)
        assert hub.started_activities == []
        assert hub.set_channel_calls == []
        assert hub.send_key_calls == []


class TestTurnOff:
    async def test_turn_off_powers_off_current_activity(self) -> None:
        hub = FakeHub(current_activity_label="Fernseher")
        await _adapter(hub).turn_off(_channel())
        assert hub.power_off_calls == 1

    async def test_turn_off_hub_error_raises_unavailable(self) -> None:
        hub = FakeHub(raise_on_operation=HubUnavailableError("down"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).turn_off(_channel())


# ---------------------------------------------------------------------------
# set_mute (MuteControllablePort)
# ---------------------------------------------------------------------------


class TestSetMute:
    async def test_mute_true_sends_toggle_when_unmuted(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_mute(_audio(), muted=True)
        assert hub.send_key_calls == ["mute"]

    async def test_mute_true_skips_toggle_when_already_muted(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_mute(_audio(), muted=True)
        hub.send_key_calls.clear()
        await adapter.set_mute(_audio(), muted=True)
        assert hub.send_key_calls == []

    async def test_mute_false_sends_toggle_when_muted(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_mute(_audio(), muted=True)  # → now muted
        hub.send_key_calls.clear()
        await adapter.set_mute(_audio(), muted=False)  # → unmute
        assert hub.send_key_calls == ["mute"]

    async def test_mute_false_skips_toggle_when_already_unmuted(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_mute(_audio(), muted=False)
        assert hub.send_key_calls == []

    async def test_mute_state_persists_across_calls(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_mute(_audio(), muted=True)
        await adapter.set_mute(_audio(), muted=False)
        await adapter.set_mute(_audio(), muted=True)
        assert len(hub.send_key_calls) == 3


# ---------------------------------------------------------------------------
# adjust_volume / set_volume (VolumeControllablePort)
# ---------------------------------------------------------------------------


class TestAdjustVolume:
    async def test_positive_delta_sends_volume_up_keys(self) -> None:
        hub = FakeHub()
        await _adapter(hub).adjust_volume(_audio(), 3)
        assert hub.send_key_calls == ["volume_up", "volume_up", "volume_up"]

    async def test_negative_delta_sends_volume_down_keys(self) -> None:
        hub = FakeHub()
        await _adapter(hub).adjust_volume(_audio(), -2)
        assert hub.send_key_calls == ["volume_down", "volume_down"]

    async def test_zero_delta_sends_no_keys(self) -> None:
        hub = FakeHub()
        await _adapter(hub).adjust_volume(_audio(), 0)
        assert hub.send_key_calls == []

    async def test_returns_new_assumed_volume(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        result = await adapter.adjust_volume(_audio(), 10)
        assert result == 60  # default 50 + 10

    async def test_clamps_at_100(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        result = await adapter.adjust_volume(_audio(), 100)
        assert result == 100

    async def test_clamps_at_0(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        result = await adapter.adjust_volume(_audio(), -100)
        assert result == 0

    async def test_assumed_volume_persists(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.adjust_volume(_audio(), 10)  # assumed = 60
        result = await adapter.adjust_volume(_audio(), 5)  # assumed = 65
        assert result == 65

    async def test_hub_error_raises_unavailable(self) -> None:
        hub = FakeHub(raise_on_operation=HubUnavailableError("disconnected"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).adjust_volume(_audio(), 1)

    async def test_ambiguous_routing_raises_unavailable(self) -> None:
        from harmonyhub.exceptions import AmbiguousRoutingError

        hub = FakeHub(
            raise_on_operation=AmbiguousRoutingError(
                key="volume_up", candidates=["TV", "AVR"]
            )
        )
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).adjust_volume(_audio(), 1)

    async def test_command_not_found_raises_unavailable(self) -> None:
        from harmonyhub.exceptions import CommandNotFoundError

        hub = FakeHub(
            raise_on_operation=CommandNotFoundError("volume_up", "Sonos Beam")
        )
        with pytest.raises(DeviceUnavailableError):
            await _adapter(hub).adjust_volume(_audio(), 1)


class TestSetVolume:
    async def test_set_volume_above_assumed_sends_up_keys(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)  # assumed = 50
        await adapter.set_volume(_audio(), 53)
        assert hub.send_key_calls == ["volume_up", "volume_up", "volume_up"]

    async def test_set_volume_below_assumed_sends_down_keys(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)  # assumed = 50
        await adapter.set_volume(_audio(), 48)
        assert hub.send_key_calls == ["volume_down", "volume_down"]

    async def test_set_volume_same_as_assumed_sends_no_keys(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)  # assumed = 50
        await adapter.set_volume(_audio(), 50)
        assert hub.send_key_calls == []

    async def test_assumed_volume_updated_after_set(self) -> None:
        hub = FakeHub()
        adapter = _adapter(hub)
        await adapter.set_volume(_audio(), 70)
        result = await adapter.adjust_volume(_audio(), 0)
        assert result == 70


# ---------------------------------------------------------------------------
# concurrency — assumed state must be lock-protected
# ---------------------------------------------------------------------------


class SlowFakeHub(FakeHub):
    """send_key yields control so concurrent directives interleave."""

    async def send_key(self, key: str) -> CommandResult:
        import asyncio

        await asyncio.sleep(0.01)
        return await super().send_key(key)


class TestConcurrentState:
    async def test_concurrent_set_mute_sends_single_toggle(self) -> None:
        import asyncio

        hub = SlowFakeHub()
        adapter = _adapter(hub)
        await asyncio.gather(
            adapter.set_mute(_audio(), True),
            adapter.set_mute(_audio(), True),
        )
        assert hub.send_key_calls == ["mute"]

    async def test_concurrent_adjust_volume_accumulates(self) -> None:
        import asyncio

        hub = SlowFakeHub()
        adapter = _adapter(hub)
        await asyncio.gather(
            adapter.adjust_volume(_audio(), 2),
            adapter.adjust_volume(_audio(), 3),
        )
        assert await adapter.get_volume(_audio()) == 55
