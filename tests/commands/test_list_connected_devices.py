"""Tests for ListConnectedDevicesCommand."""

from __future__ import annotations

from pantau.adapters.mock_blind_adapter import MockBlindAdapter
from pantau.adapters.mock_thermostat_adapter import MockThermostatAdapter
from pantau.adapters.mock_tv_adapter import MockTvAdapter
from pantau.commands.list_connected_devices import ListConnectedDevicesCommand
from pantau.domain.errors import DeviceUnavailableError
from pantau.domain.models import (
    FritzDevice,
    HarmonyActivity,
    HarmonyHubDevice,
    HomeKitDevice,
)


def _command(
    tv: MockTvAdapter | None = None,
    blind: MockBlindAdapter | None = None,
    thermostat: MockThermostatAdapter | None = None,
) -> ListConnectedDevicesCommand:
    return ListConnectedDevicesCommand(
        tv_port=tv or MockTvAdapter(),
        blind_port=blind or MockBlindAdapter(),
        thermostat_port=thermostat or MockThermostatAdapter(),
    )


# ---------------------------------------------------------------------------
# Harmony
# ---------------------------------------------------------------------------


class TestHarmonyResult:
    async def test_returns_activities_and_devices(self) -> None:
        tv = MockTvAdapter()
        tv._activities = [HarmonyActivity(id="1", label="Watch TV")]
        tv._devices = [HarmonyHubDevice(id="10", label="Samsung TV")]

        result = await _command(tv=tv).execute()

        assert result.harmony.status == "ok"
        assert result.harmony.activities == [HarmonyActivity(id="1", label="Watch TV")]
        assert result.harmony.devices == [HarmonyHubDevice(id="10", label="Samsung TV")]
        assert result.harmony.error is None

    async def test_unavailable_when_hub_raises(self) -> None:
        class FailingTvAdapter(MockTvAdapter):
            async def list_activities(self) -> list[HarmonyActivity]:
                raise DeviceUnavailableError("hub offline")

        result = await _command(tv=FailingTvAdapter()).execute()

        assert result.harmony.status == "unavailable"
        assert "hub offline" in (result.harmony.error or "")
        assert result.harmony.activities == []

    async def test_empty_lists_when_no_devices_configured(self) -> None:
        result = await _command().execute()

        assert result.harmony.status == "ok"
        assert result.harmony.activities == []
        assert result.harmony.devices == []


# ---------------------------------------------------------------------------
# HomeKit
# ---------------------------------------------------------------------------


class TestHomeKitResult:
    async def test_returns_entities(self) -> None:
        blind = MockBlindAdapter()
        blind._devices = [
            HomeKitDevice(
                entity_id="cover.wohnzimmer",
                name="Wohnzimmer Rollo",
                domain="cover",
                room="Wohnzimmer",
            )
        ]

        result = await _command(blind=blind).execute()

        assert result.homekit.status == "ok"
        assert len(result.homekit.devices) == 1
        assert result.homekit.devices[0].entity_id == "cover.wohnzimmer"

    async def test_unavailable_when_homekit_raises(self) -> None:
        class FailingBlindAdapter(MockBlindAdapter):
            async def list_devices(self) -> list[HomeKitDevice]:
                raise DeviceUnavailableError("daemon not running")

        result = await _command(blind=FailingBlindAdapter()).execute()

        assert result.homekit.status == "unavailable"
        assert "daemon not running" in (result.homekit.error or "")
        assert result.homekit.devices == []


# ---------------------------------------------------------------------------
# FRITZ!Box
# ---------------------------------------------------------------------------


class TestFritzResult:
    async def test_returns_devices(self) -> None:
        thermostat = MockThermostatAdapter()
        thermostat._fritz_devices = [
            FritzDevice(
                id="11630 0000001",
                name="Wohnzimmer",
                online=True,
                current_temp=20.5,
                target_temp=21.0,
                battery_level=80,
                battery_low=False,
            )
        ]

        result = await _command(thermostat=thermostat).execute()

        assert result.fritz.status == "ok"
        assert len(result.fritz.devices) == 1
        assert result.fritz.devices[0].name == "Wohnzimmer"

    async def test_unavailable_when_fritz_raises(self) -> None:
        class FailingThermostatAdapter(MockThermostatAdapter):
            async def list_devices(self) -> list[FritzDevice]:
                raise DeviceUnavailableError("connection refused")

        result = await _command(thermostat=FailingThermostatAdapter()).execute()

        assert result.fritz.status == "unavailable"
        assert "connection refused" in (result.fritz.error or "")
        assert result.fritz.devices == []


# ---------------------------------------------------------------------------
# Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailure:
    async def test_one_backend_down_does_not_block_others(self) -> None:
        """HomeKit offline → other two backends still succeed."""

        class FailingBlindAdapter(MockBlindAdapter):
            async def list_devices(self) -> list[HomeKitDevice]:
                raise DeviceUnavailableError("offline")

        tv = MockTvAdapter()
        tv._activities = [HarmonyActivity(id="1", label="Watch TV")]
        thermostat = MockThermostatAdapter()
        thermostat._fritz_devices = [
            FritzDevice(
                id="1",
                name="Küche",
                online=True,
                current_temp=19.0,
                target_temp=20.0,
            )
        ]

        result = await _command(
            tv=tv, blind=FailingBlindAdapter(), thermostat=thermostat
        ).execute()

        assert result.harmony.status == "ok"
        assert result.homekit.status == "unavailable"
        assert result.fritz.status == "ok"

    async def test_all_backends_down_returns_all_unavailable(self) -> None:
        class FailingTvAdapter(MockTvAdapter):
            async def list_activities(self) -> list[HarmonyActivity]:
                raise DeviceUnavailableError("tv down")

        class FailingBlindAdapter(MockBlindAdapter):
            async def list_devices(self) -> list[HomeKitDevice]:
                raise DeviceUnavailableError("blind down")

        class FailingThermostatAdapter(MockThermostatAdapter):
            async def list_devices(self) -> list[FritzDevice]:
                raise DeviceUnavailableError("fritz down")

        result = await _command(
            tv=FailingTvAdapter(),
            blind=FailingBlindAdapter(),
            thermostat=FailingThermostatAdapter(),
        ).execute()

        assert result.harmony.status == "unavailable"
        assert result.homekit.status == "unavailable"
        assert result.fritz.status == "unavailable"
