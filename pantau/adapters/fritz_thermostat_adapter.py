"""Real thermostat adapter — wraps fritzctl-py (AVM clients) with a persistent session."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from fritzctl.avm.clients import AVMClientAbstract, get_avm_client

from pantau.domain.errors import DeviceNotFoundError, DeviceUnavailableError
from pantau.domain.models import FritzDevice

if TYPE_CHECKING:
    from fritzctl.domain.models import Thermostat

log = logging.getLogger(__name__)


class FritzThermostatAdapter:
    """Implements ThermostatPort against a FRITZ!Box via fritzctl-py.

    Holds a persistent httpx session and AVM client. Call start()/stop() from
    the FastAPI lifespan to initialise/close the session once per server lifetime.

    In tests, inject a pre-built fake client via the ``client`` parameter; that
    skips httpx setup so start()/stop() are no-ops.
    """

    def __init__(self, *, client: AVMClientAbstract | None = None) -> None:
        self._injected = client
        self._http: httpx.AsyncClient | None = None
        self._client: AVMClientAbstract | None = client

    async def start(self) -> None:
        """Open the httpx session and auto-detect the AVM API. Call once on startup."""
        if self._injected is None:
            self._http = httpx.AsyncClient()
            self._client = await get_avm_client(self._http)
        log.info("FritzThermostat: client initialised")

    async def stop(self) -> None:
        """Close the httpx session. Call once on server shutdown."""
        if self._injected is None and self._http is not None:
            await self._http.aclose()
            self._http = None
            self._client = None
        log.info("FritzThermostat: client closed")

    def _get_client(self) -> AVMClientAbstract:
        if self._client is None:
            raise RuntimeError(
                "FritzThermostatAdapter is not started; call start() first"
            )
        return self._client

    async def set_temperature(self, fritz_name: str, celsius: float) -> None:
        """Resolve fritz_name → AIN, then set the target temperature."""
        try:
            client = self._get_client()
            device = await self._resolve(client, fritz_name)
            await client.set_temperature(device.id, celsius)
            log.info(
                "FritzThermostat: set_temperature name=%s ain=%s celsius=%.1f",
                fritz_name,
                device.id,
                celsius,
            )
        except DeviceNotFoundError:
            raise
        except (httpx.RequestError, TimeoutError, PermissionError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def get_temperature(self, fritz_name: str) -> float:
        """Return the current target temperature for the named device."""
        try:
            client = self._get_client()
            device = await self._resolve(client, fritz_name)
            log.debug(
                "FritzThermostat: get_temperature name=%s ain=%s -> %.1f",
                fritz_name,
                device.id,
                device.target_temp,
            )
            return device.target_temp
        except DeviceNotFoundError:
            raise
        except (httpx.RequestError, TimeoutError, PermissionError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def list_devices(self) -> list[FritzDevice]:
        """Return all FRITZ!Box smart-home devices (equivalent to `fritzctl list`)."""
        try:
            client = self._get_client()
            raw = await client.list_devices()
            log.debug("FritzThermostat: list_devices count=%d", len(raw))
            return [
                FritzDevice(
                    id=d.id,
                    name=d.name,
                    online=d.online,
                    current_temp=d.current_temp,
                    target_temp=d.target_temp,
                    battery_level=d.battery.level if d.battery else None,
                    battery_low=d.battery.low if d.battery else False,
                )
                for d in raw
            ]
        except (httpx.RequestError, TimeoutError, PermissionError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc

    async def _resolve(self, client: AVMClientAbstract, fritz_name: str) -> Thermostat:
        devices = await client.list_devices()
        device = next((d for d in devices if d.name == fritz_name), None)
        if device is None:
            raise DeviceNotFoundError(fritz_name)
        return device
