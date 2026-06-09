# commands/

**Location:** `pantau/commands/`  
**Rule:** One class per use-case. Depends only on `ports/` and `domain/`. No imports from `adapters/` or `interfaces/`.

Commands (also called *use-cases*) are the application's business logic. Each command does exactly one thing and is named after that thing. This makes the codebase navigable: if you want to know how channel switching works, open `commands/tv/activate_channel.py`.

## Structure

```
commands/
├── tv/
│   ├── activate_channel.py       # TurnOn a channel → start TV activity + set channel
│   └── set_tv_mute.py            # SetMute(true/false) with assumed-state tracking
├── blinds/
│   ├── set_blind_position.py     # SetRangeValue(0–100) → HomeKit set_position
│   └── adjust_blind_position.py  # AdjustRangeValue(delta) → relative adjustment
├── heating/
│   └── set_thermostat_temperature.py  # SetTargetTemperature → fritzctl set_temperature
└── discover_devices.py           # Alexa.Discovery → list all configured devices
```

---

## ActivateChannelCommand

**File:** `commands/tv/activate_channel.py`

Turns on a TV channel. This is a two-step orchestration:
1. Check if the `watch_activity` is already active in Harmony. If not, start it.
2. Set the channel number.

The reason for step 1: Harmony Hub activities control which devices turn on and which HDMI input is selected. If you just send `set_channel("2")` without the activity running, nothing happens.

```python
class ActivateChannelCommand:
    def __init__(self, registry: DeviceRegistryPort, tv: TvPort) -> None: ...

    async def execute(self, endpoint_id: str) -> None:
        channel = self._registry.find_channel(endpoint_id)
        if channel is None:
            raise DeviceNotFoundError(endpoint_id)  # → Alexa NO_SUCH_ENDPOINT

        await self._tv.ensure_activity(registry.tv.watch_activity)
        await self._tv.set_channel(channel.channel_number)
```

**Dependencies:** `DeviceRegistryPort`, `TvPort`

---

## SetTvMuteCommand

**File:** `commands/tv/set_tv_mute.py`

Mutes or unmutes the TV. The Harmony Hub only supports a toggle IR command — no discrete mute-on/mute-off. This command tracks the *assumed* current mute state and only sends the toggle when the state needs to change.

```python
class SetTvMuteCommand:
    def __init__(self, registry: DeviceRegistryPort, tv: TvPort) -> None:
        self._assumed_state = MuteState.UNMUTED  # starts unmuted

    async def execute(self, endpoint_id: str, mute: bool) -> None:
        # ... find device ...
        target = MuteState.MUTED if mute else MuteState.UNMUTED
        if self._assumed_state != target:
            await self._tv.toggle_mute()
            self._assumed_state = target
```

Because this command tracks state across calls, it is registered as a **singleton** in `composition.py`.

**Dependencies:** `DeviceRegistryPort`, `TvPort`

---

## SetBlindPositionCommand

**File:** `commands/blinds/set_blind_position.py`

Sets a blind to an absolute position (0 = closed, 100 = fully open).

```python
async def execute(self, endpoint_id: str, percent: int) -> None:
    device = self._registry.find_blind(endpoint_id)
    if device is None:
        raise DeviceNotFoundError(endpoint_id)

    position = Percentage(value=percent)  # validates 0–100
    actual = (100 - position.value) if device.invert else position.value
    await self._blind.set_position(device.homekit_entity_id, actual)
```

The `invert` flag on `BlindDevice` flips the axis for motors where the HomeKit convention is reversed.

**Dependencies:** `DeviceRegistryPort`, `BlindPort`

---

## AdjustBlindPositionCommand

**File:** `commands/blinds/adjust_blind_position.py`

Adjusts a blind by a relative delta. "Alexa, lower the kitchen blind by 20%" sends `rangeValueDelta = -20`.

The command:
1. Reads the current position via `BlindPort.get_position()`.
2. Adds the delta, clamping to 0–100.
3. Sets the new absolute position.
4. Returns the final position so the handler can build an accurate Alexa response.

**Dependencies:** `DeviceRegistryPort`, `BlindPort`

---

## SetThermostatTemperatureCommand

**File:** `commands/heating/set_thermostat_temperature.py`

Sets a thermostat to a target temperature.

```python
async def execute(self, endpoint_id: str, celsius: float) -> None:
    device = self._registry.find_thermostat(endpoint_id)
    if device is None:
        raise DeviceNotFoundError(endpoint_id)

    temp = Temperature.from_float(celsius)  # rounds to 0.5 °C
    if not (device.min_celsius <= temp.celsius <= device.max_celsius):
        raise ValueError(f"Temperature {temp.celsius}°C outside device range ...")

    await self._thermostat.set_temperature(device.fritz_name, temp.celsius)
```

Two layers of range validation:
- `Temperature.from_float()` enforces the global safe range (8–28 °C).
- The command enforces the *per-device* min/max from `devices.yaml`.

**Dependencies:** `DeviceRegistryPort`, `ThermostatPort`

---

## DiscoverDevicesCommand

**File:** `commands/discover_devices.py`

Returns all configured devices as a flat list of `DiscoveredDevice` objects. The Alexa Discovery handler then maps each device to the correct Alexa capability descriptor.

```python
@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    id: str
    friendly_name: str
    capability: Literal["power", "speaker", "range", "thermostat"]

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
