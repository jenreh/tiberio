"""YAML device registry adapter — loads devices.yaml and resolves endpoint IDs."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from pantau.domain.models import (
    BlindDevice,
    ChannelDevice,
    DeviceRegistry,
    ThermostatDevice,
    TvAudioDevice,
    TvConfig,
)

log = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "devices.yaml"


class YamlDeviceRegistry:
    """Loads DeviceRegistry from a YAML file and implements DeviceRegistryPort."""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG) -> None:
        self._registry = _load(config_path)
        log.info(
            "DeviceRegistry loaded: %d channels, %d blinds, %d thermostats",
            len(self._registry.tv.channels),
            len(self._registry.blinds),
            len(self._registry.thermostats),
        )

    def get_registry(self) -> DeviceRegistry:
        return self._registry

    def find_channel(self, endpoint_id: str) -> ChannelDevice | None:
        return next(
            (c for c in self._registry.tv.channels if c.id == endpoint_id), None
        )

    def find_blind(self, endpoint_id: str) -> BlindDevice | None:
        return next((b for b in self._registry.blinds if b.id == endpoint_id), None)

    def find_thermostat(self, endpoint_id: str) -> ThermostatDevice | None:
        return next(
            (t for t in self._registry.thermostats if t.id == endpoint_id), None
        )


def _load(path: Path) -> DeviceRegistry:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    tv_raw = raw["tv"]
    audio = TvAudioDevice(
        id=tv_raw["audio"]["id"],
        friendly_name=tv_raw["audio"]["friendly_name"],
    )
    channels = tuple(
        ChannelDevice(
            id=ch["id"],
            friendly_name=ch["friendly_name"],
            aliases=tuple(ch.get("aliases", [])),
            channel_number=str(ch.get("channel_number", "")),
        )
        for ch in tv_raw.get("channels", [])
    )
    tv = TvConfig(
        watch_activity=tv_raw["watch_activity"],
        audio=audio,
        channels=channels,
    )

    blinds = tuple(
        BlindDevice(
            id=b["id"],
            friendly_name=b["friendly_name"],
            homekit_entity_id=b["homekit_entity_id"],
            aliases=tuple(b.get("aliases", [])),
            invert=bool(b.get("invert", False)),
        )
        for b in raw.get("blinds", [])
    )

    thermostats = tuple(
        ThermostatDevice(
            id=t["id"],
            friendly_name=t["friendly_name"],
            fritz_name=t["fritz_name"],
            aliases=tuple(t.get("aliases", [])),
            min_celsius=float(t.get("min_celsius", 8.0)),
            max_celsius=float(t.get("max_celsius", 28.0)),
        )
        for t in raw.get("thermostats", [])
    )

    return DeviceRegistry(tv=tv, blinds=blinds, thermostats=thermostats)
