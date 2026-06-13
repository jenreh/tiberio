"""Real TV adapter — wraps harmonyhub-py HarmonyService with a per-operation connection."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from harmonyhub.exceptions import HarmonyHubError
from harmonyhub.service import HarmonyService

from tiberio.domain.errors import DeviceUnavailableError
from tiberio.domain.models import (
    ADAPTER_HARMONY,
    Activity,
    Device,
    HubDevice,
    TvAudio,
    TvChannel,
)
from tiberio.domain.values import MuteState
from tiberio.ports.listable_port import BackendListResult

log = logging.getLogger(__name__)


class HarmonyTvAdapter:
    """Implements PowerablePort, MuteControllablePort, and ListablePort via Harmony Hub.

    Each public method opens ``async with HarmonyService() as service:`` to
    fetch hub config and perform work, then disconnects.  No persistent WebSocket
    is kept alive between calls.

    Mute state is tracked internally as assumed state (toggle-only IR remote).
    The adapter must be wired as a singleton so assumed state persists across calls.

    In tests, pass ``service_factory`` — a zero-argument callable that returns an
    async context manager exposing a ``.client`` attribute.
    """

    adapter_name = ADAPTER_HARMONY

    _INITIAL_VOLUME = 50

    def __init__(
        self,
        *,
        service_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._service_factory: Callable[[], Any] = service_factory or HarmonyService
        self._assumed_mute_state: MuteState = MuteState.UNMUTED
        self._assumed_volume: int = self._INITIAL_VOLUME
        # Serialises read-modify-write of assumed state under concurrent directives
        self._state_lock = asyncio.Lock()

    async def start(self) -> None:
        """No-op — connections are opened per operation."""

    async def stop(self) -> None:
        """No-op — connections are closed after each operation."""

    # ------------------------------------------------------------------
    # PowerablePort
    # ------------------------------------------------------------------

    async def turn_on(self, device: Device) -> None:
        """Power on a device.

        For a TvChannel, start the watch activity and tune the channel. For the
        TvAudio endpoint, start the watch activity (turns the TV on).
        """
        if isinstance(device, TvChannel):
            await self.ensure_activity(device.watch_activity)
            await self.set_channel(device.channel_number)
        elif isinstance(device, TvAudio):
            await self.ensure_activity(device.watch_activity)
        else:
            log.info(
                "HarmonyTV: turn_on no-op for device=%s type=%s",
                device.id,
                type(device).__name__,
            )

    async def turn_off(self, device: Device) -> None:
        """Power off by ending the current Harmony activity."""
        try:
            async with self._service_factory() as service:
                await service.client.power_off()
            log.info("HarmonyTV: power_off for device=%s", device.id)
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    # ------------------------------------------------------------------
    # MuteControllablePort
    # ------------------------------------------------------------------

    async def set_mute(self, device: Device, muted: bool) -> None:
        """Set the mute state, toggling only when the assumed state differs."""
        desired = MuteState.MUTED if muted else MuteState.UNMUTED
        async with self._state_lock:
            if desired == self._assumed_mute_state:
                log.debug(
                    "HarmonyTV: mute already %s, skipping toggle for device=%s",
                    desired.value,
                    device.id,
                )
                return
            await self.toggle_mute()
            self._assumed_mute_state = desired
        log.info(
            "HarmonyTV: mute state for device=%s is now %s", device.id, desired.value
        )

    async def get_mute(self, device: Device) -> bool:
        """Return the current assumed mute state."""
        log.debug(
            "HarmonyTV: get_mute device=%s assumed=%s",
            device.id,
            self._assumed_mute_state.value,
        )
        return self._assumed_mute_state == MuteState.MUTED

    # ------------------------------------------------------------------
    # VolumeControllablePort
    # ------------------------------------------------------------------

    async def set_volume(self, device: Device, level: int) -> None:
        """Set volume to an absolute level by sending IR key presses from assumed state."""
        async with self._state_lock:
            delta = level - self._assumed_volume
            if delta != 0:
                await self._send_volume_keys(delta)
                self._assumed_volume = max(0, min(100, self._assumed_volume + delta))
        log.info(
            "HarmonyTV: set_volume device=%s level=%d assumed=%d",
            device.id,
            level,
            self._assumed_volume,
        )

    async def adjust_volume(self, device: Device, delta: int) -> int:
        """Adjust volume by *delta* IR key presses; returns the new assumed level."""
        async with self._state_lock:
            if delta != 0:
                await self._send_volume_keys(delta)
            self._assumed_volume = max(0, min(100, self._assumed_volume + delta))
        log.info(
            "HarmonyTV: adjust_volume device=%s delta=%d assumed=%d",
            device.id,
            delta,
            self._assumed_volume,
        )
        return self._assumed_volume

    async def get_volume(self, device: Device) -> int:
        """Return the current assumed volume level."""
        log.debug(
            "HarmonyTV: get_volume device=%s assumed=%d",
            device.id,
            self._assumed_volume,
        )
        return self._assumed_volume

    # ------------------------------------------------------------------
    # ListablePort
    # ------------------------------------------------------------------

    async def list_backend(self) -> BackendListResult:
        """Return all activities and hub devices from the Harmony Hub."""
        try:
            activities = await self.list_activities()
            devices = await self.list_devices()
            log.info(
                "HarmonyTV: list_backend activities=%d devices=%d",
                len(activities),
                len(devices),
            )
            return BackendListResult(
                status="ok",
                data={
                    "activities": [a.model_dump() for a in activities],
                    "devices": [d.model_dump() for d in devices],
                },
            )
        except DeviceUnavailableError as exc:
            log.warning("HarmonyTV: list_backend unavailable: %s", exc)
            return BackendListResult(status="unavailable", error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers (formerly TvPort methods)
    # ------------------------------------------------------------------

    async def ensure_activity(self, activity_name: str) -> None:
        """Start the given Harmony activity only if it is not already active."""
        try:
            async with self._service_factory() as service:
                status = await service.client.get_current_activity()
                if status.activity_label == activity_name:
                    log.debug(
                        "HarmonyTV: activity=%s already active, skipping", activity_name
                    )
                    return
                log.info(
                    "HarmonyTV: starting activity=%s (was=%s)",
                    activity_name,
                    status.activity_label,
                )
                await service.client.start_activity(activity_name)
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def set_channel(self, channel_number: str) -> None:
        """Switch to the given channel number."""
        try:
            async with self._service_factory() as service:
                result = await service.client.set_channel(channel_number)
                if not result.success:
                    raise DeviceUnavailableError(
                        result.error or f"set_channel({channel_number!r}) failed"
                    )
                log.info("HarmonyTV: set_channel=%s", channel_number)
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def _send_volume_keys(self, delta: int) -> None:
        """Send *|delta|* VolumeUp or VolumeDown IR key presses in a single connection."""
        key = "volume_up" if delta > 0 else "volume_down"
        count = abs(delta)
        try:
            async with self._service_factory() as service:
                for _ in range(count):
                    result = await service.client.send_key(key)
                    if not result.success:
                        raise DeviceUnavailableError(result.error or f"{key} failed")
            log.debug("HarmonyTV: sent %s x%d", key, count)
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def toggle_mute(self) -> None:
        """Send the mute toggle IR command."""
        try:
            async with self._service_factory() as service:
                result = await service.client.send_key("mute")
                if not result.success:
                    raise DeviceUnavailableError(result.error or "toggle_mute failed")
                log.info("HarmonyTV: toggle_mute sent")
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def list_activities(self) -> list[Activity]:
        """Return all configured Harmony Hub activities."""
        try:
            async with self._service_factory() as service:
                activities = await service.client.list_activities()
                log.debug("HarmonyTV: list_activities count=%d", len(activities))
                return [
                    Activity(
                        id=a.id,
                        name=a.label,
                        adapter=ADAPTER_HARMONY,
                        is_power_off=a.is_power_off,
                    )
                    for a in activities
                ]
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def list_devices(self) -> list[HubDevice]:
        """Return all physical devices registered on the Harmony Hub."""
        try:
            async with self._service_factory() as service:
                devices = await service.client.list_devices()
                log.debug("HarmonyTV: list_devices count=%d", len(devices))
                return [
                    HubDevice(
                        id=d.id,
                        name=d.label,
                        adapter=ADAPTER_HARMONY,
                        manufacturer=d.manufacturer,
                        model=d.model,
                    )
                    for d in devices
                ]
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
