# ports/

**Location:** `pantau/ports/`  
**Rule:** No imports from `adapters/`. Ports define *what* is needed; adapters define *how* it's done.

Ports are abstract contracts — Python `Protocol` classes that define the interface between use-cases and infrastructure. They're the plugs in the wall: your business logic plugs into ports, and adapters plug into the other side.

Every port is intentionally narrow: it defines only the operations that the commands actually need, nothing more (*Interface Segregation Principle*).

## Why Protocol instead of ABC?

Python's `typing.Protocol` uses **structural subtyping** (duck typing). Any class with the right methods satisfies the protocol — no `class HarmonyTvAdapter(TvPort):` inheritance needed. This makes it easy to create test doubles without touching the production code.

```python
# Production adapter — implicitly satisfies TvPort
class HarmonyTvAdapter:
    async def ensure_activity(self, activity_name: str) -> None: ...
    async def set_channel(self, channel_number: str) -> None: ...
    ...

# Test double — also implicitly satisfies TvPort
class MockTvAdapter:
    async def ensure_activity(self, activity_name: str) -> None: pass
    async def set_channel(self, channel_number: str) -> None: pass
    ...
```

---

## TvPort

```python
class TvPort(Protocol):
    async def ensure_activity(self, activity_name: str) -> None:
        """Start the given Harmony activity if it is not already active."""

    async def set_channel(self, channel_number: str) -> None:
        """Switch to the given channel number."""

    async def toggle_mute(self) -> None:
        """Send the mute toggle command (IR-only, no discrete on/off)."""

    async def get_current_activity(self) -> str | None:
        """Return the currently active Harmony activity label, or None."""
```

**Implemented by:** `HarmonyTvAdapter` (production), `MockTvAdapter` (tests)

---

## BlindPort

```python
class BlindPort(Protocol):
    async def set_position(self, homekit_entity_id: str, percent: int) -> None:
        """Set the blind position (0 = closed, 100 = fully open)."""

    async def get_position(self, homekit_entity_id: str) -> int:
        """Return the current position percentage."""
```

**Implemented by:** `HomeKitBlindAdapter` (production), `MockBlindAdapter` (tests)

---

## ThermostatPort

```python
class ThermostatPort(Protocol):
    async def set_temperature(self, fritz_name: str, celsius: float) -> None:
        """Set the target temperature for the named thermostat."""
```

**Implemented by:** `FritzThermostatAdapter` (production), `MockThermostatAdapter` (tests)

---

## DeviceRegistryPort

```python
class DeviceRegistryPort(Protocol):
    def get_registry(self) -> DeviceRegistry:
        """Return the full device registry."""

    def find_channel(self, endpoint_id: str) -> ChannelDevice | None:
        """Find a channel device by Alexa endpoint ID."""

    def find_blind(self, endpoint_id: str) -> BlindDevice | None:
        """Find a blind device by Alexa endpoint ID."""

    def find_thermostat(self, endpoint_id: str) -> ThermostatDevice | None:
        """Find a thermostat by Alexa endpoint ID."""
```

Returns `None` (not an exception) when a device is not found — the commands convert `None` to `DeviceNotFoundError`.

**Implemented by:** `YamlDeviceRegistry`

---

## TokenValidatorPort

```python
@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: str
    scope: str

class TokenValidatorPort(Protocol):
    def validate(self, token: str) -> TokenClaims:
        """Validate the Bearer token. Raises ValueError if invalid or expired."""
```

Used by the `/alexa/directive` route to validate the JWT on every incoming directive.

**Implemented by:** `JwtService` (production), `MockTokenValidator` (tests)

---

## UserStorePort

```python
class UserStorePort(Protocol):
    async def get_user_by_username(self, username: str) -> UserRecord | None: ...
    async def create_user(self, username: str, password_hash: str) -> UserRecord: ...
    async def save_refresh_token(self, token: str, user_id: str, expires_at: datetime) -> None: ...
    async def get_refresh_token_user_id(self, token: str) -> str | None: ...
    async def revoke_refresh_token(self, token: str) -> None: ...
```

Used by the OAuth router for user lookups and refresh token lifecycle management.

**Implemented by:** `SqliteUserStore`

---

## BeaconPublisherPort

```python
class BeaconPublisherPort(Protocol):
    async def publish(self, base_url: str) -> None:
        """Write {base_url, updated_at, health} to S3 endpoint.json."""
```

::: info Phase 5 — planned
This port is defined but has no production adapter yet. The `S3BeaconPublisher` adapter will be implemented in Phase 5. The home server will call `publish()` at startup and periodically to keep the S3 beacon up-to-date with the current tunnel URL.
:::

---

## Port-to-adapter mapping

| Port | Production adapter | Test double |
|---|---|---|
| `TvPort` | `HarmonyTvAdapter` | `MockTvAdapter` |
| `BlindPort` | `HomeKitBlindAdapter` | `MockBlindAdapter` |
| `ThermostatPort` | `FritzThermostatAdapter` | `MockThermostatAdapter` |
| `DeviceRegistryPort` | `YamlDeviceRegistry` | `YamlDeviceRegistry` (test fixtures) |
| `TokenValidatorPort` | `JwtService` | `MockTokenValidator` |
| `UserStorePort` | `SqliteUserStore` | `SqliteUserStore` (in-memory `:memory:`) |
| `BeaconPublisherPort` | *(planned: S3BeaconPublisher)* | — |
