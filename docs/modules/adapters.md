# adapters/

**Location:** `tiberio/adapters/`
**Rule:** Each adapter wraps exactly one external library or technology. It translates library-specific exceptions into domain errors.

Adapters are the bridge between your clean business logic and the messy real world. They speak "harmonyhub" or "FRITZ!Box" externally and "domain model" internally. If the Harmony library changes its API, you change exactly one file: `harmony_tv_adapter.py`.

---

## Device Adapters

### HarmonyTvAdapter

**File:** `adapters/harmony_tv_adapter.py`
**Library:** `harmonyhub` (wraps `harmonyhub.service.HarmonyService`)
**Implements:** `PowerablePort`, `MuteControllablePort`, `VolumeControllablePort`, `ListablePort`, `Lifecycle`

Controls the Logitech Harmony Hub. Unlike a long-lived connection, **each public method opens its own short-lived session** via `async with HarmonyService() as service:`, does its work, then disconnects — no persistent WebSocket is kept alive between calls. Because of this, `start()`/`stop()` are no-ops (present only to satisfy `Lifecycle`).

Mute and volume are **assumed state**: the Harmony only exposes toggle-style IR commands, so the adapter tracks the last-known mute state and volume level internally and guards read-modify-write with an `asyncio.Lock`. It must be wired as a singleton so this assumed state survives across directives.

```python
class HarmonyTvAdapter:
    def __init__(self, *, service_factory: Callable[[], Any] | None = None) -> None:
        self._service_factory = service_factory or HarmonyService
        self._assumed_mute_state = MuteState.UNMUTED
        self._assumed_volume = 50
        self._state_lock = asyncio.Lock()

    async def start(self) -> None:  # no-op — connections are per operation
        ...

    async def stop(self) -> None:   # no-op — connections are per operation
        ...

    async def turn_on(self, device: Device) -> None:
        if isinstance(device, TvChannel):
            await self.ensure_activity(device.watch_activity)
            await self.set_channel(device.channel_number)

    async def ensure_activity(self, activity_name: str) -> None:  # internal helper
        try:
            async with self._service_factory() as service:
                status = await service.client.get_current_activity()
                if status.activity_label != activity_name:
                    await service.client.start_activity(activity_name)
        except HarmonyHubError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
```

**Public port surface:**
- `turn_on(device)` / `turn_off(device)` — `PowerablePort`. `turn_on` of a `TvChannel` ensures the watch activity then tunes the channel; `turn_off` ends the current Harmony activity.
- `set_mute(device, muted)` / `get_mute(device)` — `MuteControllablePort`, backed by assumed mute state (toggles only when the desired state differs).
- `set_volume(device, level)` / `adjust_volume(device, delta)` / `get_volume(device)` — `VolumeControllablePort`, sending `volume_up`/`volume_down` IR keys relative to the assumed level.
- `list_backend()` — `ListablePort`, returning the Hub's activities and devices.

**Key behaviors:**
- `ensure_activity` is an internal helper (not a port method): if the activity is already active, it skips `start_activity`.
- All `harmonyhub.exceptions.HarmonyHubError` failures are caught and re-raised as `DeviceUnavailableError`.

---

### HomeKitBlindAdapter

**File:** `adapters/homekit_blind_adapter.py`
**Library:** `homekit` (wraps `homekit.client.HomeKitClient`)
**Implements:** `RangeControllablePort`, `ListablePort`, `Lifecycle`

Controls roller blinds and window coverings connected via HomeKit. Holds a **single persistent `HomeKitClient`** whose daemon is started once on server startup and stopped on shutdown (`start()`/`stop()` from the FastAPI lifespan), avoiding per-call BLE/IP connection overhead.

Methods take `Device` objects (not raw entity ids): the adapter narrows them to `WindowBlind`, resolves `WindowBlind.external_id`, and honours the per-device `invert` flag — converting between Alexa-space position (0=closed, 100=open) and the HomeKit value.

```python
class HomeKitBlindAdapter:
    def __init__(self, *, client: HomeKitClient | None = None) -> None:
        self._client = client or HomeKitClient()

    async def start(self) -> None:   # start the HomeKit daemon
        await self._client.start()

    async def stop(self) -> None:    # stop the HomeKit daemon
        await self._client.stop()

    async def set_range(self, device: Device, value: int) -> None:
        blind = _as_blind(device)
        actual = (100 - value) if blind.invert else value
        await self._set_position(blind.external_id, actual)

    async def get_range(self, device: Device) -> int:
        blind = _as_blind(device)
        homekit_pos = await self._get_position(blind.external_id)
        return (100 - homekit_pos) if blind.invert else homekit_pos
```

**Public port surface:**
- `set_range(device, value)` / `adjust_range(device, delta)` / `get_range(device)` — `RangeControllablePort`.
- `list_backend()` — `ListablePort`, returning all paired HomeKit devices.

Non-blind devices raise `DeviceCapabilityError`; `AccessoryNotFoundError` and other `HomeKitError`s are re-raised as `DeviceUnavailableError`.

---

### FritzThermostatAdapter

**File:** `adapters/fritz_thermostat_adapter.py`
**Library:** `fritzctl` (wraps `fritzctl.avm.clients` — `get_avm_client`, `AVMClientAbstract`)
**Implements:** `TemperatureControllablePort`, `ListablePort`, `Lifecycle`

Controls FRITZ!DECT smart thermostats via the AVM Home Automation API. Holds a **persistent `httpx.AsyncClient`** plus AVM client created in `start()` and closed in `stop()` (FastAPI lifespan), so the HTTP session lives for the whole server lifetime.

Methods take `Device` objects: the adapter narrows them to `Thermostat` and resolves `Thermostat.external_id` (the human-readable name) to the internal AIN (Actor Identification Number). AIN lookups are cached in `self._ain_cache`; a stale cache entry is dropped on failure so the next call re-resolves.

```python
class FritzThermostatAdapter:
    def __init__(self, *, client: AVMClientAbstract | None = None) -> None:
        self._injected = client
        self._http: httpx.AsyncClient | None = None
        self._client: AVMClientAbstract | None = client
        self._ain_cache: dict[str, str] = {}  # external_id → AIN

    async def start(self) -> None:   # open session, auto-detect the AVM API
        if self._injected is None:
            self._http = httpx.AsyncClient()
            self._client = await get_avm_client(self._http)

    async def stop(self) -> None:    # close the httpx session
        if self._injected is None and self._http is not None:
            await self._http.aclose()
        self._ain_cache.clear()

    async def set_temperature(self, device: Device, celsius: float) -> None:
        thermostat = _as_thermostat(device)
        await self._set_temperature_impl(thermostat.external_id, celsius)
```

**Public port surface:**
- `set_temperature(device, celsius)` / `get_temperature(device)` — `TemperatureControllablePort`.
- `list_backend()` — `ListablePort`, returning all FRITZ!Box thermostats with live state.

Unknown device names raise `DeviceNotFoundError`; transport failures (`httpx.HTTPError`, `TimeoutError`, `PermissionError`) become `DeviceUnavailableError`.

---

## Auth Adapters

### JwtService

**File:** `adapters/jwt_service.py`
**Library:** `python-jose` (`jose`)
**Dual role:** Implements `TokenIssuerPort` (issues access/refresh tokens) and `TokenValidatorPort` (validates access tokens)

```python
class JwtService:
    def issue_access_token(self, user_id: str) -> tuple[str, int]:
        """Returns (encoded_jwt, expires_in_seconds)."""
        payload = {
            "sub": user_id,
            "scope": "alexa",
            "iat": now,
            "exp": now + expire_minutes,
            "jti": secrets.token_hex(16),  # unique token ID
        }
        return jwt.encode(payload, self._secret, algorithm="HS256"), expires_in

    def issue_refresh_token(self) -> str:
        """Returns a random opaque token (not a JWT)."""
        return secrets.token_urlsafe(32)

    def validate(self, token: str) -> TokenClaims:
        """Raises ValueError if the token is invalid or expired."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        except JWTError as exc:
            raise ValueError("Invalid or expired token") from exc
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")
        return TokenClaims(user_id=str(user_id), scope=str(payload.get("scope", "")))
```

**Note:** Refresh tokens are *not* JWTs — they are random opaque strings stored (hashed) in SQLite. Only access tokens are JWTs. `validate` is defensive: it wraps `jose.JWTError` into `ValueError`, reads claims via `payload.get()`, and rejects a missing/empty `sub`.

Token issuance and validation run behind a **Lambda Function URL** (the OAuth transport migrated off API Gateway); the adapter itself is transport-agnostic and unaffected by that change.

---

### BcryptPasswordHasher

**File:** `adapters/password_hasher.py`
**Library:** `bcrypt`
**Implements:** `PasswordHasherPort`

Single source of truth for password hashing — used by the OAuth login flow (via `PasswordHasherPort`) and the `tiberio-users` CLI. The module also exposes plain functions `hash_password(plain)` and `verify_password(plain, hashed)`.

`BcryptPasswordHasher.verify_password` defends against user-enumeration timing attacks: when the stored hash is `None` (unknown user) it verifies against a lazily-created dummy hash of the same cost factor, so failed logins for unknown and known users take comparable time, and always returns `False`.

---

### SqliteUserStore

**File:** `adapters/sqlite_user_store.py`
**Library:** `aiosqlite`
**Implements:** `UserStorePort`, `Lifecycle`

Async SQLite store for users and refresh tokens. Creates its schema on `start()`. Default db path is `tiberio_users.db`.

Tables:
- `users (id TEXT PK, username TEXT UNIQUE, password_hash TEXT)`
- `refresh_tokens (token TEXT PK, user_id TEXT, expires_at TEXT)`

**Security:** the `token` column does *not* hold raw refresh tokens — they are stored **hashed** via `_hash_token` (SHA-256), so a database leak does not expose usable tokens.

**Lifecycle:** The connection is opened in `start()` and closed in `stop()`, managed through the FastAPI lifespan context.

**Core port method** worth highlighting:
- `pop_refresh_token(token)` — atomically validates and revokes a refresh token in one `DELETE ... RETURNING` statement, returning the `user_id` if valid and unexpired, else `None`.

**Admin operations** (beyond `UserStorePort`) used by the CLI:
- `list_users()` — list all accounts
- `delete_user(username) -> bool` — remove user and their tokens; returns whether the user existed
- `update_password(username, new_hash) -> bool` — rotate a password; returns whether the user existed

---

### AuthCodeStore

**File:** `adapters/auth_code_store.py`
**Storage:** In-memory (dict)

An in-memory store for OAuth2 authorization codes. Codes are short-lived (TTL fixed at exactly 300 seconds / 5 minutes via `_CODE_TTL_SECONDS`) and single-use, so SQLite persistence is not needed — if the server restarts during Account Linking, the user simply re-authenticates.

```python
class AuthCodeStore:
    def generate_code(self) -> str:
        """Return a fresh random opaque code."""

    async def save(self, *, user_id, client_id, redirect_uri,
                   code_challenge, code_challenge_method) -> str:
        """Generate a random code and store the entry. Returns the code."""

    async def lookup(self, code: str) -> AuthCodeEntry | None:
        """Return the entry without consuming it (None if absent/expired)."""

    async def redeem(self, code: str) -> AuthCodeEntry | None:
        """Return and atomically delete the entry. Returns None if not found/expired."""
```

`save` takes keyword-only arguments. `lookup` is a non-consuming read (used to validate before redemption), while `redeem` consumes the entry.

---

### YamlDeviceRegistry

**File:** `adapters/yaml_device_registry.py`
**Implements:** `DeviceRegistryPort`

Loads `config/devices.yaml` at startup using Pydantic for validation. Builds the `DeviceRegistry` domain model. Supports fast O(1) lookups by building index dicts `{endpoint_id → device}` at load time.

---

## Beacon Publishing Adapters

These adapters back the beacon / endpoint-discovery mechanism: the home server publishes a `Beacon` describing its current reachable base URL so the AWS side can discover where to send directives.

### S3BeaconPublisher

**File:** `adapters/s3_beacon_publisher.py`
**Library:** `boto3`
**Implements:** `BeaconPublisherPort`

Writes the beacon JSON (`endpoint.json`) to an S3 bucket via `put_object`. boto3 is synchronous, so the call runs in a worker thread via `asyncio.to_thread`. `BotoCoreError`/`ClientError` failures are re-raised as `BeaconPublishError`. The object body never contains secrets.

### MockBeaconPublisher

**File:** `adapters/mock_beacon_publisher.py`
**Implements:** `BeaconPublisherPort`

Test/local-dev double that records published beacons in an in-memory `published` list instead of touching AWS.

---

## Mock Adapters (test doubles)

| File | Implements | Behavior |
|---|---|---|
| `mock_tv_adapter.py` | `PowerablePort`, `MuteControllablePort`, `VolumeControllablePort`, `ListablePort` | Records calls; never errors |
| `mock_blind_adapter.py` | `RangeControllablePort`, `ListablePort` | Tracks position in memory |
| `mock_thermostat_adapter.py` | `TemperatureControllablePort`, `ListablePort` | Records calls; tracks temperature |
| `mock_token_validator.py` | `TokenValidatorPort` | Accepts any non-empty token |
| `mock_beacon_publisher.py` | `BeaconPublisherPort` | Records published beacons in memory |

Mock adapters are used by `build_test_container()` and in unit tests. They allow the full request path to be exercised without any hardware.

---

## The Lifecycle pattern

Adapters that hold persistent resources (a database connection, an HTTP session, a background daemon) implement the `Lifecycle` protocol defined in `composition.py`:

```python
@runtime_checkable
class Lifecycle(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

The FastAPI lifespan calls `start()` on all lifecycle adapters in registration order, and `stop()` in reverse order on shutdown:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    for adapter in container.lifecycle_adapters:
        await adapter.start()
    yield
    for adapter in reversed(container.lifecycle_adapters):
        await adapter.stop()
```

**Adapters with Lifecycle:** `SqliteUserStore` (opens/closes the SQLite connection), `FritzThermostatAdapter` (opens/closes the httpx session), `HomeKitBlindAdapter` (starts/stops the HomeKit daemon), and `HarmonyTvAdapter` — though the latter's `start()`/`stop()` are deliberate no-ops, since it opens a fresh `HarmonyService` connection per operation rather than holding one open.
