"""Tests for FritzThermostatAdapter using an injected fake client."""

from __future__ import annotations

import pytest
from fritzctl.domain.models import Battery, Lock, Thermostat

from pantau.adapters.fritz_thermostat_adapter import FritzThermostatAdapter
from pantau.domain.errors import DeviceNotFoundError, DeviceUnavailableError


def _make_thermostat(name: str, ain: str, target: float = 20.0) -> Thermostat:
    return Thermostat(
        id=ain,
        name=name,
        online=True,
        battery=Battery(level=80, low=False),
        lock=Lock(locked=False),
        current_temp=18.0,
        target_temp=target,
    )


class FakeFritzClient:
    def __init__(
        self,
        devices: list[Thermostat],
        *,
        raise_on_list: Exception | None = None,
    ) -> None:
        self._devices = devices
        self._raise_on_list = raise_on_list
        self.set_temperature_calls: list[tuple[str, float]] = []

    async def list_devices(self) -> list[Thermostat]:
        if self._raise_on_list:
            raise self._raise_on_list
        return list(self._devices)

    async def set_temperature(self, device_id: str, celsius: float) -> bool:
        self.set_temperature_calls.append((device_id, celsius))
        return True


def _adapter(client: FakeFritzClient) -> FritzThermostatAdapter:
    return FritzThermostatAdapter(client=client)  # type: ignore[arg-type]


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
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.set_temperature("Wohnzimmer", 20.0)


# ---------------------------------------------------------------------------
# set_temperature
# ---------------------------------------------------------------------------


class TestSetTemperature:
    async def test_resolves_name_to_ain_and_sets(self) -> None:
        device = _make_thermostat("Wohnzimmer", "11630 0123456")
        client = FakeFritzClient([device])
        await _adapter(client).set_temperature("Wohnzimmer", 22.0)
        assert client.set_temperature_calls == [("11630 0123456", 22.0)]

    async def test_unknown_name_raises_device_not_found(self) -> None:
        client = FakeFritzClient([_make_thermostat("Wohnzimmer", "ain-1")])
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).set_temperature("Schlafzimmer", 20.0)

    async def test_empty_device_list_raises_device_not_found(self) -> None:
        client = FakeFritzClient([])
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).set_temperature("Wohnzimmer", 20.0)

    async def test_request_error_raises_unavailable(self) -> None:
        import httpx

        client = FakeFritzClient([], raise_on_list=httpx.RequestError("conn refused"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_temperature("Wohnzimmer", 20.0)


# ---------------------------------------------------------------------------
# get_temperature
# ---------------------------------------------------------------------------


class TestGetTemperature:
    async def test_returns_target_temp(self) -> None:
        device = _make_thermostat("Wohnzimmer", "ain-1", target=21.5)
        client = FakeFritzClient([device])
        temp = await _adapter(client).get_temperature("Wohnzimmer")
        assert temp == 21.5

    async def test_unknown_name_raises_device_not_found(self) -> None:
        client = FakeFritzClient([_make_thermostat("Wohnzimmer", "ain-1")])
        with pytest.raises(DeviceNotFoundError):
            await _adapter(client).get_temperature("Schlafzimmer")

    async def test_selects_correct_device_when_multiple(self) -> None:
        devices = [
            _make_thermostat("Küche", "ain-k", target=19.0),
            _make_thermostat("Wohnzimmer", "ain-w", target=22.0),
            _make_thermostat("Schlafzimmer", "ain-s", target=18.0),
        ]
        client = FakeFritzClient(devices)
        assert await _adapter(client).get_temperature("Wohnzimmer") == 22.0
        assert await _adapter(client).get_temperature("Küche") == 19.0
