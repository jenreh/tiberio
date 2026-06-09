"""Real TV adapter — wraps harmonyhub-py HarmonyService with a per-operation connection."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from harmonyhub.exceptions import HubUnavailableError, ProtocolError
from harmonyhub.service import HarmonyService

from pantau.domain.errors import DeviceUnavailableError
from pantau.domain.models import HarmonyActivity, HarmonyHubDevice

log = logging.getLogger(__name__)


class HarmonyTvAdapter:
    """Implements TvPort using a short-lived HarmonyService connection per operation.

    Each public method opens ``async with HarmonyService() as service:`` to
    fetch hub config and perform work, then disconnects.  No persistent WebSocket
    is kept alive between calls.  The hub host is read from
    ``~/.config/harmony-local/config.toml`` (or the ``HARMONY_HUB_HOST`` env var)
    — not from ``devices.yaml``.

    Trade-off: every Alexa command incurs an HTTP provision fetch + WebSocket
    connect + disconnect (typically 1-3 s on a LAN Harmony Hub).  If that latency
    is unacceptable, switch back to ``connection_mode="persistent"`` and drive
    ``connect()``/``close()`` from ``start()``/``stop()``.

    In tests, pass ``service_factory`` — a zero-argument callable that returns an
    async context manager exposing a ``.client`` attribute.
    """

    def __init__(
        self,
        *,
        service_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._service_factory: Callable[[], Any] = service_factory or HarmonyService

    async def start(self) -> None:
        """No-op — connections are opened per operation."""

    async def stop(self) -> None:
        """No-op — connections are closed after each operation."""

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
        except (HubUnavailableError, ProtocolError) as exc:
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
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def toggle_mute(self) -> None:
        """Send the mute toggle IR command."""
        try:
            async with self._service_factory() as service:
                result = await service.client.send_key("mute")
                if not result.success:
                    raise DeviceUnavailableError(result.error or "toggle_mute failed")
                log.info("HarmonyTV: toggle_mute sent")
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def get_current_activity(self) -> str | None:
        """Return the label of the currently active Harmony activity, or None."""
        try:
            async with self._service_factory() as service:
                status = await service.client.get_current_activity()
                return status.activity_label
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def list_activities(self) -> list[HarmonyActivity]:
        """Return all configured Harmony Hub activities (equivalent to `harmony config`)."""
        try:
            async with self._service_factory() as service:
                activities = await service.client.list_activities()
                log.debug("HarmonyTV: list_activities count=%d", len(activities))
                return [
                    HarmonyActivity(
                        id=a.id,
                        label=a.label,
                        is_power_off=a.is_power_off,
                    )
                    for a in activities
                ]
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def list_devices(self) -> list[HarmonyHubDevice]:
        """Return all physical devices registered on the Harmony Hub."""
        try:
            async with self._service_factory() as service:
                devices = await service.client.list_devices()
                log.debug("HarmonyTV: list_devices count=%d", len(devices))
                return [
                    HarmonyHubDevice(
                        id=d.id,
                        label=d.label,
                        manufacturer=d.manufacturer,
                        model=d.model,
                    )
                    for d in devices
                ]
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
