# interfaces/alexa/

**Location:** `tiberio/interfaces/alexa/`
**Rule:** No business logic. Translate between Alexa's JSON format and the application's commands. Translate domain errors back to Alexa error codes.

The Alexa interface is the delivery layer for Smart Home directives. It knows everything about the Alexa Smart Home API v3 and nothing about how devices actually work.

## File map

```
interfaces/alexa/
├── directive_router.py    # FastAPI router: POST /alexa/directive (token + HMAC)
├── router.py              # AlexaDirectiveRouter (namespace,name) → handler instance
├── models.py              # Pydantic models for Alexa directive JSON
├── response_builder.py    # Helpers: build_response(), build_error_response()
└── handlers/
    ├── _base.py           # AlexaHandler template-method base + payload helpers + error mapping
    ├── power.py           # PowerHandler — Alexa.PowerController (TurnOn/TurnOff → TV channels)
    ├── speaker.py         # SpeakerHandler — Alexa.Speaker (SetMute/SetVolume/AdjustVolume)
    ├── thermostat.py      # ThermostatHandler — Alexa.ThermostatController (Set/AdjustTargetTemperature)
    ├── range.py           # RangeHandler — Alexa.RangeController (SetRangeValue/AdjustRangeValue → blinds)
    └── discovery.py       # DiscoveryHandler — Alexa.Discovery (enumerate all devices)
```

Concrete capability handlers subclass the `AlexaHandler` template-method base
in `handlers/_base.py`. Each handler is a **class** constructed with the
application commands it needs (constructor injection); it implements only
`_execute()`. The base class owns `handle()`, which extracts the directive
context, runs `_execute()`, and maps domain errors to Alexa error types in one
central place. `DiscoveryHandler` is the one exception — it is a plain class
with its own `handle()` because Discovery returns an endpoint list rather than
per-endpoint properties.

---

## directive_router.py — The FastAPI endpoint

`POST /alexa/directive` is the single entry point for all Smart Home directives from Alexa.

```python
@alexa_router.post("/directive")
async def handle_directive(request: Request) -> JSONResponse:
    # Body is read raw so the exact bytes can be HMAC-verified.
    raw_body = await request.body()

    settings = request.app.state.settings

    # 1. Replay-protected HMAC verification (only when a shared secret is set)
    shared_secret = settings.shared_secret.get_secret_value()
    if shared_secret:
        _require_valid_hmac(
            request, raw_body, shared_secret, settings.hmac_tolerance_seconds
        )

    # 2. Parse JSON (HTTP 400 on malformed body)
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    # 3. Extract the bearer token from the Alexa payload
    token = _extract_bearer_token(body)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    # 4. Validate the JWT and enforce the required scope
    validator = request.app.state.container.get(TokenValidatorPort)
    try:
        claims = validator.validate(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    if claims.scope != "alexa":
        raise HTTPException(status_code=403, detail="Insufficient scope")

    # 5. Route to the correct capability handler
    router = request.app.state.container.get(AlexaDirectiveRouter)
    response = await router.route(body)
    return JSONResponse(response)
```

**Token location in the payload:**
- Most directives: `directive.endpoint.scope.token`
- Discovery directives: `directive.payload.scope.token` (no endpoint)

The validated `claims` must carry `scope == "alexa"`; otherwise the request is
rejected with HTTP 403 (`Insufficient scope`).

### HMAC shared-secret replay protection

When `settings.shared_secret` is configured, every directive must additionally
carry a timestamped HMAC-SHA256 signature. This protects the AWS→home traffic
against replay and tampering even after the bearer token has been verified.

The signature is computed over `f"{timestamp}." + raw_body` with the shared
secret as the key, and is transported in two headers:

| Header | Meaning |
| --- | --- |
| `X-Tiberio-Timestamp` | Unix seconds when the request was signed |
| `X-Tiberio-Signature` | `HMAC-SHA256(secret, f"{timestamp}." + raw_body)` (hex) |

`_require_valid_hmac` rejects the request with HTTP 401 if either header is
missing, the timestamp is non-numeric, the timestamp is outside the
`settings.hmac_tolerance_seconds` window (replay defense), or the signature does
not match (compared with `hmac.compare_digest`).

```python
expected = hmac.new(
    secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
).hexdigest()
if not hmac.compare_digest(expected, signature):
    raise HTTPException(status_code=401, detail="Invalid HMAC signature")
```

---

## router.py — AlexaDirectiveRouter

`AlexaDirectiveRouter` is constructed with the concrete handler **instances**
(`power`, `speaker`, `thermostat`, `range_`, `discovery`) and builds its
dispatch table from their bound `handle` methods. This maps each
`(namespace, name)` pair to the correct handler for all supported Alexa
capabilities:

```python
def __init__(
    self,
    power: PowerHandler,
    speaker: SpeakerHandler,
    thermostat: ThermostatHandler,
    range_: RangeHandler,
    discovery: DiscoveryHandler,
) -> None:
    self._dispatch: dict[tuple[str, str], HandlerFn] = {
        ("Alexa.PowerController", "TurnOn"): power.handle,
        ("Alexa.PowerController", "TurnOff"): power.handle,
        ("Alexa.Speaker", "SetMute"): speaker.handle,
        ("Alexa.Speaker", "SetVolume"): speaker.handle,
        ("Alexa.Speaker", "AdjustVolume"): speaker.handle,
        ("Alexa.ThermostatController", "SetTargetTemperature"): thermostat.handle,
        ("Alexa.ThermostatController", "AdjustTargetTemperature"): thermostat.handle,
        ("Alexa.RangeController", "SetRangeValue"): range_.handle,
        ("Alexa.RangeController", "AdjustRangeValue"): range_.handle,
        ("Alexa.Discovery", "Discover"): discovery.handle,
    }
```

If a directive arrives for an unsupported capability, the router returns an `INVALID_DIRECTIVE` error response — it does *not* raise an exception. The same happens when the body fails to parse into `AlexaDirectiveRequest`.

**Adding a new capability** means: create a new `AlexaHandler` subclass that
implements `_execute()`, wire its application command dependencies in the
composition root, pass the new handler instance into `AlexaDirectiveRouter`, and
register its `(namespace, name)` entries in this dispatch table.

---

## models.py — Pydantic models

Pydantic models parse and validate the raw Alexa directive JSON:

```python
class Scope(BaseModel):
    type: str
    token: str

class DirectiveEndpoint(BaseModel):
    endpointId: str
    scope: Scope | None = None
    cookie: dict = {}

class DirectiveHeader(BaseModel):
    namespace: str                       # e.g. "Alexa.PowerController"
    name: str                            # e.g. "TurnOn"
    messageId: str
    correlationToken: str | None = None
    payloadVersion: str
    instance: str | None = None          # present on Alexa.RangeController directives

class AlexaDirective(BaseModel):
    header: DirectiveHeader
    endpoint: DirectiveEndpoint | None = None  # absent on Discover directive
    payload: dict = {}

class AlexaDirectiveRequest(BaseModel):
    directive: AlexaDirective
```

---

## response_builder.py — Response helpers

All Alexa responses follow the same structure. These helpers avoid repetition across handlers:

```python
def build_response(
    correlation_token: str | None,
    endpoint_id: str,
    bearer_token: str | None,
    properties: list[dict],
) -> dict:
    """Build a successful Alexa.Response."""

def build_error_response(
    correlation_token: str | None,
    endpoint_id: str | None,
    error_type: str,
    message: str,
) -> dict:
    """Build an Alexa ErrorResponse."""

def build_property(
    namespace: str,
    name: str,
    value: object,
    instance: str | None = None,
    uncertainty_ms: int = 500,
) -> dict:
    """Build a single context property.

    Each property carries a `timeOfSample` (ISO-8601 UTC) and an
    `uncertaintyInMilliseconds` field (from `uncertainty_ms`); `instance` is
    added only when provided.
    """

def build_discovery_response(endpoints: list[dict]) -> dict:
    """Build an Alexa.Discovery.Response."""
```

---

## Capability Handlers

Each handler is constructed with the application commands it depends on and
implements only `_execute(ctx)`, which receives a `DirectiveContext`
(name, `endpoint_id`, `correlation_token`, `bearer_token`, `payload`) and returns
the list of Alexa context properties. Payload extraction uses the shared
`require_field` / `require_int` helpers, which raise `InvalidPayloadError` on a
missing or wrongly-typed field.

### PowerHandler

**Handles:** `Alexa.PowerController` · `TurnOn` / `TurnOff`
**Controls:** TV channels
**Commands:** `TurnOnCommand`, `TurnOffCommand`

`TurnOn` calls `self._turn_on.execute(endpoint_id)` and returns `powerState = ON`.
`TurnOff` calls `self._turn_off.execute(endpoint_id)` and returns `powerState = OFF`.

### SpeakerHandler

**Handles:** `Alexa.Speaker` · `SetMute` / `SetVolume` / `AdjustVolume`
**Controls:** TV audio
**Commands:** `SetMuteCommand`, `SetVolumeCommand`, `AdjustVolumeCommand`, `GetSpeakerStateCommand`

- `SetMute`: extracts `mute: bool` and calls `self._set_mute.execute(endpoint_id, mute=mute)`.
- `SetVolume`: extracts `volume: int` and calls `self._set_volume.execute(endpoint_id, level=volume)`.
- `AdjustVolume`: extracts `volume: int` (the delta) and calls `self._adjust_volume.execute(endpoint_id, delta=delta)`.

After applying the change the handler reads the current state back via
`GetSpeakerStateCommand` and returns **both** the `muted` and `volume`
properties.

### ThermostatHandler

**Handles:** `Alexa.ThermostatController` · `SetTargetTemperature` / `AdjustTargetTemperature`
**Controls:** FRITZ!DECT thermostats
**Commands:** `SetTemperatureCommand`, `AdjustTemperatureCommand`

Temperature payloads are extracted with the `_temperature_payload` helper, which
validates the `{value, scale}` shape via `require_field`. Scales `CELSIUS`,
`FAHRENHEIT`, and `KELVIN` are supported:

- `SetTargetTemperature`: reads `targetSetpoint`, converts the absolute value with `_to_celsius`, and calls `self._set_temperature.execute(endpoint_id, celsius=...)`.
- `AdjustTargetTemperature`: reads `targetSetpointDelta`, converts the delta with `_delta_to_celsius` (factor only, no offset), and calls `self._adjust_temperature.execute(endpoint_id, delta_celsius=...)`.

Both commands return the **applied** setpoint, which is reported back as the
`targetSetpoint` property in `CELSIUS`:

```python
value, scale = _temperature_payload(ctx.payload, "targetSetpoint")
applied = await self._set_temperature.execute(
    ctx.endpoint_id, celsius=_to_celsius(value, scale)
)
```

### RangeHandler

**Handles:** `Alexa.RangeController` · `SetRangeValue` / `AdjustRangeValue`
**Controls:** Roller blinds
**Instance identifier:** `BLIND_INSTANCE = "Blind.Position"`
**Commands:** `SetRangeCommand`, `AdjustRangeCommand`

- `SetRangeValue`: extracts `rangeValue` (0–100) and calls `self._set_range.execute(endpoint_id, percent=range_value)`.
- `AdjustRangeValue`: extracts `rangeValueDelta` and calls `self._adjust_range.execute(endpoint_id, delta=delta)`, which returns the resulting value reported back in the `rangeValue` property.

The `instance: "Blind.Position"` in the Discovery response is what allows Alexa to say "open the blinds" (`SetRangeValue 100`) or "close the blinds" (`SetRangeValue 0`).

### DiscoveryHandler

**Handles:** `Alexa.Discovery` · `Discover`
**Returns:** All configured devices as Alexa endpoints
**Command:** `DiscoverDevicesCommand`

Calls `DiscoverDevicesCommand.execute()` and maps each `DiscoveredDevice` to an
Alexa endpoint via `_CAPABILITY_BY_KIND`, keyed on `device.capability`. Each
endpoint sets `manufacturerName` to the literal `"tiberio"`, carries a German
`description`, and always includes the base `Alexa` interface capability
(`_ALEXA_BASE`) alongside its capability-specific descriptor. Devices with an
unknown capability are skipped with a warning rather than raising an error.

| `device.capability` | Alexa interface | Display category | Description |
| --- | --- | --- | --- |
| `power` | `Alexa.PowerController` | `TV` | `TV-Kanal` |
| `speaker` | `Alexa.Speaker` | `SPEAKER` | `TV-Lautsprecher` |
| `thermostat` | `Alexa.ThermostatController` | `THERMOSTAT` | `Heizungsthermostat` |
| `range` | `Alexa.RangeController` (instance: `Blind.Position`) | `INTERIOR_BLIND` | `Rollo / Jalousie` |

The blind (`range`) capability descriptor carries extra Alexa metadata so that
voice commands work in addition to explicit percentages:

- **`semantics.actionMappings`** — map spoken actions to directives.
- **`semantics.stateMappings`** — `Alexa.States.Closed` → value `0`; `Alexa.States.Open` → range `1..100`.
- **`capabilityResources.friendlyNames`** — asset `Alexa.Setting.Opening`.
- **`configuration`** — `supportedRange` `0..100` (precision `1`) and `unitOfMeasure` `Alexa.Unit.Percent`.

| Semantic action | Maps to | Payload |
| --- | --- | --- |
| `Alexa.Actions.Open` | `SetRangeValue` | `{"rangeValue": 100}` |
| `Alexa.Actions.Close` | `SetRangeValue` | `{"rangeValue": 0}` |
| `Alexa.Actions.Raise` | `AdjustRangeValue` | `{"rangeValueDelta": 10, "rangeValueDeltaDefault": false}` |
| `Alexa.Actions.Lower` | `AdjustRangeValue` | `{"rangeValueDelta": -10, "rangeValueDeltaDefault": false}` |

---

## Error mapping

Error handling is centralised in `AlexaHandler.handle` (`handlers/_base.py`), not
duplicated per handler. After running `_execute()`, the base class catches domain
errors and maps them to Alexa error types, building the response with the
directive's `correlation_token` and `endpoint_id`:

```python
try:
    properties = await self._execute(ctx)
    return build_response(
        ctx.correlation_token, ctx.endpoint_id, ctx.bearer_token, properties
    )
except InvalidPayloadError as exc:
    return self._error(ctx, "INVALID_VALUE", str(exc))
except ValueError as exc:
    return self._error(ctx, "VALUE_OUT_OF_RANGE", str(exc))
except DeviceCapabilityError as exc:
    return self._error(ctx, "INVALID_VALUE", str(exc))
except DeviceNotFoundError as exc:
    return self._error(ctx, "NO_SUCH_ENDPOINT", str(exc))
except DeviceUnavailableError as exc:
    return self._error(ctx, "ENDPOINT_UNREACHABLE", str(exc))
except Exception:
    log.exception("%s: unexpected error for endpoint=%s", type(self).__name__, ctx.endpoint_id)
    return self._error(ctx, "INTERNAL_ERROR", "Internal error while handling the directive")
```

| Exception | Alexa error type |
| --- | --- |
| `InvalidPayloadError` | `INVALID_VALUE` |
| `ValueError` | `VALUE_OUT_OF_RANGE` |
| `DeviceCapabilityError` | `INVALID_VALUE` |
| `DeviceNotFoundError` | `NO_SUCH_ENDPOINT` |
| `DeviceUnavailableError` | `ENDPOINT_UNREACHABLE` |
| any other `Exception` | `INTERNAL_ERROR` (fixed generic message) |

Unexpected errors return a fixed generic message (`"Internal error while handling
the directive"`) rather than leaking `str(exc)`. Errors are never raised out of a
handler — they are always returned as valid Alexa error responses, so Alexa always
gets a well-formed response and can give the user a meaningful message.
