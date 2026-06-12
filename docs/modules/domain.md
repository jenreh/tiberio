# domain/

**Location:** `tiberio/domain/`
**Rule:** Zero imports from outside `domain/`. No I/O. No frameworks beyond Pydantic. Pure domain.

The domain is the heart of the application. It contains the vocabulary of your home automation system: what a TV channel is, what a thermostat is, what temperatures are valid. Everything else in the application depends on the domain — the domain depends on nothing.

## models.py — Device models

All models are **frozen Pydantic v2 models** (`BaseModel` with `model_config = ConfigDict(frozen=True)`). Once created, they cannot be mutated. This is intentional: device configuration doesn't change at runtime.

### Device — the shared base class

Every domain device inherits from `Device`. It carries the fields common to all devices and — crucially — the `adapter` discriminator that drives routing:

```python
class Device(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str                          # Unique device / endpoint ID
    name: str                        # Human-friendly name
    adapter: AdapterName             # Which backend owns this device
    aliases: tuple[str, ...] = ()    # Alternative names for discovery
```

The `adapter` field lets a generic command route to the right port without hard-coding type checks:

```python
async def turn_on(device: Device) -> None:
    port = container.resolve(device, PowerablePort)
    await port.turn_on(device)
```

`TvChannel`, `TvAudio`, `WindowBlind`, `Thermostat`, `Activity`, `HubDevice`, `HomeDevice` and `LiveThermostat` all inherit from `Device`.

### AdapterName & adapter constants

The `adapter` discriminator is a `Literal` type with three named constants:

```python
AdapterName = Literal["harmony", "homekit", "fritz"]

ADAPTER_HARMONY: AdapterName = "harmony"
ADAPTER_HOMEKIT: AdapterName = "homekit"
ADAPTER_FRITZ: AdapterName = "fritz"
```

These constants are what each device's `Device.adapter` field is set to, and what the composition root keys on when wiring a device to its adapter.

### DeviceRegistry

The top-level container, loaded once from `config/devices.yaml` at startup:

```python
class DeviceRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    tv: Tv
    blinds: tuple[WindowBlind, ...]
    thermostats: tuple[Thermostat, ...]

    def all_devices(self) -> tuple[Device, ...]:
        """Every configured device, regardless of type."""
        return (self.tv.audio, *self.tv.channels, *self.blinds, *self.thermostats)
```

`all_devices()` flattens the registry into a single tuple — handy for Alexa discovery, where every endpoint must be enumerated regardless of its type.

### Tv

```python
class Tv(BaseModel):
    model_config = ConfigDict(frozen=True)

    watch_activity: str                  # Harmony activity that enables TV viewing
    audio: TvAudio                       # The Speaker endpoint (mute/unmute)
    channels: tuple[TvChannel, ...]      # One per TV channel
```

### TvChannel

Each TV channel is a separate Alexa endpoint. "Alexa, switch on ZDF" → `TurnOn` on endpoint `zdf`.

```python
class TvChannel(Device):
    channel_number: str = ""    # Digits sent to the Harmony Hub
    watch_activity: str = ""    # Harmony activity to ensure before switching
```

Inherits `id`, `name`, `adapter` and `aliases` from `Device`.

### TvAudio

The single audio endpoint for mute/unmute. It adds nothing beyond the inherited `Device` fields:

```python
class TvAudio(Device):
    """The TV audio endpoint (mute/unmute via Alexa.Speaker)."""
```

### WindowBlind

```python
class WindowBlind(Device):
    external_id: str              # Adapter-specific reference (e.g. HomeKit entity_id)
    invert: bool = False          # True = motor axis is reversed
```

`external_id` is adapter-agnostic — for the HomeKit adapter it holds an entity id such as `cover.kueche`. The `invert` flag handles motors where the 0% position physically means "fully open" rather than "fully closed". When `invert=True`, the command layer flips the axis: `actual = 100 - requested`.

### Thermostat

```python
class Thermostat(Device):
    external_id: str              # Adapter-specific reference (e.g. FRITZ!Box device name)
    min_celsius: float = 8.0      # Hard floor for this specific device
    max_celsius: float = 28.0     # Hard ceiling for this specific device
```

`external_id` carries the adapter-specific reference — for the FRITZ!Box adapter it is the device name as shown on the box, e.g. `Wohnzimmer`.

### Live-discovered backend types

The configured types above describe what lives in `devices.yaml`. A second family of models represents devices and state discovered *live* from a backend at runtime. These are returned by the `list_*` methods on the ports and all inherit from `Device`:

```python
class Activity(Device):
    """A Harmony Hub activity (e.g. "Watch TV", "PowerOff")."""
    is_power_off: bool = False

class HubDevice(Device):
    """A physical device registered on the Harmony Hub."""
    manufacturer: str | None = None
    model: str | None = None

class HomeDevice(Device):
    """A device discovered on the smart-home network (e.g. via HomeKit)."""
    domain: str
    room: str | None = None

class LiveThermostat(Device):
    """A FRITZ!Box thermostat with real-time state."""
    online: bool
    current_temp: float
    target_temp: float
    battery_level: int | None = None
    battery_low: bool = False
```

::: tip Configured vs. live
`Tv`/`TvChannel`/`WindowBlind`/`Thermostat` are static configuration. `Activity`/`HubDevice`/`HomeDevice`/`LiveThermostat` are discovery results returned from a backend — they reflect the current world rather than the YAML file.
:::

---

## values.py — Value Objects

Value objects wrap primitive types. Where an invariant exists, it is enforced with a Pydantic validator at construction time.

### Temperature

```python
class Temperature(BaseModel):
    model_config = ConfigDict(frozen=True)

    celsius: float

    @classmethod
    def from_float(cls, value: float) -> Temperature:
        return cls(celsius=round(value * 2) / 2)  # round to 0.5-step
```

`Temperature.from_float(22.3)` → `Temperature(celsius=22.5)`. The FRITZ!Box only accepts 0.5 °C increments.

::: warning No range validation here
`Temperature` does **not** validate a min/max range. As its docstring states, the range is enforced by the command layer using each device's `Thermostat.min_celsius` / `Thermostat.max_celsius`. Constructing a `Temperature` does not guarantee it is within any device's accepted range.
:::

### Percentage

```python
class Percentage(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: int  # 0–100

    @model_validator(mode="after")
    def _validate_range(self) -> Percentage:
        if not (0 <= self.value <= 100):
            msg = f"Percentage {self.value} is outside the valid range 0–100"
            raise ValueError(msg)
        return self
```

Used for blind positions. Alexa sends a `rangeValue` (0–100); it becomes a `Percentage` before being passed to the blind command. The `@model_validator(mode="after")` rejects out-of-range values at construction time.

### MuteState

```python
class MuteState(Enum):
    MUTED = "muted"
    UNMUTED = "unmuted"
```

The Harmony Hub only supports a *toggle* mute command — there is no discrete "mute on" or "mute off". `SetTvMuteCommand` keeps track of the assumed current state as a `MuteState` and only sends the toggle if it needs to change the state.

> **Known limitation:** If someone presses the physical remote's mute button, the server's assumed state drifts out of sync. This is a documented trade-off — it cannot be solved without proactive state reporting from the Hub, which harmonyhub-py does not support.

---

## beacon.py — Endpoint Beacon

The `Beacon` is the public reachability record for the home server. It is published as `endpoint.json` to S3 so the AWS edge (the Lambda proxy) can discover the current tunnel URL. It never contains secrets.

```python
class Beacon(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str
    updated_at: str        # ISO-8601 timestamp
    health: str = "ok"
```

This ties into the OAuth/edge architecture: the home server keeps the beacon fresh, and the edge Lambda reads it to know where to forward Alexa directives.

---

## errors.py — Domain Errors

Domain-level exceptions that the Alexa handlers translate into Alexa error response codes (or surface as publish failures).

```python
class DeviceNotFoundError(Exception):
    """Endpoint ID doesn't match any configured device."""
    def __init__(self, endpoint_id: str) -> None:
        super().__init__(f"Device not found: {endpoint_id!r}")
        self.endpoint_id = endpoint_id

class DeviceUnavailableError(Exception):
    """Device can't be reached (network timeout, hub offline, etc.)."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class BeaconPublishError(Exception):
    """Publishing the endpoint beacon to remote storage failed."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class DeviceCapabilityError(Exception):
    """A found device does not support the requested capability."""
    def __init__(self, endpoint_id: str, capability: str) -> None:
        super().__init__(
            f"Device {endpoint_id!r} does not support capability {capability!r}"
        )
        self.endpoint_id = endpoint_id
        self.capability = capability
```

| Exception | Raised by | Maps to Alexa error |
|---|---|---|
| `DeviceNotFoundError` | Commands (registry lookup returns `None`) | `NO_SUCH_ENDPOINT` |
| `DeviceUnavailableError` | Adapters (library-specific exceptions) | `ENDPOINT_UNREACHABLE` |
| `DeviceCapabilityError` | Commands (device lacks requested capability) | `INVALID_VALUE` |
| `BeaconPublishError` | Beacon publisher (remote storage write fails) | — (publish-time failure, not an Alexa directive) |
