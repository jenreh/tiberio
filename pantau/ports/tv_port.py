"""Port: TV / Harmony Hub control."""

from __future__ import annotations

from typing import Protocol

from pantau.domain.models import HarmonyActivity, HarmonyHubDevice


class TvPort(Protocol):
    """Abstracts the Harmony Hub library (harmonyhub-py)."""

    async def ensure_activity(self, activity_name: str) -> None:
        """Start the given Harmony activity if it is not already active."""
        ...

    async def set_channel(self, channel_number: str) -> None:
        """Switch to the given channel number."""
        ...

    async def toggle_mute(self) -> None:
        """Send the mute toggle command (IR-only, no discrete on/off)."""
        ...

    async def get_current_activity(self) -> str | None:
        """Return the label of the currently active Harmony activity, or None."""
        ...

    async def list_activities(self) -> list[HarmonyActivity]:
        """Return all configured Harmony Hub activities (equivalent to `harmony config`)."""
        ...

    async def list_devices(self) -> list[HarmonyHubDevice]:
        """Return all physical devices registered on the Harmony Hub."""
        ...
