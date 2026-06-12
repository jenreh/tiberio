# commands/

**Location:** `tiberio/commands/`
**Rule:** One class per use-case. Depends only on `ports/` and `domain/`. No imports from `adapters/` or `interfaces/`.

Commands (also called *use-cases*) are the application's business logic. Each command does exactly one thing and is named after that thing. This makes the codebase navigable: if you want to know how volume adjustment works, open `commands/adjust_volume.py`.

Commands are **device-agnostic**: they look up the device in the registry, then resolve the adapter that implements the required *capability port* via the `CapabilityResolverPort`. There are no per-backend sub-packages — the same `TurnOnCommand` works for any device whose adapter implements `PowerablePort`.

## Structure

```
commands/
├── __init__.py                 # Package marker (application-layer use-cases)
├── _base.py                    # DeviceCommand — shared find/resolve helpers
├── turn_on.py                  # TurnOn → PowerablePort.turn_on
├── turn_off.py                 # TurnOff → PowerablePort.turn_off
├── set_mute.py                 # SetMute(true/false) → MuteControllablePort
├── set_volume.py               # SetVolume(0–100) → VolumeControllablePort
├── adjust_volume.py            # AdjustVolume(delta) → VolumeControllablePort
├── get_speaker_state.py        # State report: (muted, volume)
├── set_range.py                # SetRangeValue(0–100) → RangeControllablePort
├── adjust_range.py             # AdjustRangeValue(delta) → RangeControllablePort
├── set_temperature.py          # SetTargetTemperature → TemperatureControllablePort
├── adjust_temperature.py       # AdjustTargetTemperature(delta) → delegates to set
├── discover_devices.py         # Alexa.Discovery → list all configured devices
└── list_connected_devices.py   # Live backend inventory via ListablePort
```

---

## DeviceCommand (shared base)

**File:** `commands/_base.py`

All device-targeting commands inherit from `DeviceCommand`, which holds the two dependencies every command needs and provides the lookup helpers:

```python
class DeviceCommand:
    def __init__(
        self, registry: DeviceRegistryPort, resolver: CapabilityResolverPort
    ) -> None:
        self._registry = registry
        self._resolver = resolver

    def _find_device(self, endpoint_id: str) -> Device:
        """Return the configured device or raise DeviceNotFoundError."""

    def _find_and_resolve(
        self, endpoint_id: str, capability: type[T]
    ) -> tuple[Device, T]:
        """Find the device and resolve the adapter implementing *capability*."""
```

`_find_device` converts a registry miss into `DeviceNotFoundError` (→ Alexa `NO_SUCH_ENDPOINT`). `_find_and_resolve` additionally asks the resolver for the adapter behind `device.adapter` that implements the requested capability port.

---

## TurnOnCommand / TurnOffCommand

**Files:** `commands/turn_on.py`, `commands/turn_off.py`

Power any device on or off via `PowerablePort`:

```python
class TurnOnCommand(DeviceCommand):
    async def execute(self, endpoint_id: str) -> None:
        device, adapter = self._find_and_resolve(endpoint_id, PowerablePort)
        await adapter.turn_on(device)
```

For TV channel devices the Harmony adapter handles activity orchestration internally (start the watch activity, then switch the channel).

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `PowerablePort`

---

## SetMuteCommand

**File:** `commands/set_mute.py`

Mutes or unmutes a device via `MuteControllablePort.set_mute(device, mute)`. Assumed-state tracking for IR-only toggle hardware lives in the adapter (`HarmonyTvAdapter`), not in the command.

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `MuteControllablePort`

---

## SetVolumeCommand / AdjustVolumeCommand

**Files:** `commands/set_volume.py`, `commands/adjust_volume.py`

`SetVolumeCommand` sets an absolute level; the value is validated with `Percentage(value=level)` (0–100, raises `ValueError` otherwise). `AdjustVolumeCommand` applies a relative delta and **returns the new assumed level** so the handler can build an accurate Alexa response:

```python
class AdjustVolumeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, delta: int) -> int:
        device, adapter = self._find_and_resolve(endpoint_id, VolumeControllablePort)
        return await adapter.adjust_volume(device, delta)
```

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `VolumeControllablePort`

---

## GetSpeakerStateCommand

**File:** `commands/get_speaker_state.py`

Reads the current speaker state for Alexa state reports. Resolves *two* capabilities for the same device and returns `(muted, volume)`:

```python
class GetSpeakerStateCommand(DeviceCommand):
    async def execute(self, endpoint_id: str) -> tuple[bool, int]:
        device = self._find_device(endpoint_id)
        mute_adapter = self._resolver.resolve(device, MuteControllablePort)
        volume_adapter = self._resolver.resolve(device, VolumeControllablePort)
        return await mute_adapter.get_mute(device), await volume_adapter.get_volume(device)
```

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `MuteControllablePort` + `VolumeControllablePort`

---

## SetRangeCommand

**File:** `commands/set_range.py`

Sets a range device (e.g. a blind) to an absolute position (0 = closed, 100 = fully open). The percentage is validated with `Percentage(value=percent)`; axis inversion for reversed motors is handled inside `HomeKitBlindAdapter`.

```python
class SetRangeCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, percent: int) -> None:
        device, adapter = self._find_and_resolve(endpoint_id, RangeControllablePort)
        Percentage(value=percent)  # validates 0–100
        await adapter.set_range(device, percent)
```

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `RangeControllablePort`

---

## AdjustRangeCommand

**File:** `commands/adjust_range.py`

Adjusts a range device by a relative delta. "Alexa, lower the kitchen blind by 20%" sends `rangeValueDelta = -20`. Delegates to `RangeControllablePort.adjust_range(device, delta)` (the adapter reads the current position, clamps to 0–100, and sets the new value) and **returns the new position**.

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `RangeControllablePort`

---

## SetTemperatureCommand

**File:** `commands/set_temperature.py`

Sets a thermostat to a target temperature and **returns the applied (0.5-rounded) value**:

```python
class SetTemperatureCommand(DeviceCommand):
    async def execute(self, endpoint_id: str, celsius: float) -> float:
        device = self._find_device(endpoint_id)
        if not isinstance(device, Thermostat):
            raise DeviceCapabilityError(endpoint_id, "TemperatureControllable")

        temp = Temperature.from_float(celsius)  # rounds to 0.5 °C
        if not (device.min_celsius <= temp.celsius <= device.max_celsius):
            raise ValueError(...)  # → Alexa VALUE_OUT_OF_RANGE

        adapter = self._resolver.resolve(device, TemperatureControllablePort)
        await adapter.set_temperature(device, temp.celsius)
        return temp.celsius
```

Two layers of range validation:
- `Temperature.from_float()` enforces the global safe range.
- The command enforces the *per-device* min/max from `devices.yaml`.

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort` → `TemperatureControllablePort`

---

## AdjustTemperatureCommand

**File:** `commands/adjust_temperature.py`

Adjusts the thermostat target by a relative delta. It reads the current target setpoint via `TemperatureControllablePort.get_temperature()`, adds the delta, and **delegates to `SetTemperatureCommand`** — so rounding and both range validations apply identically:

```python
class AdjustTemperatureCommand(DeviceCommand):
    def __init__(
        self,
        registry: DeviceRegistryPort,
        resolver: CapabilityResolverPort,
        set_temperature: SetTemperatureCommand,
    ) -> None: ...

    async def execute(self, endpoint_id: str, delta_celsius: float) -> float:
        ...
        current = await adapter.get_temperature(device)
        return await self._set_temperature.execute(
            endpoint_id, celsius=current + delta_celsius
        )
```

Returns the applied setpoint.

**Dependencies:** `DeviceRegistryPort`, `CapabilityResolverPort`, `SetTemperatureCommand`

---

## DiscoverDevicesCommand

**File:** `commands/discover_devices.py`

Returns all configured devices as a flat list of `DiscoveredDevice` objects. The Alexa Discovery handler then maps each device to the correct Alexa capability descriptor.

```python
CapabilityKind = Literal["power", "speaker", "range", "thermostat"]

class DiscoveredDevice(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    capability: CapabilityKind

class DiscoverDevicesCommand:
    async def execute(self) -> list[DiscoveredDevice]:
        registry = self._registry.get_registry()
        channels = [DiscoveredDevice(id=ch.id, ..., capability="power") ...]
        audio = [DiscoveredDevice(id=registry.tv.audio.id, ..., capability="speaker")]
        blinds = [DiscoveredDevice(..., capability="range") ...]
        thermostats = [DiscoveredDevice(..., capability="thermostat") ...]
        return channels + audio + blinds + thermostats
```

**Dependencies:** `DeviceRegistryPort`

---

## ListConnectedDevicesCommand

**File:** `commands/list_connected_devices.py`

Queries every registered adapter that implements `ListablePort` for its live backend inventory and returns a mapping of `adapter_name → serialisable data`:

```python
class ListConnectedDevicesCommand:
    def __init__(self, resolver: CapabilityResolverPort) -> None: ...

    async def execute(self) -> dict[str, dict]:
        adapters = self._resolver.all_implementing(ListablePort)
        backends = await asyncio.gather(
            *[a.list_backend() for a in adapters], return_exceptions=True
        )
        ...
```

Each backend is queried independently. In the normal path the entry's `status` is taken verbatim from the adapter's `BackendListResult.status` (a `BackendStatus` of `"ok"` or `"unavailable"`), and any `error` message it reports is passed through — so a reachable-but-erroring backend can surface its own status plus an error. Only if a `list_backend()` call raises an *unexpected* exception does this command synthesise `status="unavailable"` with a generic error. Either way the other backends are unaffected (per-backend isolation). Adding a new adapter (e.g. Hue, Sonos) only requires implementing `ListablePort` and registering it — this command never changes.

**Dependencies:** `CapabilityResolverPort` → `ListablePort`
