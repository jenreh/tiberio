# adapters/

**Location:** `pantau/adapters/`  
**Rule:** Each adapter wraps exactly one external library or technology. It translates library-specific exceptions into domain errors.

Adapters are the bridge between your clean business logic and the messy real world. They speak "harmonyhub" or "FRITZ!Box" externally and "domain model" internally. If the Harmony library changes its API, you change exactly one file: `harmony_tv_adapter.py`.

---

## Device Adapters

### HarmonyTvAdapter

**File:** `adapters/harmony_tv_adapter.py`  
**Library:** `harmonyhub-py`  
**Protocol:** WebSocket (persistent connection)

Controls the Logitech Harmony Hub. Holds a single `HarmonyHubClient` with a persistent WebSocket connection, which is opened/closed through the `Lifecycle` protocol (FastAPI lifespan).

```python
class HarmonyTvAdapter:
    def __init__(self, host: str) -> None:
        self._hub = HarmonyHubClient(host, connection_mode="persistent")

    async def start(self) -> None:  # called at server startup
        await self._hub.connect()

    async def stop(self) -> None:   # called at server shutdown
        await self._hub.close()

    async def ensure_activity(self, activity_name: str) -> None:
        try:
            status = await self._hub.get_current_activity()
            if status.activity_label != activity_name:
                await self._hub.start_activity(activity_name)
        except (HubUnavailableError, ProtocolError) as exc:
            raise DeviceUnavailableError(str(exc)) from exc
```

**Key behaviors:**
- `ensure_activity` is idempotent — if the activity is already running, it skips `start_activity`.
- All Hub exceptions are caught and re-raised as `DeviceUnavailableError`.

---

### HomeKitBlindAdapter

**File:** `adapters/homekit_blind_adapter.py`  
**Library:** `homekit-py`  
**Protocol:** Apple HomeKit over LAN

Controls roller blinds and window coverings connected via HomeKit.

```python
class HomeKitBlindAdapter:
    async def set_position(self, homekit_entity_id: str, percent: int) -> None:
        async with HomeKitClient(load_config()) as client:
            await client.set_position(homekit_entity_id, percent)

    async def get_position(self, homekit_entity_id: str) -> int:
        async with HomeKitClient(load_config()) as client:
            state = await client.get_state(homekit_entity_id)
            return state.position
```

---

### FritzThermostatAdapter

**File:** `adapters/fritz_thermostat_adapter.py`  
**Library:** `fritzctl-py`  
**Protocol:** FRITZ!Box HTTP API

Controls FRITZ!DECT smart thermostats via the AVM Home Automation API.

```python
class FritzThermostatAdapter:
    async def set_temperature(self, fritz_name: str, celsius: float) -> None:
        async with fritz_client_context() as client:
            devices = await client.list_devices()
            ain = next(d.id for d in devices if d.name == fritz_name)
            await client.set_temperature(ain, celsius)
```

The adapter resolves the human-readable device name (`fritz_name` from `devices.yaml`) to the internal AIN (Actor Identification Number) by listing all devices. The fritzctl library handles the safety engine (rate limiting, delta limits, cooldown).

---

## Auth Adapters

### JwtService

**File:** `adapters/jwt_service.py`  
**Library:** `python-jose`  
**Dual role:** Implements `TokenValidatorPort` (validates tokens) and is used directly by the OAuth router (issues tokens)

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
        payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        return TokenClaims(user_id=payload["sub"], scope=payload["scope"])
```

**Note:** Refresh tokens are *not* JWTs — they are random opaque strings stored in SQLite. Only access tokens are JWTs.

---

### SqliteUserStore

**File:** `adapters/sqlite_user_store.py`  
**Library:** `aiosqlite`  
**Implements:** `UserStorePort`, `Lifecycle`

Async SQLite store for users and refresh tokens. Creates its schema on `start()`.

Tables:
- `users (id TEXT PK, username TEXT UNIQUE, password_hash TEXT)`
- `refresh_tokens (token TEXT PK, user_id TEXT, expires_at TEXT)`

**Lifecycle:** The connection is opened in `start()` and closed in `stop()`, managed through the FastAPI lifespan context.

**Admin operations** (beyond `UserStorePort`) used by the CLI:
- `list_users()` — list all accounts
- `delete_user(username)` — remove user and their tokens
- `update_password(username, new_hash)` — rotate a password

---

### AuthCodeStore

**File:** `adapters/auth_code_store.py`  
**Storage:** In-memory (dict)

An in-memory store for OAuth2 authorization codes. Codes are short-lived (a few minutes) and single-use, so SQLite persistence is not needed — if the server restarts during Account Linking, the user simply re-authenticates.

```python
class AuthCodeStore:
    async def save(self, user_id, client_id, redirect_uri,
                   code_challenge, code_challenge_method) -> str:
        """Generate a random code and store the entry. Returns the code."""

    async def redeem(self, code: str) -> AuthCodeEntry | None:
        """Return and atomically delete the entry. Returns None if not found."""
```

---

### YamlDeviceRegistry

**File:** `adapters/yaml_device_registry.py`  
**Implements:** `DeviceRegistryPort`

Loads `config/devices.yaml` at startup using Pydantic for validation. Builds the `DeviceRegistry` domain model. Supports fast O(1) lookups by building index dicts `{endpoint_id → device}` at load time.

---

## Mock Adapters (test doubles)

| File | Implements | Behavior |
|---|---|---|
| `mock_tv_adapter.py` | `TvPort` | Records calls; never errors |
| `mock_blind_adapter.py` | `BlindPort` | Tracks position in memory |
| `mock_thermostat_adapter.py` | `ThermostatPort` | Records calls |
| `mock_token_validator.py` | `TokenValidatorPort` | Accepts any non-empty token |

Mock adapters are used by `build_test_container()` and in unit tests. They allow the full request path to be exercised without any hardware.

---

## The Lifecycle pattern

Adapters that hold persistent connections (database connection, WebSocket) implement the `Lifecycle` protocol defined in `composition.py`:

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

**Adapters with Lifecycle:** `HarmonyTvAdapter`, `SqliteUserStore`
