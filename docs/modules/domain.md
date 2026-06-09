# domain/

**Location:** `pantau/domain/`  
**Rule:** Zero imports from outside `domain/`. No I/O. No frameworks. Pure Python.

The domain is the heart of the application. It contains the vocabulary of your home automation system: what a TV channel is, what a thermostat is, what temperatures are valid. Everything else in the application depends on the domain — the domain depends on nothing.

## models.py — Device models

All models are **frozen dataclasses** (`frozen=True, slots=True`). Once created, they cannot be mutated. This is intentional: device configuration doesn't change at runtime.

### DeviceRegistry

The top-level container, loaded once from `config/devices.yaml` at startup:

```python
@dataclass(frozen=True, slots=True)
class DeviceRegistry:
    tv: TvConfig
    blinds: tuple[BlindDevice, ...]
    thermostats: tuple[ThermostatDevice, ...]
```

### TvConfig

```python
@dataclass(frozen=True, slots=True)
class TvConfig:
    harmony_host: str       # LAN IP of the Harmony Hub
    watch_activity: str     # Harmony activity that enables TV viewing
    audio: TvAudioDevice    # The Speaker endpoint (mute/unmute)
    channels: tuple[ChannelDevice, ...]  # One per TV channel
```

### ChannelDevice

Each TV channel is a separate Alexa endpoint. "Alexa, switch on ZDF" → `TurnOn` on endpoint `zdf`.

```python
@dataclass(frozen=True, slots=True)
class ChannelDevice:
    id: str                          # Alexa endpoint ID (unique, URL-safe)
    friendly_name: str               # What Alexa calls this device
    aliases: tuple[str, ...] = ()    # Alternative names for discovery
    channel_number: str = ""         # Digits sent to the Harmony Hub
```

### TvAudioDevice

The single audio endpoint for mute/unmute:

```python
@dataclass(frozen=True, slots=True)
class TvAudioDevice:
    id: str
    friendly_name: str
```

### BlindDevice

```python
@dataclass(frozen=True, slots=True)
class BlindDevice:
    id: str
    friendly_name: str
    homekit_entity_id: str        # Entity ID in the HomeKit library
    aliases: tuple[str, ...] = ()
    invert: bool = False          # True = motor axis is reversed
```

The `invert` flag handles motors where the HomeKit 0% position physically means "fully open" rather than "fully closed". When `invert=True`, the command layer flips the axis: `actual = 100 - requested`.

### ThermostatDevice

```python
@dataclass(frozen=True, slots=True)
class ThermostatDevice:
    id: str
    friendly_name: str
    fritz_name: str               # Device name as shown on the FRITZ!Box
    aliases: tuple[str, ...] = ()
    min_celsius: float = 8.0      # Hard floor for this specific device
    max_celsius: float = 28.0     # Hard ceiling for this specific device
```

---

## values.py — Value Objects

Value objects wrap primitive types and enforce invariants in `__post_init__`. If a `Temperature` object exists, you *know* it's within the valid range.

### Temperature

```python
@dataclass(frozen=True, slots=True)
class Temperature:
    celsius: float

    def __post_init__(self) -> None:
        if not (8.0 <= self.celsius <= 28.0):
            raise ValueError(f"Temperature {self.celsius}°C out of range 8–28°C")

    @classmethod
    def from_float(cls, value: float) -> Temperature:
        """Round to nearest 0.5 °C step (FRITZ!Box requirement)."""
        return cls(celsius=round(value * 2) / 2)
```

`Temperature.from_float(22.3)` → `Temperature(celsius=22.5)`. The FRITZ!Box only accepts 0.5 °C increments.

### Percentage

```python
@dataclass(frozen=True, slots=True)
class Percentage:
    value: int  # 0–100

    def __post_init__(self) -> None:
        if not (0 <= self.value <= 100):
            raise ValueError(f"Percentage {self.value} out of range 0–100")

    @classmethod
    def half(cls) -> Percentage: return cls(value=50)

    @classmethod
    def closed(cls) -> Percentage: return cls(value=0)

    @classmethod
    def open(cls) -> Percentage: return cls(value=100)
```

Used for blind positions. Alexa sends a `rangeValue` (0–100); it becomes a `Percentage` before being passed to the blind command.

### MuteState

```python
class MuteState(Enum):
    MUTED = "muted"
    UNMUTED = "unmuted"
```

The Harmony Hub only supports a *toggle* mute command — there is no discrete "mute on" or "mute off". `SetTvMuteCommand` keeps track of the assumed current state as a `MuteState` and only sends the toggle if it needs to change the state.

> **Known limitation:** If someone presses the physical remote's mute button, the server's assumed state drifts out of sync. This is a documented trade-off — it cannot be solved without proactive state reporting from the Hub, which harmonyhub-py does not support.

---

## errors.py — Domain Errors

Two domain-level exceptions that the Alexa handlers translate into Alexa error response codes.

```python
class DeviceNotFoundError(Exception):
    """Endpoint ID doesn't match any configured device."""
    def __init__(self, endpoint_id: str) -> None:
        self.endpoint_id = endpoint_id

class DeviceUnavailableError(Exception):
    """Device can't be reached (network timeout, hub offline, etc.)."""
```

| Exception | Raised by | Maps to Alexa error |
|---|---|---|
| `DeviceNotFoundError` | Commands (registry lookup returns `None`) | `NO_SUCH_ENDPOINT` |
| `DeviceUnavailableError` | Adapters (library-specific exceptions) | `ENDPOINT_UNREACHABLE` |
