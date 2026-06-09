"""Real blind adapter — wraps homekit-py (HomeKitClient) with a persistent daemon."""

from __future__ import annotations

import logging

from homekit.client import HomeKitClient
from homekit.exceptions import AccessoryNotFoundError, HomeKitError

from pantau.domain.errors import DeviceUnavailableError

log = logging.getLogger(__name__)


class HomeKitBlindAdapter:
    """Implements BlindPort against HomeKit accessories via homekit-py.

    Holds a single persistent HomeKitClient whose daemon is started once on
    server startup and stopped on server shutdown (call start()/stop() from the
    FastAPI lifespan). This avoids per-call BLE/IP connection overhead.

    In tests, inject a pre-built fake client via the ``client`` parameter.
    """

    def __init__(self, *, client: HomeKitClient | None = None) -> None:
        self._client = client or HomeKitClient()

    async def start(self) -> None:
        """Start the HomeKit daemon. Call once when the server starts."""
        await self._client.start()
        log.info("HomeKitBlind: daemon started")

    async def stop(self) -> None:
        """Stop the HomeKit daemon. Call once when the server shuts down."""
        await self._client.stop()
        log.info("HomeKitBlind: daemon stopped")

    async def set_position(self, homekit_entity_id: str, percent: int) -> None:
        """Set the blind position (0 = closed, 100 = open)."""
        try:
            await self._client.set_position(homekit_entity_id, percent)
            log.info(
                "HomeKitBlind: set_position entity=%s percent=%d",
                homekit_entity_id,
                percent,
            )
        except AccessoryNotFoundError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        except HomeKitError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def get_position(self, homekit_entity_id: str) -> int:
        """Return the current position percentage of a blind."""
        try:
            state = await self._client.get_state(homekit_entity_id)
            position = int(float(state.state))
            log.debug(
                "HomeKitBlind: get_position entity=%s -> %d",
                homekit_entity_id,
                position,
            )
            return position
        except (ValueError, TypeError) as exc:
            raise DeviceUnavailableError(
                f"Unexpected state value for {homekit_entity_id!r}: {exc}"
            ) from exc
        except AccessoryNotFoundError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        except HomeKitError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
