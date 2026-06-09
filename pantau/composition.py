"""Composition root — the only place that wires ports to adapters.

Instantiate once at application startup; inject into routers/use-cases via
FastAPI dependency injection.
"""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar, cast, runtime_checkable

from pantau.adapters.fritz_thermostat_adapter import FritzThermostatAdapter
from pantau.adapters.harmony_tv_adapter import HarmonyTvAdapter
from pantau.adapters.homekit_blind_adapter import HomeKitBlindAdapter
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.config.settings import Settings
from pantau.ports.blind_port import BlindPort
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.thermostat_port import ThermostatPort
from pantau.ports.tv_port import TvPort

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
    return (
        Container()
        .register(DeviceRegistryPort, registry)
        .register(TvPort, HarmonyTvAdapter(harmony_host))
        .register(BlindPort, HomeKitBlindAdapter())
        .register(ThermostatPort, FritzThermostatAdapter())
    )
