"""Composition root — the only place that wires ports to adapters.

Instantiate once at application startup; inject into routers/use-cases via
FastAPI dependency injection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, TypeVar, cast, runtime_checkable

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.fritz_thermostat_adapter import FritzThermostatAdapter
from pantau.adapters.harmony_tv_adapter import HarmonyTvAdapter
from pantau.adapters.homekit_blind_adapter import HomeKitBlindAdapter
from pantau.adapters.jwt_service import JwtService
from pantau.adapters.mock_blind_adapter import MockBlindAdapter
from pantau.adapters.mock_thermostat_adapter import MockThermostatAdapter
from pantau.adapters.mock_token_validator import MockTokenValidator
from pantau.adapters.mock_tv_adapter import MockTvAdapter
from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.commands.blinds.adjust_blind_position import AdjustBlindPositionCommand
from pantau.commands.blinds.set_blind_position import SetBlindPositionCommand
from pantau.commands.discover_devices import DiscoverDevicesCommand
from pantau.commands.heating.set_thermostat_temperature import (
    SetThermostatTemperatureCommand,
)
from pantau.commands.tv.activate_channel import ActivateChannelCommand
from pantau.commands.tv.set_tv_mute import SetTvMuteCommand
from pantau.config.settings import Settings
from pantau.interfaces.alexa.handlers.discovery import DiscoveryHandler
from pantau.interfaces.alexa.handlers.power import PowerHandler
from pantau.interfaces.alexa.handlers.range import RangeHandler
from pantau.interfaces.alexa.handlers.speaker import SpeakerHandler
from pantau.interfaces.alexa.handlers.thermostat import ThermostatHandler
from pantau.interfaces.alexa.router import AlexaDirectiveRouter
from pantau.ports.blind_port import BlindPort
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.thermostat_port import ThermostatPort
from pantau.ports.token_validator_port import TokenValidatorPort
from pantau.ports.tv_port import TvPort
from pantau.ports.user_store_port import UserStorePort

log = logging.getLogger(__name__)

T = TypeVar("T")


@runtime_checkable
class Lifecycle(Protocol):
    """Adapters that own a persistent connection implement this."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class Container:
    """Type-keyed adapter registry.

    Register adapters once at startup; retrieve by port type anywhere.
    Adding a new adapter requires only one `.register()` call here —
    no other class needs to change.
    """

    def __init__(self) -> None:
        self._store: dict[type, object] = {}
        self._order: list[type] = []

    def register(self, port: type[T], adapter: T) -> Container:
        """Register *adapter* under *port*. Returns self for chaining."""
        if port in self._store:
            self._order.remove(port)
        self._store[port] = adapter
        self._order.append(port)
        return self

    def get(self, port: type[T]) -> T:
        """Return the adapter registered for *port*, or raise KeyError."""
        if port not in self._store:
            raise KeyError(f"No adapter registered for {port.__name__!r}")
        return cast(T, self._store[port])

    @property
    def lifecycle_adapters(self) -> list[Lifecycle]:
        """Adapters with start/stop, in registration order."""
        return [a for t in self._order if isinstance(a := self._store[t], Lifecycle)]


def build_container(settings: Settings) -> Container:
    """Build the dependency container from settings."""
    registry = YamlDeviceRegistry(settings.devices_config_path)
    harmony_host = registry.get_registry().tv.harmony_host
    log.info("Building dependency container (real adapters, hub=%s)", harmony_host)

    jwt_service = JwtService(settings)
    user_store = SqliteUserStore(settings.users_db_path)
    auth_codes = AuthCodeStore()

    container = (
        Container()
        .register(DeviceRegistryPort, registry)  # type: ignore[type-abstract]
        .register(TvPort, HarmonyTvAdapter(harmony_host))  # type: ignore[type-abstract]
        .register(BlindPort, HomeKitBlindAdapter())  # type: ignore[type-abstract]
        .register(ThermostatPort, FritzThermostatAdapter())  # type: ignore[type-abstract]
        .register(TokenValidatorPort, jwt_service)  # type: ignore[type-abstract]
        .register(JwtService, jwt_service)
        .register(UserStorePort, user_store)  # type: ignore[type-abstract]
        .register(AuthCodeStore, auth_codes)
    )

    _wire_commands_and_router(container)
    return container


def _wire_commands_and_router(container: Container) -> None:
    """Instantiate commands as singletons and wire the Alexa directive router."""
    registry_port = container.get(DeviceRegistryPort)  # type: ignore[type-abstract]
    tv_port = container.get(TvPort)  # type: ignore[type-abstract]
    blind_port = container.get(BlindPort)  # type: ignore[type-abstract]
    thermostat_port = container.get(ThermostatPort)  # type: ignore[type-abstract]

    # Commands — singletons so SetTvMuteCommand preserves assumed mute state
    activate_channel = ActivateChannelCommand(registry_port, tv_port)
    set_mute = SetTvMuteCommand(registry_port, tv_port)
    set_temperature = SetThermostatTemperatureCommand(registry_port, thermostat_port)
    set_blind = SetBlindPositionCommand(registry_port, blind_port)
    adjust_blind = AdjustBlindPositionCommand(registry_port, blind_port)
    discover = DiscoverDevicesCommand(registry_port)

    container.register(ActivateChannelCommand, activate_channel)
    container.register(SetTvMuteCommand, set_mute)
    container.register(SetThermostatTemperatureCommand, set_temperature)
    container.register(SetBlindPositionCommand, set_blind)
    container.register(AdjustBlindPositionCommand, adjust_blind)
    container.register(DiscoverDevicesCommand, discover)

    # Handlers
    power_handler = PowerHandler(activate_channel)
    speaker_handler = SpeakerHandler(set_mute)
    thermostat_handler = ThermostatHandler(set_temperature)
    range_handler = RangeHandler(set_blind, adjust_blind)
    discovery_handler = DiscoveryHandler(discover)

    # Alexa directive router
    alexa_router = AlexaDirectiveRouter(
        power=power_handler,
        speaker=speaker_handler,
        thermostat=thermostat_handler,
        range_=range_handler,
        discovery=discovery_handler,
    )
    container.register(AlexaDirectiveRouter, alexa_router)
    log.info(
        "Alexa directive router wired with %d directives", alexa_router.directive_count
    )


def build_test_container(devices_config_path: Path) -> Container:
    """Build a container with mock adapters — for integration tests only."""
    registry = YamlDeviceRegistry(devices_config_path)
    log.debug("Building test container (mock adapters)")
    container = (
        Container()
        .register(DeviceRegistryPort, registry)  # type: ignore[type-abstract]
        .register(TvPort, MockTvAdapter())  # type: ignore[type-abstract]
        .register(BlindPort, MockBlindAdapter())  # type: ignore[type-abstract]
        .register(ThermostatPort, MockThermostatAdapter())  # type: ignore[type-abstract]
        .register(TokenValidatorPort, MockTokenValidator())  # type: ignore[type-abstract]
    )
    _wire_commands_and_router(container)
    return container


def build_oauth_test_container(
    devices_config_path: Path,
    user_store: SqliteUserStore,
    jwt_service: JwtService,
    auth_codes: AuthCodeStore,
) -> Container:
    """Container for OAuth integration tests — in-memory SQLite + real JWT service."""
    container = build_test_container(devices_config_path)
    # Override TokenValidatorPort with the real JwtService for OAuth tests
    container.register(JwtService, jwt_service)
    container.register(TokenValidatorPort, jwt_service)  # type: ignore[type-abstract]
    container.register(UserStorePort, user_store)  # type: ignore[type-abstract]
    container.register(AuthCodeStore, auth_codes)
    return container
