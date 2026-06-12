# Configuration Reference

Tiberio is configured through two sources:

1. **`config/devices.yaml`** — the device registry (which physical devices exist and how to reach them)
2. **Environment variables / `.env` file** — secrets, ports, paths

## devices.yaml

Every device that Alexa can control must be declared here. Adding a new channel, blind, or thermostat requires **only a YAML change** — no code.

```yaml
tv:
  harmony_host: "192.168.178.50"   # LAN IP of your Logitech Harmony Hub
  watch_activity: "Fernseher"      # Activity name in the Harmony app that turns on TV

  audio:
    id: "tv-audio"                 # Alexa endpoint ID for mute/unmute
    friendly_name: "TV Audio"      # How Alexa refers to it: "mute TV Audio"

  channels:
    - id: "ard"                    # Alexa endpoint ID — must be unique, URL-safe
      friendly_name: "ARD"         # Alexa-visible name: "switch on ARD"
      aliases: ["ARD", "Das Erste"] # Alternative names Alexa may recognize
      channel_number: "1"          # Channel number sent to the Harmony Hub

    - id: "zdf"
      friendly_name: "ZDF"
      aliases: ["ZDF", "Zweites"]
      channel_number: "2"

blinds:
  - id: "kueche-rollo"
    friendly_name: "Kitchen Blind"
    aliases: ["Kitchen", "Kitchen Roller"]
    homekit_entity_id: "cover.kueche"  # Entity ID in your HomeKit setup
    invert: false                       # true = motor is inverted (0 = open, 100 = closed)

thermostats:
  - id: "wohnzimmer-heizung"
    friendly_name: "Living Room Heating"
    aliases: ["Living Room", "Living Room Heating"]
    fritz_name: "Wohnzimmer"       # Device name as it appears on the FRITZ!Box
    min_celsius: 16.0              # Lower guard: Alexa won't set below this
    max_celsius: 24.0              # Upper guard: Alexa won't set above this
```

### Field reference

#### TV

| Field | Type | Description |
| --- | --- | --- |
| `harmony_host` | string | LAN IP address of the Harmony Hub |
| `watch_activity` | string | Exact Harmony activity name that enables TV viewing |
| `audio.id` | string | Alexa endpoint ID for the Speaker capability (mute/unmute) |
| `audio.friendly_name` | string | Alexa-visible label for the audio device |

#### Channels

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique endpoint ID (used internally and by Alexa) |
| `friendly_name` | string | Name Alexa uses to identify this endpoint |
| `aliases` | string[] | Optional alternative names for discovery |
| `channel_number` | string | Channel digits sent to the Harmony Hub |

#### Blinds

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique endpoint ID |
| `friendly_name` | string | Alexa-visible label |
| `homekit_entity_id` | string | Entity ID in the HomeKit library's `entities.toml` |
| `invert` | bool | `true` if your motor uses reversed position values |
| `aliases` | string[] | Optional alternative names |

#### Thermostats

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique endpoint ID |
| `friendly_name` | string | Alexa-visible label |
| `fritz_name` | string | Device name as shown in the FRITZ!Box web UI |
| `min_celsius` | float | Minimum temperature Alexa is allowed to set (default: 8.0) |
| `max_celsius` | float | Maximum temperature Alexa is allowed to set (default: 28.0) |
| `aliases` | string[] | Optional alternative names |

---

## Environment Variables

Settings are loaded from environment variables or a `.env` file in the project root (`tiberio/config/settings.py → Settings`).

All variables use the `TIBERIO_` prefix. A template with every variable is provided in `.env.default` at the project root — copy it to `.env` and fill in the required values.

### Server

| Variable | Default | Description |
| --- | --- | --- |
| `TIBERIO_HOST` | `0.0.0.0` | Bind address |
| `TIBERIO_PORT` | `8080` | Listen port |
| `TIBERIO_DEBUG` | `false` | Enable Uvicorn auto-reload (development only) |
| `TIBERIO_DEVICES_CONFIG_PATH` | `config/devices.yaml` | Path to the device registry YAML |

### Security

| Variable | Default | Description |
| --- | --- | --- |
| `TIBERIO_SHARED_SECRET` | *(empty)* | HMAC shared secret for AWS Lambda → home server request signing. When set, `POST /alexa/directive` requires `X-Tiberio-Timestamp` / `X-Tiberio-Signature` headers (HMAC-SHA256 over `"{timestamp}." + body`). Empty disables HMAC (bearer-token auth only). |
| `TIBERIO_HMAC_TOLERANCE_SECONDS` | `300` | Replay-protection window for the HMAC timestamp |
| `TIBERIO_JWT_SECRET` | *(empty)* | **Required in production** (min 32 chars). HS256 signing key for JWT tokens — the server refuses to start when this is empty or too short unless `TIBERIO_DEV_MODE=true`. |
| `TIBERIO_JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `TIBERIO_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime (minutes) |
| `TIBERIO_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime (days) |
| `TIBERIO_RATE_LIMIT_MAX_ATTEMPTS` | `10` | Max OAuth login/token requests per window (per client IP / username; an additional 3× per-IP bucket blocks username spraying) |
| `TIBERIO_RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window for the rate limiter |

::: warning Deployment caveats

- The HMAC timestamp check bounds *freshness*, not single use: a captured signed request can be replayed within the tolerance window. Lower `TIBERIO_HMAC_TOLERANCE_SECONDS` if your clock sync allows it.
- Rate limiting keys on the TCP client address. Behind a reverse proxy, all clients share the proxy's IP — terminate TLS on the server directly, or configure trusted `X-Forwarded-For` handling before relying on per-IP limits.
:::

### OAuth

| Variable | Default | Description |
| --- | --- | --- |
| `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` | *(empty)* | Comma-separated list of permitted redirect URIs. **Must be set in production** — see below. |
| `TIBERIO_DEV_MODE` | `false` | When `true`, an empty `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` accepts any redirect URI. **Never enable in production.** |

::: warning Fail-closed allowlist
When `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` is empty **and** `TIBERIO_DEV_MODE` is `false`, every request to `GET /oauth/authorize` and `POST /oauth/authorize` returns **503 Service Unavailable**. This is intentional — a misconfigured production server must fail loudly rather than silently accept any redirect URI.

For local development without a fixed redirect URI, set `TIBERIO_DEV_MODE=true` in your `.env`.
:::

### Storage

| Variable | Default | Description |
| --- | --- | --- |
| `TIBERIO_USERS_DB_PATH` | `tiberio_users.db` | Path to the SQLite database for user accounts |

### AWS / S3 beacon

| Variable | Default | Description |
| --- | --- | --- |
| `TIBERIO_AWS_REGION` | `eu-central-1` | AWS region for S3 beacon |
| `TIBERIO_S3_BEACON_BUCKET` | `tiberio-beacon` | S3 bucket name |
| `TIBERIO_S3_BEACON_KEY` | `endpoint.json` | S3 object key for the beacon file |

---

## Example .env for local development

```bash
# .env — do not commit to git
TIBERIO_HOST=127.0.0.1
TIBERIO_PORT=8080
TIBERIO_DEBUG=true
TIBERIO_DEVICES_CONFIG_PATH=config/devices.yaml
TIBERIO_USERS_DB_PATH=tiberio_users_dev.db
TIBERIO_JWT_SECRET=dev-secret-not-for-production
TIBERIO_DEV_MODE=true
```

## Example .env for production

```bash
TIBERIO_HOST=0.0.0.0
TIBERIO_PORT=8080
TIBERIO_DEBUG=false
TIBERIO_DEVICES_CONFIG_PATH=/opt/tiberio/config/devices.yaml
TIBERIO_USERS_DB_PATH=/var/lib/tiberio/users.db

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
TIBERIO_JWT_SECRET=a84f2c...
TIBERIO_SHARED_SECRET=7e91d3...

TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS=https://layla.amazon.com/api/skill/link/AMZN1234
```

::: tip Nested env vars
pydantic-settings supports `__` as a nesting delimiter inside the prefix. For example, `TIBERIO_JWT__SECRET` is an alternative spelling for `TIBERIO_JWT_SECRET`.
:::
