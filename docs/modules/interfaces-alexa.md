# interfaces/alexa/

**Location:** `pantau/interfaces/alexa/`  
**Rule:** No business logic. Translate between Alexa's JSON format and the application's commands. Translate domain errors back to Alexa error codes.

The Alexa interface is the delivery layer for Smart Home directives. It knows everything about the Alexa Smart Home API v3 and nothing about how devices actually work.

## File map

```
interfaces/alexa/
├── directive_router.py    # FastAPI router: POST /alexa/directive
├── router.py              # AlexaDirectiveRouter (namespace,name) → handler
├── models.py              # Pydantic models for Alexa directive JSON
├── response_builder.py    # Helpers: build_response(), build_error_response()
└── handlers/
    ├── power.py           # Alexa.PowerController (TurnOn/TurnOff → TV channels)
    ├── speaker.py         # Alexa.Speaker (SetMute → TV audio)
    ├── thermostat.py      # Alexa.ThermostatController (SetTargetTemperature)
    ├── range.py           # Alexa.RangeController (SetRangeValue/AdjustRangeValue → blinds)
    └── discovery.py       # Alexa.Discovery (enumerate all devices)
```

---

## directive_router.py — The FastAPI endpoint

`POST /alexa/directive` is the single entry point for all Smart Home directives from Alexa.

```python
@alexa_router.post("/directive")
async def handle_directive(request: Request) -> JSONResponse:
    body = await request.json()

    # 1. Extract the bearer token from the Alexa payload
    token = _extract_bearer_token(body)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    # 2. Validate the JWT
    validator = request.app.state.container.get(TokenValidatorPort)
    try:
        validator.validate(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 3. Route to the correct capability handler
    router = request.app.state.container.get(AlexaDirectiveRouter)
    response = await router.route(body)
    return JSONResponse(response)
```

**Token location in the payload:**
- Most directives: `directive.endpoint.scope.token`
- Discovery directives: `directive.payload.scope.token` (no endpoint)

---

## router.py — AlexaDirectiveRouter

Maps `(namespace, name)` pairs to handler functions. This is the dispatch table for all supported Alexa capabilities:

```python
self._dispatch: dict[tuple[str, str], HandlerFn] = {
    ("Alexa.PowerController", "TurnOn"):             power.handle,
    ("Alexa.PowerController", "TurnOff"):            power.handle,
    ("Alexa.Speaker", "SetMute"):                    speaker.handle,
    ("Alexa.ThermostatController", "SetTargetTemperature"): thermostat.handle,
    ("Alexa.RangeController", "SetRangeValue"):      range_.handle,
    ("Alexa.RangeController", "AdjustRangeValue"):   range_.handle,
    ("Alexa.Discovery", "Discover"):                 discovery.handle,
}
```

If a directive arrives for an unsupported capability, the router returns an `INVALID_DIRECTIVE` error response — it does *not* raise an exception.

**Adding a new capability** requires only adding an entry to this dict and registering the handler in `composition.py`. No existing code changes.

---

## models.py — Pydantic models

Pydantic models parse and validate the raw Alexa directive JSON:

```python
class AlexaDirectiveRequest(BaseModel):
    directive: AlexaDirective

class AlexaDirective(BaseModel):
    header: DirectiveHeader
    endpoint: DirectiveEndpoint | None  # absent on Discovery
    payload: dict = {}

class DirectiveHeader(BaseModel):
    namespace: str          # e.g. "Alexa.PowerController"
    name: str               # e.g. "TurnOn"
    messageId: str
    correlationToken: str | None
    payloadVersion: str
    instance: str | None    # present on RangeController directives

class DirectiveEndpoint(BaseModel):
    endpointId: str
    scope: Scope | None
    cookie: dict = {}

class Scope(BaseModel):
    type: str
    token: str              # The JWT Bearer token
```

---

## response_builder.py — Response helpers

All Alexa responses follow the same structure. These helpers avoid repetition across handlers:

```python
def build_response(
    correlation_token: str | None,
    endpoint_id: str | None,
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
) -> dict:
    """Build a single context property."""

def build_discovery_response(endpoints: list[dict]) -> dict:
    """Build an Alexa.Discovery.Response."""
```

---

## Capability Handlers

### PowerHandler

**Handles:** `Alexa.PowerController` · `TurnOn` / `TurnOff`  
**Controls:** TV channels

`TurnOn` calls `ActivateChannelCommand.execute(endpoint_id)` and returns `powerState = ON`.  
`TurnOff` is a documented no-op for channel endpoints (a channel can't really be "turned off" independently of the TV).

### SpeakerHandler

**Handles:** `Alexa.Speaker` · `SetMute`  
**Controls:** TV audio

Extracts `mute: bool` from `directive.payload.mute` and calls `SetTvMuteCommand.execute(endpoint_id, mute)`.

### ThermostatHandler

**Handles:** `Alexa.ThermostatController` · `SetTargetTemperature`  
**Controls:** FRITZ!DECT thermostats

Extracts `targetSetpoint.value` and `targetSetpoint.scale` from the payload. Converts Fahrenheit to Celsius if needed. Calls `SetThermostatTemperatureCommand.execute(endpoint_id, celsius)`.

```python
target = req.directive.payload.get("targetSetpoint", {})
raw_value: float = float(target.get("value", 0.0))
scale: str = target.get("scale", "CELSIUS")
celsius = _to_celsius(raw_value, scale)
```

### RangeHandler

**Handles:** `Alexa.RangeController` · `SetRangeValue` / `AdjustRangeValue`  
**Controls:** Roller blinds  
**Instance identifier:** `"Blind.Position"`

`SetRangeValue`: extracts `rangeValue` (0–100), calls `SetBlindPositionCommand`.  
`AdjustRangeValue`: extracts `rangeValueDelta`, calls `AdjustBlindPositionCommand`.

The `instance: "Blind.Position"` in the Discovery response is what allows Alexa to say "open the blinds" (`AdjustRangeValue +100`) or "close the blinds" (`SetRangeValue 0`).

### DiscoveryHandler

**Handles:** `Alexa.Discovery` · `Discover`  
**Returns:** All configured devices as Alexa endpoints

Calls `DiscoverDevicesCommand.execute()` and maps each `DiscoveredDevice` to the correct Alexa capability descriptor:

| Capability | Alexa interface | Display category |
|---|---|---|
| `power` | `Alexa.PowerController` | `TV` |
| `speaker` | `Alexa.Speaker` | `SPEAKER` |
| `thermostat` | `Alexa.ThermostatController` | `THERMOSTAT` |
| `range` | `Alexa.RangeController` (instance: `Blind.Position`) | `INTERIOR_BLIND` |

The Discovery response includes **semantic action mappings** for blinds, so that Alexa understands "open/close/raise/lower" in addition to explicit percentages:

| Semantic action | Maps to |
|---|---|
| `Alexa.Actions.Open` | `SetRangeValue(100)` |
| `Alexa.Actions.Close` | `SetRangeValue(0)` |
| `Alexa.Actions.Raise` | `AdjustRangeValue(+10)` |
| `Alexa.Actions.Lower` | `AdjustRangeValue(-10)` |

---

## Error mapping

Every handler wraps its command call in a try/except and maps exceptions to Alexa error types:

```python
except ValueError as exc:
    return build_error_response(token, endpoint_id, "VALUE_OUT_OF_RANGE", str(exc))
except DeviceNotFoundError as exc:
    return build_error_response(token, endpoint_id, "NO_SUCH_ENDPOINT", str(exc))
except DeviceUnavailableError as exc:
    return build_error_response(token, endpoint_id, "ENDPOINT_UNREACHABLE", str(exc))
except Exception as exc:
    log.exception("Unexpected error for endpoint=%s", endpoint_id)
    return build_error_response(token, endpoint_id, "INTERNAL_ERROR", str(exc))
```

Errors are never raised — they are always returned as valid Alexa error responses. This ensures Alexa always gets a well-formed response and can give the user a meaningful message.
