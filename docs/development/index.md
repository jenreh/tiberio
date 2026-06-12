# Testing & Contributing

## Daily development workflow

```bash
# Run all quality gates (do this before every push)
task lint && task format && task typecheck && task test
```

Individual commands:

| Command | What it does |
|---|---|
| `task test` | Run pytest with coverage report |
| `task lint` | `ruff check` — finds style and logic issues |
| `task format` | `ruff format` — auto-formats all Python files |
| `task typecheck` | `ty` — static type checking |

Coverage must stay at **≥ 80%**. The CI pipeline enforces this.

---

## Test architecture

Tests mirror the source tree:

```
tests/
├── adapters/
│   ├── test_jwt_service.py        # JwtService unit tests
│   └── test_sqlite_user_store.py  # SqliteUserStore integration tests
├── interfaces/
│   ├── alexa/
│   │   ├── test_directive_router.py     # AlexaDirectiveRouter unit tests
│   │   └── test_directive_auth.py       # JWT validation on /alexa/directive
│   └── oauth/
│       ├── test_authorize.py            # GET/POST /oauth/authorize
│       └── test_token.py               # POST /oauth/token (code + refresh)
└── commands/         # (unit tests for each command)
```

### Test containers

Every test that needs a server uses one of three pre-built containers from `composition.py`:

```python
# Fast: all mock adapters, no hardware needed
container = build_test_container(Path("config/devices.yaml"))

# OAuth tests: real JwtService + in-memory SQLite
user_store = SqliteUserStore(":memory:")
jwt_service = JwtService(test_settings)
container = build_oauth_test_container(devices_path, user_store, jwt_service, auth_codes)
```

### Example: testing a directive end-to-end

```python
@pytest.mark.asyncio
async def test_turn_on_channel(test_client: AsyncClient) -> None:
    body = {
        "directive": {
            "header": {
                "namespace": "Alexa.PowerController",
                "name": "TurnOn",
                "messageId": "test-1",
                "payloadVersion": "3",
                "correlationToken": "token-abc",
            },
            "endpoint": {
                "endpointId": "zdf",
                "scope": {"type": "BearerToken", "token": "valid-test-token"},
            },
            "payload": {},
        }
    }
    response = await test_client.post("/alexa/directive", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["event"]["header"]["namespace"] == "Alexa.Response"
```

The `test_client` fixture builds a test container and creates a FastAPI `TestClient` in one fixture.

---

## Code quality rules

These rules are enforced by pre-commit hooks and CI. Know them before you write code.

### No f-strings in logger calls

```python
# ✅ Correct — arguments are only formatted if the log level is active
log.info("Channel %s activated (activity=%s)", channel_id, activity)

# ❌ Wrong — always formats the string even when debug logging is off
log.info(f"Channel {channel_id} activated (activity={activity})")
```

### No `print` statements

Use `logging.getLogger(__name__)`. Default level is `DEBUG`; important events use `INFO`; issues use `WARNING`/`ERROR`.

### Type annotations everywhere

Every function signature needs type annotations:

```python
def find_device(self, endpoint_id: str) -> Device | None: ...
```

### Files ≤ 1000 lines

If a file grows beyond 1000 lines, split it. This keeps files focused and navigable.

---

## Adding a new TV channel

This is config-only — no code changes needed.

1. Open `config/devices.yaml`.
2. Add an entry under `tv.channels`:
   ```yaml
   - id: "kabel1"
     friendly_name: "Kabel 1"
     aliases: ["Kabel Eins"]
     channel_number: "7"
   ```
3. Restart the server.
4. Tell Alexa to discover devices: "Alexa, discover my devices."

Done. Alexa will find the new channel.

---

## Adding a new Alexa capability

This is what "Open for extension, closed for modification" looks like in practice. You add new code; you don't change existing code.

**Example:** adding `Alexa.ColorController` for smart lights.

### 1. Add domain models

```python
# domain/models.py — frozen Pydantic models (see the shared Device base)
class Light(Device):
    external_id: str  # adapter-specific reference (e.g. HomeKit entity_id)
```

### 2. Define a port

```python
# ports/light_port.py
class LightPort(Protocol):
    async def set_color(self, entity_id: str, hue: float, saturation: float) -> None: ...
    async def set_brightness(self, entity_id: str, percent: int) -> None: ...
```

### 3. Write the command

```python
# commands/lights/set_light_color.py
class SetLightColorCommand:
    def __init__(self, registry: DeviceRegistryPort, light: LightPort) -> None: ...
    async def execute(self, endpoint_id: str, hue: float, saturation: float) -> None: ...
```

### 4. Write the adapter

```python
# adapters/homekit_light_adapter.py
class HomeKitLightAdapter:
    async def set_color(self, entity_id: str, hue: float, saturation: float) -> None:
        async with HomeKitClient(load_config()) as client:
            await client.set_hue_saturation(entity_id, hue, saturation)
```

### 5. Write the Alexa handler

```python
# interfaces/alexa/handlers/color.py
class ColorHandler:
    def __init__(self, set_light_color: SetLightColorCommand) -> None: ...
    async def handle(self, req: AlexaDirectiveRequest) -> dict: ...
```

### 6. Register everything in composition.py

```python
# In build_container():
container.register(LightPort, HomeKitLightAdapter())

# In _wire_commands_and_router():
set_color_cmd = SetLightColorCommand(registry_port, light_port)
color_handler = ColorHandler(set_color_cmd)

# Add to AlexaDirectiveRouter dispatch table:
("Alexa.ColorController", "SetColor"): color_handler.handle,
```

### 7. Add to devices.yaml

```yaml
lights:
  - id: "wohnzimmer-licht"
    friendly_name: "Living Room Light"
    homekit_entity_id: "light.wohnzimmer"
```

That's it. All existing code is unchanged.

---

## Managing users (CLI)

The `tiberio-users` CLI manages the SQLite user database:

```bash
# Create a new user
uv run tiberio-users add alice

# List all users
uv run tiberio-users list

# Delete a user (and revoke their tokens)
uv run tiberio-users delete alice

# Change a password
uv run tiberio-users passwd alice
```

---

## Branching strategy

See `BRANCHING.md` for the full strategy. Short version:

- `main` — stable, always deployable
- `feat/…` — feature branches, PR to `main`
- `fix/…` — bug fix branches

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(alexa): add ColorController handler
fix(oauth): prevent timing attack in PKCE verification
refactor(commands): extract temperature conversion to value object
```
