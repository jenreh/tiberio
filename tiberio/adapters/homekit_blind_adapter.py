"""Real blind adapter — talks to the homekit-py daemon over its Unix socket.

The daemon owns the BLE/IP sessions to the accessories; tiberio connects to it
as a client instead of driving HomeKit in-process. This avoids two processes
fighting over the same BLE accessories and keeps per-call latency low.

Lifecycle:

* ``start()`` ensures the daemon is running (spawning it on first connect) and
  opens a **persistent** RPC connection that is held for the whole server
  lifetime.
* The daemon only idle-shuts-down when it has *zero* connected clients, so
  holding this connection open keeps it alive for as long as tiberio runs — it
  never auto-stops mid-session.
* ``stop()`` closes only tiberio's connection; it never sends a shutdown RPC, so
  the daemon is left running for other clients / a later restart.

In tests, inject a pre-built fake client via the ``client`` parameter — that
bypasses the daemon entirely.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from homekit.config import load_config
from homekit.daemon.client import DaemonRpcClient, RemoteHomeKitClient
from homekit.daemon.lifecycle import ensure_running
from homekit.exceptions import AccessoryNotFoundError, HomeKitError

from tiberio.domain.errors import DeviceCapabilityError, DeviceUnavailableError
from tiberio.domain.models import ADAPTER_HOMEKIT, Device, HomeDevice, WindowBlind
from tiberio.ports.listable_port import BackendListResult

log = logging.getLogger(__name__)

# Messages DaemonRpcClient raises when the underlying socket is gone. Used to
# tell a transport drop (reconnect + retry) apart from a real device error.
_TRANSPORT_ERRORS = ("not connected", "connection closed")


class _HomeKitClientLike(Protocol):
    """Subset of the homekit client surface this adapter relies on."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def set_position(self, entity_id: str, percent: int) -> object: ...

    async def get_state(self, entity_id: str) -> object: ...

    async def list_entities(self) -> list[object]: ...


def _as_blind(device: Device) -> WindowBlind:
    """Reject non-blind devices instead of casting blindly."""
    if not isinstance(device, WindowBlind):
        raise DeviceCapabilityError(device.id, "RangeControllable")
    return device


def _is_transport_error(exc: HomeKitError) -> bool:
    """True when the error is a dropped daemon connection, not a device fault."""
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSPORT_ERRORS)


class HomeKitBlindAdapter:
    """Implements RangeControllablePort and ListablePort via the homekit daemon."""

    adapter_name = ADAPTER_HOMEKIT

    def __init__(self, *, client: _HomeKitClientLike | None = None) -> None:
        # An injected client (tests) bypasses the daemon connection logic.
        self._injected = client is not None
        self._client: _HomeKitClientLike | None = client
        self._rpc: DaemonRpcClient | None = None

    async def start(self) -> None:
        """Connect to the daemon (spawning it if needed). Call once on startup."""
        if self._injected:
            assert self._client is not None
            await self._client.start()
            return
        await self._connect_daemon()

    async def stop(self) -> None:
        """Close our connection only — the daemon is intentionally left running."""
        if self._injected:
            assert self._client is not None
            await self._client.stop()
            return
        if self._rpc is not None:
            await self._rpc.close()
            self._rpc = None
            self._client = None
            log.info("HomeKitBlind: daemon connection closed (daemon left running)")

    # ------------------------------------------------------------------
    # Daemon connection
    # ------------------------------------------------------------------

    async def _connect_daemon(self) -> None:
        """Ensure the daemon is up and open a persistent RPC connection."""
        daemon = load_config().daemon
        reachable = await ensure_running(
            daemon.socket_path,
            auto_spawn=daemon.auto_spawn,
            log_path=daemon.log_path,
        )
        if not reachable:
            raise DeviceUnavailableError(
                f"HomeKit daemon unreachable at {daemon.socket_path}"
            )
        rpc = DaemonRpcClient(daemon.socket_path)
        await rpc.connect()
        self._rpc = rpc
        self._client = RemoteHomeKitClient(rpc)
        log.info("HomeKitBlind: connected to daemon socket=%s", daemon.socket_path)

    # ------------------------------------------------------------------
    # RangeControllablePort
    # ------------------------------------------------------------------

    async def set_range(self, device: Device, value: int) -> None:
        """Set blind position (0=closed, 100=open). Handles device.invert."""
        blind = _as_blind(device)
        actual = (100 - value) if blind.invert else value
        await self._set_position(blind.external_id, actual)
        log.info(
            "HomeKitBlind: set_range device=%s value=%d actual=%d",
            blind.id,
            value,
            actual,
        )

    async def adjust_range(self, device: Device, delta: int) -> int:
        """Adjust position by delta, returning the new Alexa-space position."""
        blind = _as_blind(device)
        homekit_pos = await self._get_position(blind.external_id)
        alexa_pos = (100 - homekit_pos) if blind.invert else homekit_pos
        new_alexa = max(0, min(100, alexa_pos + delta))
        homekit_new = (100 - new_alexa) if blind.invert else new_alexa
        await self._set_position(blind.external_id, homekit_new)
        log.info(
            "HomeKitBlind: adjust_range device=%s delta=%d -> %d",
            blind.id,
            delta,
            new_alexa,
        )
        return new_alexa

    async def get_range(self, device: Device) -> int:
        """Return the current Alexa-space position (handles device.invert)."""
        blind = _as_blind(device)
        homekit_pos = await self._get_position(blind.external_id)
        return (100 - homekit_pos) if blind.invert else homekit_pos

    # ------------------------------------------------------------------
    # ListablePort
    # ------------------------------------------------------------------

    async def list_backend(self) -> BackendListResult:
        """Return all paired HomeKit devices."""
        try:
            devices = await self._list_devices()
            return BackendListResult(
                status="ok",
                data={"devices": [d.model_dump() for d in devices]},
            )
        except DeviceUnavailableError as exc:
            log.warning("HomeKitBlind: list_backend unavailable: %s", exc)
            return BackendListResult(status="unavailable", error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call(self, method: str, *args: object) -> Any:
        """Invoke ``self._client.<method>(*args)``, reconnecting once on a drop.

        ``self._client`` is re-read after a reconnect, so the retry runs against
        the fresh connection. A second failure propagates to the caller.
        """
        try:
            return await getattr(self._client, method)(*args)
        except HomeKitError as exc:
            if self._injected or not _is_transport_error(exc):
                raise
            log.warning("HomeKitBlind: daemon connection lost (%s); reconnecting", exc)
            await self._connect_daemon()
            return await getattr(self._client, method)(*args)

    async def _set_position(self, external_id: str, percent: int) -> None:
        """Set the blind position (0 = closed, 100 = open)."""
        try:
            await self._call("set_position", external_id, percent)
            log.info(
                "HomeKitBlind: set_position entity=%s percent=%d",
                external_id,
                percent,
            )
        except AccessoryNotFoundError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        except HomeKitError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def _get_position(self, external_id: str) -> int:
        """Return the current position percentage of a blind."""
        try:
            state = await self._call("get_state", external_id)
            position = int(float(state.state))
            log.debug(
                "HomeKitBlind: get_position entity=%s -> %d",
                external_id,
                position,
            )
            return position
        except (ValueError, TypeError) as exc:
            raise DeviceUnavailableError(
                f"Unexpected state value for {external_id!r}: {exc}"
            ) from exc
        except AccessoryNotFoundError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        except HomeKitError as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def _list_devices(self) -> list[HomeDevice]:
        """Return all paired smart-home devices."""
        try:
            entities = await self._call("list_entities")
            log.debug("HomeKitBlind: list_devices count=%d", len(entities))
            return [
                HomeDevice(
                    id=e.entity_id,
                    name=e.name,
                    adapter=ADAPTER_HOMEKIT,
                    domain=e.domain,
                    room=e.room,
                )
                for e in entities
            ]
        except HomeKitError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
