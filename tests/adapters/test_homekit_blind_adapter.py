"""Tests for HomeKitBlindAdapter using an injected fake client."""

from __future__ import annotations

import pytest
from homekit.exceptions import AccessoryNotFoundError, HomeKitError

from pantau.adapters.homekit_blind_adapter import HomeKitBlindAdapter
from pantau.domain.errors import DeviceUnavailableError


class FakeEntityState:
    def __init__(self, state: str) -> None:
        self.state = state


class FakeHomeKitClient:
    def __init__(
        self,
        *,
        position: int = 50,
        raise_on_set: Exception | None = None,
        raise_on_get: Exception | None = None,
    ) -> None:
        self._position = position
        self._raise_on_set = raise_on_set
        self._raise_on_get = raise_on_get
        self.set_position_calls: list[tuple[str, int]] = []
        self.start_count = 0
        self.stop_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    async def set_position(self, entity_id: str, percent: int) -> None:
        if self._raise_on_set:
            raise self._raise_on_set
        self.set_position_calls.append((entity_id, percent))

    async def get_state(self, entity_id: str) -> FakeEntityState:
        if self._raise_on_get:
            raise self._raise_on_get
        return FakeEntityState(state=str(self._position))


def _adapter(client: FakeHomeKitClient) -> HomeKitBlindAdapter:
    return HomeKitBlindAdapter(client=client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start_delegates_to_client(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).start()
        assert client.start_count == 1

    async def test_stop_delegates_to_client(self) -> None:
        client = FakeHomeKitClient()
        adapter = _adapter(client)
        await adapter.start()
        await adapter.stop()
        assert client.stop_count == 1


# ---------------------------------------------------------------------------
# set_position
# ---------------------------------------------------------------------------


class TestSetPosition:
    async def test_delegates_to_client(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_position("cover.kueche", 50)
        assert client.set_position_calls == [("cover.kueche", 50)]

    async def test_closed_position(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_position("cover.kueche", 0)
        assert client.set_position_calls == [("cover.kueche", 0)]

    async def test_open_position(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_position("cover.kueche", 100)
        assert client.set_position_calls == [("cover.kueche", 100)]

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(
            raise_on_set=AccessoryNotFoundError("cover.kueche not found")
        )
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_position("cover.kueche", 50)

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_set=HomeKitError("connection failed"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_position("cover.kueche", 50)


# ---------------------------------------------------------------------------
# get_position
# ---------------------------------------------------------------------------


class TestGetPosition:
    async def test_returns_parsed_position(self) -> None:
        client = FakeHomeKitClient(position=75)
        pos = await _adapter(client).get_position("cover.kueche")
        assert pos == 75

    async def test_returns_zero_for_closed(self) -> None:
        client = FakeHomeKitClient(position=0)
        assert await _adapter(client).get_position("cover.kueche") == 0

    async def test_returns_hundred_for_open(self) -> None:
        client = FakeHomeKitClient(position=100)
        assert await _adapter(client).get_position("cover.kueche") == 100

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=AccessoryNotFoundError("cover missing"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).get_position("cover.kueche")

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=HomeKitError("ble error"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).get_position("cover.kueche")
