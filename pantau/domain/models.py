"""Domain models — immutable data structures representing the home automation domain."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ChannelDevice:
    """A TV channel exposed as an Alexa PowerController endpoint."""

    id: str
    friendly_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    channel_number: str = ""


@dataclass(frozen=True, slots=True)
class TvAudioDevice:
    """The TV audio endpoint (mute/unmute via Alexa.Speaker)."""

    id: str
    friendly_name: str


@dataclass(frozen=True, slots=True)
class TvConfig:
    """Configuration for the Harmony Hub TV integration."""

    watch_activity: str
    audio: TvAudioDevice
    channels: tuple[ChannelDevice, ...]


@dataclass(frozen=True, slots=True)
class BlindDevice:
    """A roller blind/shutter controlled via HomeKit (Alexa.RangeController)."""

    id: str
    friendly_name: str
    homekit_entity_id: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    invert: bool = False


@dataclass(frozen=True, slots=True)
class ThermostatDevice:
    """A heating thermostat controlled via fritzctl (Alexa.ThermostatController)."""

    id: str
    friendly_name: str
    fritz_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    min_celsius: float = 8.0
    max_celsius: float = 28.0


@dataclass(frozen=True, slots=True)
class DeviceRegistry:
    """All configured devices, loaded from devices.yaml."""

    tv: TvConfig
    blinds: tuple[BlindDevice, ...]
    thermostats: tuple[ThermostatDevice, ...]


# ---------------------------------------------------------------------------
# Live backend discovery types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConnectedDevice:
    """Base class for all live-discovered backend devices."""


@dataclass(frozen=True, slots=True)
class HarmonyActivity:
    """A Harmony Hub activity (equivalent to one entry in `harmony config`)."""

    id: str
    label: str
    is_power_off: bool = False


@dataclass(frozen=True, slots=True)
class HarmonyHubDevice(ConnectedDevice):
    """A physical device controlled by the Harmony Hub."""

    id: str
    label: str
    manufacturer: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class HomeKitDevice(ConnectedDevice):
    """A HomeKit device (equivalent to one entry in `homekit entities`)."""

    entity_id: str
    name: str
    domain: str
    room: str | None = None


@dataclass(frozen=True, slots=True)
class FritzDevice(ConnectedDevice):
    """A FRITZ!Box smart-home device (equivalent to one entry in `fritzctl list`)."""

    id: str
    name: str
    online: bool
    current_temp: float
    target_temp: float
    battery_level: int | None = None
    battery_low: bool = False
