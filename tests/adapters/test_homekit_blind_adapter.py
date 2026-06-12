"""Tests for HomeKitBlindAdapter using an injected fake client."""

from __future__ import annotations

from typing import cast

import pytest
from homekit.client import HomeKitClient
from homekit.exceptions import AccessoryNotFoundError, HomeKitError

from tiberio.adapters.homekit_blind_adapter import HomeKitBlindAdapter
from tiberio.domain.errors import DeviceUnavailableError
from tiberio.domain.models import WindowBlind


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
    return HomeKitBlindAdapter(client=cast(HomeKitClient, client))


def _blind(external_id: str = "cover.kueche", invert: bool = False) -> WindowBlind:
    return WindowBlind(
        id="kueche-rollo",
        name="Rollo Küche",
        adapter="homekit",
        external_id=external_id,
        invert=invert,
    )


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
# set_range (capability port)
# ---------------------------------------------------------------------------


class TestSetRange:
    async def test_delegates_to_client_with_external_id(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_range(_blind(), 50)
        assert client.set_position_calls == [("cover.kueche", 50)]

    async def test_closed_position(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_range(_blind(), 0)
        assert client.set_position_calls == [("cover.kueche", 0)]

    async def test_open_position(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_range(_blind(), 100)
        assert client.set_position_calls == [("cover.kueche", 100)]

    async def test_invert_flips_position(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_range(_blind(invert=True), 30)
        assert client.set_position_calls == [("cover.kueche", 70)]

    async def test_invert_half_stays_half(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client).set_range(_blind(invert=True), 50)
        assert client.set_position_calls == [("cover.kueche", 50)]

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(
            raise_on_set=AccessoryNotFoundError("cover.kueche not found")
        )
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_range(_blind(), 50)

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_set=HomeKitError("connection failed"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).set_range(_blind(), 50)


# ---------------------------------------------------------------------------
# adjust_range (capability port)
# ---------------------------------------------------------------------------


class TestAdjustRange:
    async def test_increases_position(self) -> None:
        client = FakeHomeKitClient(position=40)
        new_pos = await _adapter(client).adjust_range(_blind(), 20)
        assert new_pos == 60
        assert client.set_position_calls == [("cover.kueche", 60)]

    async def test_decreases_position(self) -> None:
        client = FakeHomeKitClient(position=60)
        new_pos = await _adapter(client).adjust_range(_blind(), -20)
        assert new_pos == 40

    async def test_clamps_at_100(self) -> None:
        client = FakeHomeKitClient(position=90)
        new_pos = await _adapter(client).adjust_range(_blind(), 20)
        assert new_pos == 100

    async def test_clamps_at_0(self) -> None:
        client = FakeHomeKitClient(position=5)
        new_pos = await _adapter(client).adjust_range(_blind(), -20)
        assert new_pos == 0

    async def test_invert_adjust_position(self) -> None:
        # HomeKit stores 30, which maps to Alexa 70 (inverted).
        # Delta +10 → Alexa 80 → HomeKit 20.
        client = FakeHomeKitClient(position=30)
        new_pos = await _adapter(client).adjust_range(_blind(invert=True), 10)
        assert new_pos == 80
        assert client.set_position_calls[-1] == ("cover.kueche", 20)


# ---------------------------------------------------------------------------
# get_range (capability port)
# ---------------------------------------------------------------------------


class TestGetRange:
    async def test_returns_parsed_position(self) -> None:
        client = FakeHomeKitClient(position=75)
        pos = await _adapter(client).get_range(_blind())
        assert pos == 75

    async def test_returns_zero_for_closed(self) -> None:
        client = FakeHomeKitClient(position=0)
        assert await _adapter(client).get_range(_blind()) == 0

    async def test_invert_maps_homekit_to_alexa(self) -> None:
        client = FakeHomeKitClient(position=30)
        pos = await _adapter(client).get_range(_blind(invert=True))
        assert pos == 70

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=AccessoryNotFoundError("cover missing"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).get_range(_blind())

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=HomeKitError("ble error"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client).get_range(_blind())


# ---------------------------------------------------------------------------
# Internal helpers — tests to protect existing behaviour
# ---------------------------------------------------------------------------


class TestSetPositionInternal:
    async def test_delegates_to_client(self) -> None:
        client = FakeHomeKitClient()
        await _adapter(client)._set_position("cover.kueche", 50)
        assert client.set_position_calls == [("cover.kueche", 50)]

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(
            raise_on_set=AccessoryNotFoundError("cover.kueche not found")
        )
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client)._set_position("cover.kueche", 50)

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_set=HomeKitError("connection failed"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client)._set_position("cover.kueche", 50)


class TestGetPositionInternal:
    async def test_returns_parsed_position(self) -> None:
        client = FakeHomeKitClient(position=75)
        pos = await _adapter(client)._get_position("cover.kueche")
        assert pos == 75

    async def test_returns_zero_for_closed(self) -> None:
        client = FakeHomeKitClient(position=0)
        assert await _adapter(client)._get_position("cover.kueche") == 0

    async def test_returns_hundred_for_open(self) -> None:
        client = FakeHomeKitClient(position=100)
        assert await _adapter(client)._get_position("cover.kueche") == 100

    async def test_accessory_not_found_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=AccessoryNotFoundError("cover missing"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client)._get_position("cover.kueche")

    async def test_homekit_error_raises_unavailable(self) -> None:
        client = FakeHomeKitClient(raise_on_get=HomeKitError("ble error"))
        with pytest.raises(DeviceUnavailableError):
            await _adapter(client)._get_position("cover.kueche")


class TestCapabilityGuard:
    async def test_non_blind_device_raises_capability_error(self) -> None:
        from tiberio.domain.errors import DeviceCapabilityError
        from tiberio.domain.models import TvAudio

        adapter = HomeKitBlindAdapter(client=cast(HomeKitClient, FakeHomeKitClient()))
        audio = TvAudio(id="tv-audio", name="Fernseher", adapter="harmony")
        with pytest.raises(DeviceCapabilityError):
            await adapter.set_range(audio, 50)


# ---------------------------------------------------------------------------
# Daemon-backed lifecycle (no injected client)
# ---------------------------------------------------------------------------


class _FakeDaemonConfig:
    socket_path = "test-homekit.sock"
    auto_spawn = True
    log_path = "test-homekit.log"


class _FakeConfig:
    daemon = _FakeDaemonConfig()


class _FakeRpc:
    """Stand-in for DaemonRpcClient: tracks connect/close, never shuts down."""

    def __init__(self, socket_path: object) -> None:
        self.socket_path = socket_path
        self.connect_count = 0
        self.close_count = 0
        self.shutdown_called = False

    async def connect(self) -> None:
        self.connect_count += 1

    async def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def daemon_patches(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Patch the homekit daemon collaborators imported into the adapter module."""
    import tiberio.adapters.homekit_blind_adapter as mod

    created: dict[str, object] = {"rpcs": [], "ensure_calls": []}

    async def fake_ensure_running(socket_path, *, auto_spawn, log_path):  # type: ignore[no-untyped-def]
        created["ensure_calls"].append((socket_path, auto_spawn, log_path))
        return True

    def fake_rpc_factory(socket_path):  # type: ignore[no-untyped-def]
        rpc = _FakeRpc(socket_path)
        created["rpcs"].append(rpc)
        return rpc

    def fake_load_config() -> _FakeConfig:
        return _FakeConfig()

    def fake_remote_client(rpc: object) -> FakeHomeKitClient:
        return FakeHomeKitClient()

    monkeypatch.setattr(mod, "load_config", fake_load_config)
    monkeypatch.setattr(mod, "ensure_running", fake_ensure_running)
    monkeypatch.setattr(mod, "DaemonRpcClient", fake_rpc_factory)
    monkeypatch.setattr(mod, "RemoteHomeKitClient", fake_remote_client)
    return created


class TestDaemonLifecycle:
    async def test_start_spawns_and_connects(
        self, daemon_patches: dict[str, object]
    ) -> None:
        adapter = HomeKitBlindAdapter()
        await adapter.start()
        rpcs = cast(list[_FakeRpc], daemon_patches["rpcs"])
        assert len(rpcs) == 1
        assert rpcs[0].connect_count == 1
        assert daemon_patches["ensure_calls"] == [
            ("test-homekit.sock", True, "test-homekit.log")
        ]

    async def test_stop_closes_connection_without_shutting_daemon_down(
        self, daemon_patches: dict[str, object]
    ) -> None:
        adapter = HomeKitBlindAdapter()
        await adapter.start()
        await adapter.stop()
        rpcs = cast(list[_FakeRpc], daemon_patches["rpcs"])
        # Connection closed, but the daemon was never asked to shut down.
        assert rpcs[0].close_count == 1
        assert rpcs[0].shutdown_called is False

    async def test_unreachable_daemon_raises_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, daemon_patches: dict[str, object]
    ) -> None:
        import tiberio.adapters.homekit_blind_adapter as mod

        async def unreachable(socket_path, *, auto_spawn, log_path):  # type: ignore[no-untyped-def]
            return False

        monkeypatch.setattr(mod, "ensure_running", unreachable)
        with pytest.raises(DeviceUnavailableError):
            await HomeKitBlindAdapter().start()

    async def test_set_position_reconnects_after_transport_drop(
        self, monkeypatch: pytest.MonkeyPatch, daemon_patches: dict[str, object]
    ) -> None:
        import tiberio.adapters.homekit_blind_adapter as mod

        # First client fails with a transport error; second one succeeds.
        good = FakeHomeKitClient()
        clients = iter(
            [
                FakeHomeKitClient(
                    raise_on_set=HomeKitError("Daemon connection closed")
                ),
                good,
            ]
        )
        monkeypatch.setattr(mod, "RemoteHomeKitClient", lambda rpc: next(clients))

        adapter = HomeKitBlindAdapter()
        await adapter.start()
        await adapter.set_range(_blind(), 40)

        assert good.set_position_calls == [("cover.kueche", 40)]
        # Reconnected: a second RPC connection was opened.
        rpcs = cast(list[_FakeRpc], daemon_patches["rpcs"])
        assert len(rpcs) == 2
