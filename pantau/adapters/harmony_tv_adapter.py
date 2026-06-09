"""Real TV adapter — wraps harmonyhub-py (HarmonyHubClient) with a persistent connection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from harmonyhub.client import HarmonyHubClient
from harmonyhub.exceptions import HubUnavailableError, ProtocolError

from pantau.domain.errors import DeviceUnavailableError

if TYPE_CHECKING:
    from harmonyhub.models import ActivityStatus

log = logging.getLogger(__name__)


class HarmonyTvAdapter:
    """Implements TvPort against a Logitech Harmony Hub via harmonyhub-py.

    Holds a single persistent HarmonyHubClient. Call start()/stop() from the
    FastAPI lifespan to connect/disconnect the WebSocket once per server lifetime.

    In tests, inject a pre-built fake hub via the ``hub`` parameter.
    """

    def __init__(self, host: str, *, hub: HarmonyHubClient | None = None) -> None:
        self._hub = hub or HarmonyHubClient(host, connection_mode="persistent")

    async def start(self) -> None:
        """Connect the Harmony Hub WebSocket. Call once on server startup."""
        await self._hub.connect()
        log.info("HarmonyTV: connected to hub")

    async def stop(self) -> None:
        """Close the Harmony Hub WebSocket. Call once on server shutdown."""
        await self._hub.close()
        log.info("HarmonyTV: disconnected from hub")

    async def ensure_activity(self, activity_name: str) -> None:
        """Start the given Harmony activity only if it is not already active."""
        try:
            status: ActivityStatus = await self._hub.get_current_activity()
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
            await self._hub.start_activity(activity_name)
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def set_channel(self, channel_number: str) -> None:
        """Switch to the given channel number."""
        try:
            result = await self._hub.set_channel(channel_number)
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
            result = await self._hub.send_key("mute")
            if not result.success:
                raise DeviceUnavailableError(result.error or "toggle_mute failed")
            log.info("HarmonyTV: toggle_mute sent")
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def get_current_activity(self) -> str | None:
        """Return the label of the currently active Harmony activity, or None."""
        try:
            status = await self._hub.get_current_activity()
            return status.activity_label
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
