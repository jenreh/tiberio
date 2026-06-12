"""Composition root — the only place that wires ports to adapters.

Instantiate once at application startup; inject into routers/use-cases via
FastAPI dependency injection.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, TypeVar, cast, runtime_checkable

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.fritz_thermostat_adapter import FritzThermostatAdapter
from pantau.adapters.harmony_tv_adapter import HarmonyTvAdapter
from pantau.adapters.homekit_blind_adapter import HomeKitBlindAdapter
from pantau.adapters.jwt_service import JwtService
from pantau.adapters.mock_beacon_publisher import MockBeaconPublisher
from pantau.adapters.mock_blind_adapter import MockBlindAdapter
from pantau.adapters.mock_thermostat_adapter import MockThermostatAdapter
from pantau.adapters.mock_token_validator import MockTokenValidator
from pantau.adapters.mock_tv_adapter import MockTvAdapter
from pantau.adapters.password_hasher import BcryptPasswordHasher
from pantau.adapters.s3_beacon_publisher import S3BeaconPublisher
from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.application.publish_beacon import PublishBeaconUseCase
from pantau.commands.adjust_range import AdjustRangeCommand
from pantau.commands.adjust_temperature import AdjustTemperatureCommand
from pantau.commands.adjust_volume import AdjustVolumeCommand
from pantau.commands.discover_devices import DiscoverDevicesCommand
from pantau.commands.get_speaker_state import GetSpeakerStateCommand
from pantau.commands.list_connected_devices import ListConnectedDevicesCommand
from pantau.commands.set_mute import SetMuteCommand
from pantau.commands.set_range import SetRangeCommand
from pantau.commands.set_temperature import SetTemperatureCommand
from pantau.commands.set_volume import SetVolumeCommand
from pantau.commands.turn_off import TurnOffCommand
from pantau.commands.turn_on import TurnOnCommand
from pantau.config.settings import Settings
from pantau.domain.errors import DeviceCapabilityError, DeviceUnavailableError
from pantau.domain.models import ADAPTER_FRITZ, ADAPTER_HARMONY, ADAPTER_HOMEKIT, Device
from pantau.interfaces.alexa.handlers.discovery import DiscoveryHandler
from pantau.interfaces.alexa.handlers.power import PowerHandler
from pantau.interfaces.alexa.handlers.range import RangeHandler
from pantau.interfaces.alexa.handlers.speaker import SpeakerHandler
from pantau.interfaces.alexa.handlers.thermostat import ThermostatHandler
from pantau.interfaces.alexa.router import AlexaDirectiveRouter
from pantau.ports.auth_code_store_port import AuthCodeStorePort
from pantau.ports.beacon_publisher_port import BeaconPublisherPort
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.password_hasher_port import PasswordHasherPort
from pantau.ports.token_issuer_port import TokenIssuerPort
from pantau.ports.token_validator_port import TokenValidatorPort
from pantau.ports.user_store_port import UserStorePort

log = logging.getLogger(__name__)

T = TypeVar("T")


@runtime_checkable
class Lifecycle(Protocol):
    """Adapters that own a persistent connection implement this."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class Container:
    """Type-keyed adapter registry with device-centric capability resolution.

    Register adapters once at startup; retrieve by port type anywhere.
    Adding a new adapter requires only one `.register()` call here —
    no other class needs to change.
    """

    def __init__(self) -> None:
        self._store: dict[type, object] = {}
        self._order: list[type] = []
        self._by_adapter: dict[str, object] = {}  # adapter_name → instance

    def register(
        self, port: type[T], adapter: T, *, adapter_name: str | None = None
    ) -> Container:
        """Register *adapter* under *port*. Returns self for chaining.

        Pass *adapter_name* (e.g. ``"harmony"``) to also make the adapter
        retrievable via :meth:`resolve`.
        """
        if port in self._store:
            self._order.remove(port)
        self._store[port] = adapter
        self._order.append(port)
        if adapter_name is not None:
            self._by_adapter[adapter_name] = adapter
        return self

    def get(self, port: type[T]) -> T:
        """Return the adapter registered for *port*, or raise KeyError."""
        if port not in self._store:
            raise KeyError(f"No adapter registered for {port.__name__!r}")
        return cast(T, self._store[port])

    def resolve(self, device: Device, capability: type[T]) -> T:
        """Return the adapter for *device.adapter* that implements *capability*.

        Raises DeviceUnavailableError if no adapter is registered for the
        adapter name, or DeviceCapabilityError if the adapter does not
        implement the capability — so handlers map them to proper Alexa
        error types instead of INTERNAL_ERROR.
        """
        adapter_name = device.adapter
        if adapter_name not in self._by_adapter:
            raise DeviceUnavailableError(f"No adapter registered for {adapter_name!r}")
        adapter = self._by_adapter[adapter_name]
        if not isinstance(adapter, capability):  # type: ignore[arg-type]
            raise DeviceCapabilityError(device.id, capability.__name__)
        return adapter  # type: ignore[return-value]

    def all_implementing(self, capability: type[T]) -> list[T]:
        """Return all distinct registered adapters that implement *capability*."""
        return self._unique_instances(self._by_adapter.values(), capability)

    @property
    def lifecycle_adapters(self) -> list[Lifecycle]:
        """Adapters with start/stop, in registration order, deduped by instance."""
        return self._unique_instances((self._store[t] for t in self._order), Lifecycle)

    def _unique_instances(
        self, source: Iterable[object], capability: type[T]
    ) -> list[T]:
        seen: set[int] = set()
        result: list[T] = []
        for obj in source:
            if id(obj) not in seen and isinstance(obj, capability):  # type: ignore[arg-type]
                seen.add(id(obj))
                result.append(obj)  # type: ignore[arg-type]
        return result


def build_container(settings: Settings) -> Container:
    """Build the dependency container from settings."""
    registry = YamlDeviceRegistry(settings.devices_config_path)
    log.info("Building dependency container (real adapters)")

    harmony = HarmonyTvAdapter()
    homekit = HomeKitBlindAdapter()
    fritz = FritzThermostatAdapter()
    jwt_service = JwtService(
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )
    user_store = SqliteUserStore(settings.users_db_path)
    auth_codes = AuthCodeStore()
    beacon_publisher = _build_beacon_publisher(settings)
    publish_beacon = PublishBeaconUseCase(beacon_publisher, settings.public_base_url)

    container = (
        Container()
        .register(DeviceRegistryPort, registry)  # type: ignore[type-abstract]
        .register(HarmonyTvAdapter, harmony, adapter_name=ADAPTER_HARMONY)
        .register(HomeKitBlindAdapter, homekit, adapter_name=ADAPTER_HOMEKIT)
        .register(FritzThermostatAdapter, fritz, adapter_name=ADAPTER_FRITZ)
        .register(TokenValidatorPort, jwt_service)  # type: ignore[type-abstract]
        .register(TokenIssuerPort, jwt_service)  # type: ignore[type-abstract]
        .register(UserStorePort, user_store)  # type: ignore[type-abstract]
        .register(AuthCodeStorePort, auth_codes)  # type: ignore[type-abstract]
        .register(PasswordHasherPort, BcryptPasswordHasher())  # type: ignore[type-abstract]
        .register(BeaconPublisherPort, beacon_publisher)  # type: ignore[type-abstract]
        .register(PublishBeaconUseCase, publish_beacon)
    )

    _wire_commands_and_router(container)
    return container


def _build_beacon_publisher(settings: Settings) -> BeaconPublisherPort:
    """Select the beacon publisher adapter from settings.

    ``beacon_enabled`` is the single active/inactive predicate; the app
    startup validation guarantees ``public_base_url`` is set when enabled.
    """
    if settings.beacon_enabled:
        log.info(
            "Beacon publisher: S3 (bucket=%s, key=%s)",
            settings.s3_beacon_bucket,
            settings.s3_beacon_key,
        )
        return S3BeaconPublisher(
            bucket=settings.s3_beacon_bucket,
            key=settings.s3_beacon_key,
            region=settings.aws_region,
        )
    log.debug("Beacon publisher: mock (beacon disabled)")
    return MockBeaconPublisher()


def _wire_commands_and_router(container: Container) -> None:
    """Instantiate commands as singletons and wire the Alexa directive router."""
    registry_port = container.get(DeviceRegistryPort)  # type: ignore[type-abstract]

    # Container satisfies CapabilityResolverPort structurally but mypy cannot verify
    # generic Protocol conformance at call sites — suppress until PEP 673 / mypy #4717.
    turn_on = TurnOnCommand(registry_port, container)  # type: ignore[arg-type]
    turn_off = TurnOffCommand(registry_port, container)  # type: ignore[arg-type]
    set_mute = SetMuteCommand(registry_port, container)  # type: ignore[arg-type]
    set_volume = SetVolumeCommand(registry_port, container)  # type: ignore[arg-type]
    adjust_volume = AdjustVolumeCommand(registry_port, container)  # type: ignore[arg-type]
    get_speaker_state = GetSpeakerStateCommand(registry_port, container)  # type: ignore[arg-type]
    set_range = SetRangeCommand(registry_port, container)  # type: ignore[arg-type]
    adjust_range = AdjustRangeCommand(registry_port, container)  # type: ignore[arg-type]
    set_temperature = SetTemperatureCommand(registry_port, container)  # type: ignore[arg-type]
    adjust_temperature = AdjustTemperatureCommand(
        registry_port,
        container,  # type: ignore[arg-type]
        set_temperature,
    )
    discover = DiscoverDevicesCommand(registry_port)
    list_connected = ListConnectedDevicesCommand(container)  # type: ignore[arg-type]

    container.register(TurnOnCommand, turn_on)
    container.register(TurnOffCommand, turn_off)
    container.register(SetMuteCommand, set_mute)
    container.register(SetVolumeCommand, set_volume)
    container.register(AdjustVolumeCommand, adjust_volume)
    container.register(GetSpeakerStateCommand, get_speaker_state)
    container.register(SetRangeCommand, set_range)
    container.register(AdjustRangeCommand, adjust_range)
    container.register(SetTemperatureCommand, set_temperature)
    container.register(AdjustTemperatureCommand, adjust_temperature)
    container.register(DiscoverDevicesCommand, discover)
    container.register(ListConnectedDevicesCommand, list_connected)

    power_handler = PowerHandler(turn_on, turn_off)
    speaker_handler = SpeakerHandler(
        set_mute, set_volume, adjust_volume, get_speaker_state
    )
    thermostat_handler = ThermostatHandler(set_temperature, adjust_temperature)
    range_handler = RangeHandler(set_range, adjust_range)
    discovery_handler = DiscoveryHandler(discover)

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

    mock_tv = MockTvAdapter()
    mock_blind = MockBlindAdapter()
    mock_thermostat = MockThermostatAdapter()
    mock_beacon = MockBeaconPublisher()

    container = (
        Container()
        .register(DeviceRegistryPort, registry)  # type: ignore[type-abstract]
        .register(MockTvAdapter, mock_tv, adapter_name=ADAPTER_HARMONY)
        .register(MockBlindAdapter, mock_blind, adapter_name=ADAPTER_HOMEKIT)
        .register(MockThermostatAdapter, mock_thermostat, adapter_name=ADAPTER_FRITZ)
        .register(TokenValidatorPort, MockTokenValidator())  # type: ignore[type-abstract]
        .register(BeaconPublisherPort, mock_beacon)  # type: ignore[type-abstract]
        .register(PublishBeaconUseCase, PublishBeaconUseCase(mock_beacon, ""))
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
    container.register(TokenValidatorPort, jwt_service)  # type: ignore[type-abstract]
    container.register(TokenIssuerPort, jwt_service)  # type: ignore[type-abstract]
    container.register(UserStorePort, user_store)  # type: ignore[type-abstract]
    container.register(AuthCodeStorePort, auth_codes)  # type: ignore[type-abstract]
    container.register(PasswordHasherPort, BcryptPasswordHasher())  # type: ignore[type-abstract]
    return container
