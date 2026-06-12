# ports/

**Location:** `tiberio/ports/`
**Rule:** No imports from `adapters/`. Ports define *what* is needed; adapters define *how* it's done.

Ports are abstract contracts — Python `Protocol` classes that define the interface between use-cases and infrastructure. They're the plugs in the wall: your business logic plugs into ports, and adapters plug into the other side.

Every port is intentionally narrow: it defines only the operations that the commands actually need, nothing more (*Interface Segregation Principle*). Device-facing ports are **capability ports** — one port per capability (power, mute, volume, temperature, range, beacon publishing), not one port per backend. An adapter implements exactly the capabilities its devices support.

## Why Protocol instead of ABC?

Python's `typing.Protocol` uses **structural subtyping** (duck typing). Any class with the right methods satisfies the protocol — no `class HarmonyTvAdapter(PowerablePort):` inheritance needed. This makes it easy to create test doubles without touching the production code.

```python
# Production adapter — implicitly satisfies PowerablePort
class HarmonyTvAdapter:
    async def turn_on(self, device: Device) -> None: ...
    async def turn_off(self, device: Device) -> None: ...
    ...

# Test double — also implicitly satisfies PowerablePort
class MockTvAdapter:
    async def turn_on(self, device: Device) -> None: pass
    async def turn_off(self, device: Device) -> None: pass
    ...
```

The capability ports are additionally `@runtime_checkable`, so the container can check `isinstance(adapter, capability)` when resolving a device's adapter.

---

## PowerablePort

**File:** `ports/power_port.py`

```python
@runtime_checkable
class PowerablePort(Protocol):
    async def turn_on(self, device: Device) -> None: ...

    async def turn_off(self, device: Device) -> None: ...
```

**Implemented by:** `HarmonyTvAdapter` (production), `MockTvAdapter` (tests)

---

## MuteControllablePort

**File:** `ports/mute_port.py`

```python
@runtime_checkable
class MuteControllablePort(Protocol):
    async def set_mute(self, device: Device, muted: bool) -> None: ...

    async def get_mute(self, device: Device) -> bool:
        """Return the current (assumed) mute state."""
```

**Implemented by:** `HarmonyTvAdapter` (production), `MockTvAdapter` (tests)

---

## VolumeControllablePort

**File:** `ports/volume_port.py`

```python
@runtime_checkable
class VolumeControllablePort(Protocol):
    async def set_volume(self, device: Device, level: int) -> None: ...

    async def adjust_volume(self, device: Device, delta: int) -> int:
        """Adjust volume by delta steps; returns the new assumed level."""

    async def get_volume(self, device: Device) -> int:
        """Return the current (assumed) volume level."""
```

**Implemented by:** `HarmonyTvAdapter` (production), `MockTvAdapter` (tests)

---

## TemperatureControllablePort

**File:** `ports/temperature_port.py`

```python
@runtime_checkable
class TemperatureControllablePort(Protocol):
    async def set_temperature(self, device: Device, celsius: float) -> None: ...

    async def get_temperature(self, device: Device) -> float: ...
```

**Implemented by:** `FritzThermostatAdapter` (production), `MockThermostatAdapter` (tests)

---

## RangeControllablePort

**File:** `ports/range_port.py`

```python
@runtime_checkable
class RangeControllablePort(Protocol):
    async def set_range(self, device: Device, value: int) -> None: ...

    async def adjust_range(self, device: Device, delta: int) -> int: ...

    async def get_range(self, device: Device) -> int: ...
```

Used for devices with a 0–100 position range (currently blinds).

**Implemented by:** `HomeKitBlindAdapter` (production), `MockBlindAdapter` (tests)

---

## ListablePort

**File:** `ports/listable_port.py`

```python
BackendStatus = Literal["ok", "unavailable"]

@dataclass
class BackendListResult:
    """Serialisable result from one backend's list_backend() call."""
    status: BackendStatus
    data: dict = field(default_factory=dict)
    error: str | None = None

@runtime_checkable
class ListablePort(Protocol):
    adapter_name: str

    async def list_backend(self) -> BackendListResult: ...
```

Capability for adapters that can enumerate their live backend devices. `ListConnectedDevicesCommand` queries every registered adapter implementing this port; an offline backend reports `status="unavailable"` with an error message without affecting the others.

**Implemented by:** all production device adapters (`HarmonyTvAdapter`, `HomeKitBlindAdapter`, `FritzThermostatAdapter`)

---

## DeviceRegistryPort

**File:** `ports/device_registry_port.py`

```python
class DeviceRegistryPort(Protocol):
    def get_registry(self) -> DeviceRegistry:
        """Return the full device registry."""

    def find_device(self, endpoint_id: str) -> Device | None:
        """Find any configured device by its endpoint ID."""
```

Returns `None` (not an exception) when a device is not found — the commands convert `None` to `DeviceNotFoundError`.

**Implemented by:** `YamlDeviceRegistry`

---

## CapabilityResolverPort

**File:** `ports/capability_resolver_port.py`

```python
class CapabilityResolverPort(Protocol):
    def resolve(self, device: Device, capability: type[T]) -> T: ...

    def all_implementing(self, capability: type[T]) -> list[T]: ...
```

Commands depend on this port instead of importing the `Container` directly. The `Container` in `composition.py` satisfies it structurally: `resolve()` looks up the adapter registered under `device.adapter` and verifies that it implements the requested capability.

**Implemented by:** `Container` (composition root)

---

## TokenValidatorPort

**File:** `ports/token_validator_port.py`

```python
class TokenClaims(BaseModel):
    """Validated claims extracted from a bearer token."""
    model_config = ConfigDict(frozen=True)

    user_id: str
    scope: str

class TokenValidatorPort(Protocol):
    def validate(self, token: str) -> TokenClaims:
        """Validate the token and return its claims. Raises ValueError if invalid."""
```

Used by the `/alexa/directive` route to validate the JWT on every incoming directive.

**Implemented by:** `JwtService` (production), `MockTokenValidator` (tests)

---

## TokenIssuerPort

**File:** `ports/token_issuer_port.py`

```python
class TokenIssuerPort(Protocol):
    def issue_access_token(self, user_id: str) -> tuple[str, int]:
        """Return (encoded_token, expires_in_seconds)."""

    def issue_refresh_token(self) -> str:
        """Return a random, opaque refresh token."""
```

Used by the OAuth token endpoint to mint access/refresh token pairs.

**Implemented by:** `JwtService` (the same instance also implements `TokenValidatorPort`)

---

## AuthCodeStorePort

**File:** `ports/auth_code_store_port.py`

```python
class AuthCodeEntry(BaseModel):
    """A stored authorization code with its binding claims."""
    model_config = ConfigDict(frozen=True)

    code: str
    user_id: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    expires_at: datetime

class AuthCodeStorePort(Protocol):
    async def save(
        self, *, user_id: str, client_id: str, redirect_uri: str,
        code_challenge: str, code_challenge_method: str,
    ) -> str: ...

    async def lookup(self, code: str) -> AuthCodeEntry | None: ...

    async def redeem(self, code: str) -> AuthCodeEntry | None: ...
```

Stores single-use PKCE authorization codes. `lookup()` lets the token endpoint validate all claims *before* `redeem()` atomically consumes the code.

**Implemented by:** `AuthCodeStore` (in-memory)

---

## UserStorePort

**File:** `ports/user_store_port.py`

```python
class UserRecord(BaseModel):
    """A stored user."""
    model_config = ConfigDict(frozen=True)

    id: str
    username: str
    password_hash: str

class UserStorePort(Protocol):
    async def get_user_by_username(self, username: str) -> UserRecord | None: ...
    async def create_user(self, username: str, password_hash: str) -> UserRecord: ...
    async def save_refresh_token(self, token: str, user_id: str, expires_at: datetime) -> None: ...
    async def revoke_refresh_token(self, token: str) -> None: ...
    async def pop_refresh_token(self, token: str) -> str | None: ...
```

Used by the OAuth router for user lookups and refresh token lifecycle management. `pop_refresh_token()` is an atomic check-and-revoke: it returns the user ID and deletes the token in one step, so concurrent refresh requests cannot both succeed.

**Implemented by:** `SqliteUserStore`

---

## PasswordHasherPort

**File:** `ports/password_hasher_port.py`

```python
class PasswordHasherPort(Protocol):
    def hash_password(self, plain: str) -> str: ...

    def verify_password(self, plain: str, hashed: str | None) -> bool: ...
```

`verify_password` accepts `hashed=None` for unknown users: the implementation must burn comparable CPU time against a dummy hash and return `False`, so login latency does not reveal whether a username exists.

**Implemented by:** `BcryptPasswordHasher`

---

## BeaconPublisherPort

**File:** `ports/beacon_publisher_port.py`

```python
@runtime_checkable
class BeaconPublisherPort(Protocol):
    async def publish(self, beacon: Beacon) -> None: ...
```

Capability for publishing the endpoint beacon — a `Beacon` (`domain/beacon.py`) is the public reachability record (`base_url`, `updated_at`, `health`) written as `endpoint.json` so the AWS edge can discover the current tunnel URL. Never contains secrets.

Unlike the device-facing capability ports, this one is wired once via `_build_beacon_publisher(settings)`: `settings.beacon_enabled` selects the production `S3BeaconPublisher` (writes to the beacon bucket via boto3) or falls back to `MockBeaconPublisher` when disabled.

**Implemented by:** `S3BeaconPublisher` (production), `MockBeaconPublisher` (tests / beacon disabled)

---

## Port-to-adapter mapping

Capability ports are resolved **per device** via `Container.resolve(device, capability)`, keyed by the device's `adapter` field (`harmony`, `homekit`, `fritz`):

| Adapter name | Production adapter | Test double | Capabilities |
|---|---|---|---|
| `harmony` | `HarmonyTvAdapter` | `MockTvAdapter` | `PowerablePort`, `MuteControllablePort`, `VolumeControllablePort`, `ListablePort` |
| `homekit` | `HomeKitBlindAdapter` | `MockBlindAdapter` | `RangeControllablePort`, `ListablePort` |
| `fritz` | `FritzThermostatAdapter` | `MockThermostatAdapter` | `TemperatureControllablePort`, `ListablePort` |

Infrastructure ports are registered once under their port type:

| Port | Production adapter | Test double |
|---|---|---|
| `DeviceRegistryPort` | `YamlDeviceRegistry` | `YamlDeviceRegistry` (test fixtures) |
| `CapabilityResolverPort` | `Container` | `Container` |
| `TokenValidatorPort` | `JwtService` | `MockTokenValidator` |
| `TokenIssuerPort` | `JwtService` | `JwtService` (OAuth tests) |
| `AuthCodeStorePort` | `AuthCodeStore` | `AuthCodeStore` |
| `UserStorePort` | `SqliteUserStore` | `SqliteUserStore` (in-memory `:memory:`) |
| `PasswordHasherPort` | `BcryptPasswordHasher` | `BcryptPasswordHasher` |
| `BeaconPublisherPort` | `S3BeaconPublisher` | `MockBeaconPublisher` |
