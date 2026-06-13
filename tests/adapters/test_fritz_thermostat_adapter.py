"""Tests for FritzThermostatAdapter using an injected fake client."""

from __future__ import annotations

from typing import cast

import pytest
from fritzctl.avm.clients import AVMClientAbstract
from fritzctl.domain.models import Battery, Lock
from fritzctl.domain.models import Thermostat as FritzThermostat

from tiberio.adapters.fritz_thermostat_adapter import FritzThermostatAdapter
from tiberio.domain.errors import DeviceNotFoundError, DeviceUnavailableError
from tiberio.domain.models import Thermostat as DomainThermostat


def _make_fritz_thermostat(
    name: str, ain: str, target: float = 20.0
) -> FritzThermostat:
    return FritzThermostat(
        id=ain,
        name=name,
        online=True,
        battery=Battery(level=80, low=False),
        lock=Lock(locked=False),
        current_temp=18.0,
        target_temp=target,
    )


def _domain_thermostat(external_id: str = "Wohnzimmer") -> DomainThermostat:
    return DomainThermostat(
        id="wohnzimmer-heizung",
        name="Heizung Wohnzimmer",
        adapter="fritz",
        external_id=external_id,
    )


class FakeFritzClient:
    def __init__(
        self,
        devices: list[FritzThermostat],
        *,
        raise_on_list: Exception | None = None,
        raise_on_set: Exception | None = None,
    ) -> None:
        self._devices = devices
        self._raise_on_list = raise_on_list
        self._raise_on_set = raise_on_set
        self.set_temperature_calls: list[tuple[str, float]] = []
        self.list_calls = 0

    async def list_devices(self) -> list[FritzThermostat]:
        self.list_calls += 1
        if self._raise_on_list:
            raise self._raise_on_list
        return list(self._devices)

    async def set_temperature(self, device_id: str, celsius: float) -> bool:
        if self._raise_on_set:
            raise self._raise_on_set
        self.set_temperature_calls.append((device_id, celsius))
        return True


def _adapter(client: FakeFritzClient) -> FritzThermostatAdapter:
    return FritzThermostatAdapter(client=cast(AVMClientAbstract, client))


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start_is_noop_when_client_injected(self) -> None:
        client = FakeFritzClient([])
        adapter = _adapter(client)
        await adapter.start()
        assert adapter._client is client  # type: ignore[attr-defined]

    async def test_stop_is_noop_when_client_injected(self) -> None:
        client = FakeFritzClient([])
        adapter = _adapter(client)
        await adapter.start()
        await adapter.stop()
        assert adapter._client is client  # type: ignore[attr-defined]

    async def test_not_started_raises_runtime_error(self) -> None:
        adapter = FritzThermostatAdapter()
        device = _domain_thermostat("Wohnzimmer")
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.set_temperature(device, 20.0)


# ---------------------------------------------------------------------------
# set_temperature (capability port)
# ---------------------------------------------------------------------------


class TestSetTemperature:
    async def test_resolves_name_to_ain_and_sets(self) -> None:
        fritz_device = _make_fritz_thermostat("Wohnzimmer", "11630 0123456")
        client = FakeFritzClient([fritz_device])
        domain_device = _domain_thermostat("Wohnzimmer")
        await _adapter(client).set_temperature(domain_device, 22.0)
        assert client.set_temperature_calls == [("11630 0123456", 22.0)]

    async def test_unknown_name_raises_device_not_found(self) -> None:
        client = FakeFritzClient([_make_fritz_thermostat("Wohnzimmer", "ain-1")])
        device = _domain_thermostat("Schlafzimmer")
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).set_temperature(device, 20.0)

    async def test_empty_device_list_raises_device_not_found(self) -> None:
        client = FakeFritzClient([])
        device = _domain_thermostat("Wohnzimmer")
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).set_temperature(device, 20.0)

    async def test_request_error_raises_unavailable(self) -> None:
        import httpx

        client = FakeFritzClient([], raise_on_list=httpx.RequestError("conn refused"))
        device = _domain_thermostat("Wohnzimmer")
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_temperature(device, 20.0)

    async def test_http_status_error_raises_unavailable(self) -> None:
        import httpx

        request = httpx.Request("GET", "http://fritz.box")
        error = httpx.HTTPStatusError(
            "503", request=request, response=httpx.Response(503, request=request)
        )
        client = FakeFritzClient([], raise_on_list=error)
        device = _domain_thermostat("Wohnzimmer")
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_temperature(device, 20.0)

    async def test_failed_set_invalidates_ain_cache(self) -> None:
        import httpx

        fritz_device = _make_fritz_thermostat("Wohnzimmer", "ain-1")
        client = FakeFritzClient(
            [fritz_device], raise_on_set=httpx.RequestError("conn reset")
        )
        adapter = _adapter(client)
        device = _domain_thermostat("Wohnzimmer")

        with pytest.raises(DeviceUnavailableError):
            await adapter.set_temperature(device, 20.0)
        assert client.list_calls == 1

        # AIN must be re-resolved after the failure (cache invalidated)
        client._raise_on_set = None
        await adapter.set_temperature(device, 21.0)
        assert client.list_calls == 2
        assert client.set_temperature_calls == [("ain-1", 21.0)]


# ---------------------------------------------------------------------------
# get_temperature (capability port)
# ---------------------------------------------------------------------------


class TestGetTemperature:
    async def test_returns_target_temp(self) -> None:
        fritz_device = _make_fritz_thermostat("Wohnzimmer", "ain-1", target=21.5)
        client = FakeFritzClient([fritz_device])
        domain_device = _domain_thermostat("Wohnzimmer")
        temp = await _adapter(client).get_temperature(domain_device)
        assert temp == 21.5

    async def test_unknown_name_raises_device_not_found(self) -> None:
        client = FakeFritzClient([_make_fritz_thermostat("Wohnzimmer", "ain-1")])
        device = _domain_thermostat("Schlafzimmer")
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).get_temperature(device)

    async def test_selects_correct_device_when_multiple(self) -> None:
        fritz_devices = [
            _make_fritz_thermostat("Küche", "ain-k", target=19.0),
            _make_fritz_thermostat("Wohnzimmer", "ain-w", target=22.0),
            _make_fritz_thermostat("Schlafzimmer", "ain-s", target=18.0),
        ]
        client = FakeFritzClient(fritz_devices)
        assert (
            await _adapter(client).get_temperature(_domain_thermostat("Wohnzimmer"))
            == 22.0
        )
        assert (
            await _adapter(client).get_temperature(_domain_thermostat("Küche")) == 19.0
        )


class TestGetCurrentTemperature:
    async def test_returns_current_temp(self) -> None:
        # _make_fritz_thermostat fixes current_temp at 18.0°C.
        client = FakeFritzClient([_make_fritz_thermostat("Wohnzimmer", "ain-1")])
        temp = await _adapter(client).get_current_temperature(
            _domain_thermostat("Wohnzimmer")
        )
        assert temp == 18.0

    async def test_unknown_name_raises_device_not_found(self) -> None:
        client = FakeFritzClient([_make_fritz_thermostat("Wohnzimmer", "ain-1")])
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).get_current_temperature(
                _domain_thermostat("Schlafzimmer")
            )

    async def test_setpoint_and_current_share_one_fetch(self) -> None:
        client = FakeFritzClient(
            [_make_fritz_thermostat("Wohnzimmer", "ain-1", target=21.5)]
        )
        adapter = _adapter(client)
        device = _domain_thermostat("Wohnzimmer")

        setpoint = await adapter.get_temperature(device)
        current = await adapter.get_current_temperature(device)

        assert (setpoint, current) == (21.5, 18.0)
        # A single ReportState reads both via one coalesced FRITZ!Box round-trip.
        assert client.list_calls == 1


class TestDeviceListCoalescing:
    async def test_concurrent_reads_share_one_fetch(self) -> None:
        import asyncio

        devices = [
            _make_fritz_thermostat("Wohnzimmer", "ain-w", target=22.0),
            _make_fritz_thermostat("Bad", "ain-b", target=21.0),
        ]
        client = FakeFritzClient(devices)
        adapter = _adapter(client)

        results = await asyncio.gather(
            adapter.get_temperature(_domain_thermostat("Wohnzimmer")),
            adapter.get_temperature(_domain_thermostat("Bad")),
            adapter.get_temperature(_domain_thermostat("Wohnzimmer")),
        )

        assert results == [22.0, 21.0, 22.0]
        # The burst collapses into a single FRITZ!Box round-trip.
        assert client.list_calls == 1

    async def test_set_temperature_invalidates_read_cache(self) -> None:
        device = _make_fritz_thermostat("Wohnzimmer", "ain-w", target=20.0)
        client = FakeFritzClient([device])
        adapter = _adapter(client)
        domain_device = _domain_thermostat("Wohnzimmer")

        await adapter.get_temperature(domain_device)
        assert client.list_calls == 1

        # AIN already cached from the read, so the write itself needs no fetch.
        await adapter.set_temperature(domain_device, 23.0)
        assert client.list_calls == 1

        # A read after a write must re-fetch instead of serving stale state.
        await adapter.get_temperature(domain_device)
        assert client.list_calls == 2


class TestCapabilityGuard:
    async def test_non_thermostat_device_raises_capability_error(self) -> None:
        from tiberio.domain.errors import DeviceCapabilityError
        from tiberio.domain.models import TvAudio

        client = FakeFritzClient([])
        audio = TvAudio(id="tv-audio", name="Fernseher", adapter="harmony")
        with pytest.raises(DeviceCapabilityError):
            await _adapter(client).set_temperature(audio, 20.0)
