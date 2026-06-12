# Message Flows

This page traces the two critical request paths through the system step by step. Read these carefully — they show exactly what every module does and why it exists.

## Flow A — Account Linking (OAuth2)

Account Linking happens once, when a user enables the Alexa Skill for the first time. The goal: exchange a username/password for a pair of JWT tokens that Alexa will attach to every future directive.

::: info Phase status
The OAuth2 server on the home server (right half of the diagram) is **fully implemented** (Phase 4). The API Gateway proxy (left half) is **planned** (Phase 5). During development you can test OAuth directly at `http://localhost:8080/oauth/...`.
:::

```mermaid
sequenceDiagram
    actor User as 👤 User
    participant App as Alexa App
    participant Alexa as Alexa Cloud
    participant APIGW as API Gateway<br/>(OAuth Proxy — Phase 5)
    participant HS as Home Server<br/>/oauth
    participant DB as SQLite<br/>(users + tokens)

    User->>App: Enable Tiberio skill
    App->>Alexa: Initiate Account Linking
    Alexa->>APIGW: GET /oauth/authorize?<br/>client_id=&redirect_uri=&<br/>code_challenge=&state=
    APIGW->>HS: Forward (S3 beacon lookup)
    HS-->>User: Render HTML login form

    User->>HS: POST username + password
    HS->>DB: get_user_by_username(username)
    DB-->>HS: UserRecord {id, password_hash}
    HS->>HS: bcrypt.checkpw(password, hash)

    alt Invalid credentials
        HS-->>User: Re-render form with error message
    else Valid credentials
        HS->>DB: auth_codes.save(user_id, client_id,<br/>redirect_uri, code_challenge, method)
        DB-->>HS: code (random hex)
        HS-->>Alexa: 302 redirect → ?code=…&state=…
    end

    Alexa->>APIGW: POST /oauth/token<br/>{grant_type=authorization_code,<br/>code, code_verifier, redirect_uri}
    APIGW->>HS: Forward
    HS->>DB: auth_codes.redeem(code)
    DB-->>HS: AuthCodeEntry {code_challenge, method, …}
    HS->>HS: Verify PKCE:<br/>SHA-256(code_verifier) == code_challenge
    HS->>HS: jwt.encode(sub=user_id, exp=+60min)
    HS->>HS: secrets.token_urlsafe(32) → refresh_token
    HS->>DB: save_refresh_token(token, user_id, expires_at)
    HS-->>Alexa: {access_token, token_type=Bearer,<br/>expires_in, refresh_token}

    Note over Alexa,HS: Account Linking complete.<br/>Alexa now has a valid Bearer token.

    Alexa->>HS: POST /alexa/directive<br/>Alexa.Discovery + Bearer token
    HS-->>Alexa: Discovery response (all devices)
    Alexa-->>User: "I found 9 new devices"
```

### Key security mechanisms

| Mechanism | What it does |
|---|---|
| **PKCE (S256)** | Alexa sends a `code_challenge` (SHA-256 hash of `code_verifier`) during authorize. At token exchange it sends the raw `code_verifier`. The server recomputes the hash and compares — ensures only the original caller can exchange the code. |
| **Auth code is single-use** | `auth_codes.redeem()` atomically deletes the entry. A replayed code returns `invalid_grant`. |
| **Refresh token rotation** | On every `/oauth/token?grant_type=refresh_token`, the old token is revoked before the new pair is issued. |
| **bcrypt** | Passwords are never stored in plain text. Only the bcrypt hash is stored in SQLite. |
| **JWT expiry** | Access tokens expire after 60 minutes (configurable). Alexa uses the refresh token to get new ones automatically. |

---

## Flow B — Voice Command

This is the hot path — everything that happens between "Alexa, switch to ZDF" and the TV changing channel.

::: info Phase status
The home server portion (FastAPI → Router → Handler → Command → Adapter → Device) is **fully implemented** (Phase 3 + 2). The Lambda proxy + S3 beacon (the top section) is **planned** (Phase 5). During development, POST directly to `http://localhost:8080/alexa/directive`.
:::

```mermaid
sequenceDiagram
    actor User as 👤 User
    participant Alexa as Alexa Cloud
    participant Lambda as Lambda<br/>Directive Proxy (Phase 5)
    participant S3 as S3 Beacon<br/>(Phase 5)
    participant FastAPI as FastAPI<br/>/alexa/directive
    participant Router as AlexaDirectiveRouter
    participant Handler as PowerHandler
    participant Cmd as ActivateChannelCommand
    participant RegPort as DeviceRegistryPort
    participant TvPort as TvPort
    participant Adapter as HarmonyTvAdapter
    participant Hub as Harmony Hub (LAN)

    User->>Alexa: "Alexa, switch on ZDF"
    Alexa->>Lambda: POST Smart Home directive<br/>{namespace: Alexa.PowerController,<br/>name: TurnOn, endpoint: zdf}<br/>+ Bearer token
    Lambda->>S3: GET endpoint.json (If-None-Match: ETag)
    S3-->>Lambda: 200 {base_url} or 304 Not Modified
    Lambda->>FastAPI: POST /alexa/directive<br/>+ X-Shared-Secret header
    Note over FastAPI: Validate Shared-Secret HMAC

    FastAPI->>FastAPI: Extract Bearer token from<br/>directive.endpoint.scope.token
    FastAPI->>FastAPI: JwtService.validate(token)<br/>→ TokenClaims{user_id, scope}

    alt Token invalid or expired
        FastAPI-->>Lambda: HTTP 401 Unauthorized
        Lambda-->>Alexa: Error response
        Alexa-->>User: "Sorry, there was a problem"
    end

    FastAPI->>Router: route(body)
    Router->>Router: AlexaDirectiveRequest.parse(body)
    Router->>Router: lookup (Alexa.PowerController, TurnOn)<br/>→ PowerHandler.handle

    Router->>Handler: handle(AlexaDirectiveRequest)
    Handler->>Cmd: ActivateChannelCommand.execute("zdf")
    Cmd->>RegPort: find_channel("zdf")
    RegPort-->>Cmd: ChannelDevice{channel_number="2",<br/>friendly_name="ZDF"}
    Cmd->>TvPort: ensure_activity("Fernseher")
    TvPort->>Adapter: HarmonyTvAdapter.ensure_activity(...)
    Adapter->>Hub: WebSocket: get_current_activity()
    Hub-->>Adapter: ActivityStatus{label="Fernseher"}
    Note over Adapter: Already active — skip start_activity
    Cmd->>TvPort: set_channel("2")
    TvPort->>Adapter: HarmonyTvAdapter.set_channel("2")
    Adapter->>Hub: WebSocket: set_channel("2")
    Hub-->>Adapter: ChannelResult{success=True}
    Adapter-->>Cmd: (returns)

    Cmd-->>Handler: (returns)
    Handler->>Handler: build_response(correlationToken,<br/>endpointId, bearer, properties)
    Handler-->>Router: Alexa response dict
    Router-->>FastAPI: response dict
    FastAPI-->>Lambda: JSONResponse 200
    Lambda-->>Alexa: Alexa Smart Home response
    Alexa-->>User: "OK" ✅
```

### What each layer does in this flow

| Layer | Responsibility in this flow |
|---|---|
| **Lambda** | Looks up current home server URL; adds Shared-Secret header; forwards raw directive |
| **FastAPI route** | Extracts and validates the Bearer JWT; rejects with 401 if invalid |
| **AlexaDirectiveRouter** | Parses the Alexa JSON into a typed model; dispatches to the correct handler by `(namespace, name)` |
| **PowerHandler** | Extracts endpoint ID and correlation token; calls the command; builds the Alexa response |
| **ActivateChannelCommand** | Orchestrates the two-step TV activation (ensure activity → set channel); raises `DeviceNotFoundError` or `DeviceUnavailableError` |
| **DeviceRegistryPort** | Looks up the `ChannelDevice` by ID; returns `None` if not found |
| **TvPort / HarmonyTvAdapter** | WebSocket calls to the Harmony Hub; maps Hub exceptions to `DeviceUnavailableError` |

### Error handling

Every handler wraps the command call in a try/except block and maps domain errors to Alexa error responses:

| Exception | Alexa error type | Alexa behavior |
|---|---|---|
| `DeviceNotFoundError` | `NO_SUCH_ENDPOINT` | "That device is not available" |
| `DeviceUnavailableError` | `ENDPOINT_UNREACHABLE` | "That device is not responding" |
| `ValueError` | `VALUE_OUT_OF_RANGE` | "That value is out of range" |
| Any other exception | `INTERNAL_ERROR` | "Sorry, something went wrong" |

---

## Flow C — Token Refresh

Alexa automatically refreshes the access token when it expires (every 60 minutes). The refresh token rotates on each use.

```mermaid
sequenceDiagram
    participant Alexa as Alexa Cloud
    participant APIGW as API Gateway (Phase 5)
    participant HS as Home Server /oauth/token
    participant DB as SQLite

    Alexa->>APIGW: POST /oauth/token<br/>{grant_type=refresh_token, refresh_token=…}
    APIGW->>HS: Forward
    HS->>DB: get_refresh_token_user_id(token)
    DB-->>HS: user_id (or None if expired/invalid)

    alt Token invalid or expired
        HS-->>Alexa: {error: invalid_grant}
        Note over Alexa: User must re-link account
    else Token valid
        HS->>DB: revoke_refresh_token(old_token)
        HS->>HS: Issue new JWT access token
        HS->>HS: Generate new random refresh token
        HS->>DB: save_refresh_token(new_token, user_id, expires_at)
        HS-->>Alexa: {access_token, expires_in, refresh_token}
    end
```

Refresh token rotation means a stolen refresh token can only be used once — the legitimate user's next refresh will fail, alerting them to the compromise.
