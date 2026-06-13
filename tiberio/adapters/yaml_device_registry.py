"""YAML device registry adapter — loads devices.yaml and resolves endpoint IDs."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tiberio.domain.models import (
    ADAPTER_FRITZ,
    ADAPTER_HARMONY,
    ADAPTER_HOMEKIT,
    Device,
    DeviceRegistry,
    Thermostat,
    Tv,
    TvAudio,
    TvChannel,
    WindowBlind,
)

log = logging.getLogger(__name__)


class YamlDeviceRegistry:
    """Loads DeviceRegistry from a YAML file and implements DeviceRegistryPort."""

    def __init__(self, config_path: Path) -> None:
        self._registry = _load(config_path)
        tv = self._registry.tv
        log.info(
            "DeviceRegistry loaded: %d channels, %d blinds, %d thermostats",
            len(tv.channels) if tv else 0,
            len(self._registry.blinds),
            len(self._registry.thermostats),
        )

    def get_registry(self) -> DeviceRegistry:
        return self._registry

    def find_device(self, endpoint_id: str) -> Device | None:
        """Find any configured device (channel, audio, blind, thermostat) by ID."""
        return next(
            (d for d in self._registry.all_devices() if d.id == endpoint_id), None
        )


def _load(path: Path) -> DeviceRegistry:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    tv = _load_tv(raw.get("tv"))

    blinds = tuple(
        WindowBlind(
            id=b["id"],
            name=b["friendly_name"],
            adapter=ADAPTER_HOMEKIT,
            external_id=b["homekit_entity_id"],
            aliases=tuple(b.get("aliases", [])),
            invert=bool(b.get("invert", False)),
        )
        for b in raw.get("blinds", [])
    )

    thermostats = tuple(
        Thermostat(
            id=t["id"],
            name=t["friendly_name"],
            adapter=ADAPTER_FRITZ,
            external_id=t["fritz_name"],
            aliases=tuple(t.get("aliases", [])),
            min_celsius=float(t.get("min_celsius", 8.0)),
            max_celsius=float(t.get("max_celsius", 28.0)),
        )
        for t in raw.get("thermostats", [])
    )

    registry = DeviceRegistry(tv=tv, blinds=blinds, thermostats=thermostats)
    _ensure_unique_ids(registry)
    return registry


def _load_tv(tv_raw: dict | None) -> Tv | None:
    """Build the optional TV configuration; ``None`` when no ``tv`` section."""
    if not tv_raw:
        return None

    watch_activity = tv_raw["watch_activity"]
    audio = TvAudio(
        id=tv_raw["audio"]["id"],
        name=tv_raw["audio"]["friendly_name"],
        adapter=ADAPTER_HARMONY,
        aliases=tuple(tv_raw["audio"].get("aliases", [])),
        watch_activity=watch_activity,
    )
    channels = tuple(
        TvChannel(
            id=ch["id"],
            name=ch["friendly_name"],
            adapter=ADAPTER_HARMONY,
            aliases=tuple(ch.get("aliases", [])),
            channel_number=str(ch.get("channel_number", "")),
            watch_activity=watch_activity,
        )
        for ch in tv_raw.get("channels", [])
    )
    return Tv(watch_activity=watch_activity, audio=audio, channels=channels)


def _ensure_unique_ids(registry: DeviceRegistry) -> None:
    """Duplicate endpoint IDs silently shadow devices — reject them at load."""
    all_ids = [d.id for d in registry.all_devices()]
    duplicates = sorted({i for i in all_ids if all_ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate device ids in devices.yaml: {duplicates}")
