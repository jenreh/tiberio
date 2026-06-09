# Configuration Reference

pantau-alexa is configured through two sources:

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
|---|---|---|
| `harmony_host` | string | LAN IP address of the Harmony Hub |
| `watch_activity` | string | Exact Harmony activity name that enables TV viewing |
| `audio.id` | string | Alexa endpoint ID for the Speaker capability (mute/unmute) |
| `audio.friendly_name` | string | Alexa-visible label for the audio device |

#### Channels

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique endpoint ID (used internally and by Alexa) |
| `friendly_name` | string | Name Alexa uses to identify this endpoint |
| `aliases` | string[] | Optional alternative names for discovery |
| `channel_number` | string | Channel digits sent to the Harmony Hub |

#### Blinds

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique endpoint ID |
| `friendly_name` | string | Alexa-visible label |
| `homekit_entity_id` | string | Entity ID in the HomeKit library's `entities.toml` |
| `invert` | bool | `true` if your motor uses reversed position values |
| `aliases` | string[] | Optional alternative names |

#### Thermostats

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique endpoint ID |
| `friendly_name` | string | Alexa-visible label |
| `fritz_name` | string | Device name as shown in the FRITZ!Box web UI |
| `min_celsius` | float | Minimum temperature Alexa is allowed to set (default: 8.0) |
| `max_celsius` | float | Maximum temperature Alexa is allowed to set (default: 28.0) |
| `aliases` | string[] | Optional alternative names |

---

## Environment Variables

Settings are loaded from environment variables or a `.env` file in the project root. The class is `pantau/config/settings.py` → `Settings`.

### Server

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8080` | Listen port |
| `DEBUG` | `false` | Enable Uvicorn auto-reload (development only) |
| `DEVICES_CONFIG_PATH` | `config/devices.yaml` | Path to the device registry YAML |

### Security

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | *(empty)* | **Required in production.** HS256 signing key for JWT tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |
| `SHARED_SECRET` | *(empty)* | **Required in production.** HMAC shared secret between Lambda and home server |

### OAuth

| Variable | Default | Description |
|---|---|---|
| `OAUTH_ALLOWED_REDIRECT_URIS` | *(empty list)* | Comma-separated list of permitted redirect URIs. **Empty = allow any (dev mode only).** Set this in production. |

### Storage

| Variable | Default | Description |
|---|---|---|
| `USERS_DB_PATH` | `pantau_users.db` | Path to the SQLite database for user accounts |

### AWS (Phase 5 — planned)

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `eu-central-1` | AWS region for S3 beacon |
| `S3_BEACON_BUCKET` | `pantau-alexa-beacon` | S3 bucket name |
| `S3_BEACON_KEY` | `endpoint.json` | S3 object key for the beacon file |

---

## Example .env for local development

```bash
# .env — do not commit to git
HOST=127.0.0.1
PORT=8080
DEBUG=true
DEVICES_CONFIG_PATH=config/devices.yaml
USERS_DB_PATH=pantau_users_dev.db
JWT_SECRET=dev-secret-not-for-production
```

## Example .env for production

```bash
HOST=0.0.0.0
PORT=8080
DEBUG=false
DEVICES_CONFIG_PATH=/opt/pantau/config/devices.yaml
USERS_DB_PATH=/var/lib/pantau/users.db

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=a84f2c...
SHARED_SECRET=7e91d3...

OAUTH_ALLOWED_REDIRECT_URIS=https://layla.amazon.com/api/skill/link/AMZN1234
```

::: tip Nested env vars
pydantic-settings supports `__` as a nesting delimiter. For example, you can set `JWT__SECRET` as an alternative to `JWT_SECRET` (the underscore-based flattening also works, as shown above).
:::
