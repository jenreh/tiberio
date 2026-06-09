"""Command: list live devices from all connected backends."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from pantau.domain.errors import DeviceUnavailableError
from pantau.domain.models import (
    FritzDevice,
    HarmonyActivity,
    HarmonyHubDevice,
    HomeKitDevice,
)
from pantau.ports.blind_port import BlindPort
from pantau.ports.thermostat_port import ThermostatPort
from pantau.ports.tv_port import TvPort

log = logging.getLogger(__name__)

BackendStatus = Literal["ok", "unavailable"]


@dataclass
class HarmonyResult:
    status: BackendStatus
    activities: list[HarmonyActivity] = field(default_factory=list)
    devices: list[HarmonyHubDevice] = field(default_factory=list)
    error: str | None = None


@dataclass
class HomeKitResult:
    status: BackendStatus
    devices: list[HomeKitDevice] = field(default_factory=list)
    error: str | None = None


@dataclass
class FritzResult:
    status: BackendStatus
    devices: list[FritzDevice] = field(default_factory=list)
    error: str | None = None


@dataclass
class ConnectedDevicesResult:
    harmony: HarmonyResult
    homekit: HomeKitResult
    fritz: FritzResult


class ListConnectedDevicesCommand:
    """Query all three backends for live connected devices.

    Each backend is queried independently. If one is offline its result carries
    ``status="unavailable"`` and an error message; the other backends are
    unaffected.
    """

    def __init__(
        self,
        tv_port: TvPort,
        blind_port: BlindPort,
        thermostat_port: ThermostatPort,
    ) -> None:
        self._tv = tv_port
        self._blind = blind_port
        self._thermostat = thermostat_port

    async def execute(self) -> ConnectedDevicesResult:
        return ConnectedDevicesResult(
            harmony=await self._query_harmony(),
            homekit=await self._query_homekit(),
            fritz=await self._query_fritz(),
        )

    async def _query_harmony(self) -> HarmonyResult:
        try:
            activities = await self._tv.list_activities()
            devices = await self._tv.list_devices()
            log.info(
                "ListConnectedDevices: harmony activities=%d devices=%d",
                len(activities),
                len(devices),
            )
            return HarmonyResult(status="ok", activities=activities, devices=devices)
        except DeviceUnavailableError as exc:
            log.warning("ListConnectedDevices: harmony unavailable: %s", exc)
            return HarmonyResult(status="unavailable", error=str(exc))

    async def _query_homekit(self) -> HomeKitResult:
        try:
            devices = await self._blind.list_devices()
            log.info("ListConnectedDevices: homekit devices=%d", len(devices))
            return HomeKitResult(status="ok", devices=devices)
        except DeviceUnavailableError as exc:
            log.warning("ListConnectedDevices: homekit unavailable: %s", exc)
            return HomeKitResult(status="unavailable", error=str(exc))

    async def _query_fritz(self) -> FritzResult:
        try:
            devices = await self._thermostat.list_devices()
            log.info("ListConnectedDevices: fritz devices=%d", len(devices))
            return FritzResult(status="ok", devices=devices)
        except DeviceUnavailableError as exc:
            log.warning("ListConnectedDevices: fritz unavailable: %s", exc)
            return FritzResult(status="unavailable", error=str(exc))
