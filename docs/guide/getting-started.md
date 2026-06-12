# Getting Started

This page gets you from zero to a running server in five minutes. The result is a FastAPI server on your LAN that can already receive Alexa directives — perfect for local development and testing even before the AWS edge is set up (Phase 5).

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.14+ | Managed by `uv` automatically |
| [uv](https://docs.astral.sh/uv/) | latest | Fast Python package manager |
| [Task](https://taskfile.dev) | latest | Task runner (replaces `make`) |
| Node.js | 18+ | Only needed to build these docs |

You also need at least one physical device (Harmony Hub, FRITZ!Box, or HomeKit accessory) **or** you can run entirely with the mock adapters that are used in tests.

## Installation

```bash
# Clone the repository
git clone https://github.com/jenreh/tiberio
cd tiberio

# Install the pinned Python version, sync dependencies, and set up pre-commit
task init
```

`task init` installs and pins the required Python version, runs `uv sync`
(which creates the venv automatically), and installs the pre-commit hooks. If
you only need the dependencies, `uv sync` on its own is enough.

## Configure devices

The active device registry is selected by the `TIBERIO_DEVICES_CONFIG_PATH`
environment variable, which defaults to `config/devices.yaml`. Edit that file
directly, or point the variable at a copy you keep out of version control:

```bash
# Optional: keep your own copy and point the server at it via .env
cp config/devices.yaml config/devices.mine.yaml
# then set TIBERIO_DEVICES_CONFIG_PATH=config/devices.mine.yaml in your .env
```

At minimum, match the `watch_activity` name to the activity configured in your Harmony remote (the Harmony Hub is discovered automatically on the LAN — there is no host/IP to set):

```yaml
# config/devices.yaml
tv:
  watch_activity: "Fernseher"      # ← exact activity name in Harmony app
  aliases: ["Fernseher", "TV"]     # Alexa device-name aliases
  audio:
    id: "tv-audio"
    friendly_name: "TV Audio"
  channels:
    - id: "zdf"
      friendly_name: "ZDF"
      channel_number: "2"
```

See the full [Configuration Reference](./configuration) for all fields.

## Create an .env file

All runtime settings use the `TIBERIO_` prefix (see [`.env.default`](https://github.com/jenreh/tiberio/blob/main/.env.default) for the full list). Unprefixed names are silently ignored, so the server would refuse to start with an empty `jwt_secret`.

```bash
# .env — never commit this file
# Local development: relax the JWT/redirect-uri startup checks so you can
# boot without real secrets.
TIBERIO_DEV_MODE=true

# Production: set strong secrets instead of DEV_MODE (min 32 chars for the JWT).
# TIBERIO_JWT_SECRET=change-me-to-a-long-random-string-in-production
# TIBERIO_SHARED_SECRET=another-long-random-secret

# Path to the device registry (defaults to config/devices.yaml)
TIBERIO_DEVICES_CONFIG_PATH=config/devices.yaml
```

::: tip Local dev shortcut
The server validates secrets on startup and refuses to boot when
`TIBERIO_JWT_SECRET` is empty or shorter than 32 characters. Setting
`TIBERIO_DEV_MODE=true` relaxes that check (and the OAuth redirect-URI
allowlist) so you can run locally without real secrets. Never enable it in
production.
:::

::: warning Production secrets
Generate real secrets before exposing the server to the internet, and drop
`TIBERIO_DEV_MODE`:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

:::

## Create the first user

The OAuth2 login form requires at least one user in the SQLite database. User
management is the separate `tiberio-users` console script; its `add` subcommand
takes the username as a positional argument:

```bash
uv run tiberio-users add alice
# You will be prompted for a password
```

## Start the server

```bash
task run
```

`task run` launches Uvicorn with auto-reload
(`uvicorn tiberio.api.app:create_app --reload --factory --host 0.0.0.0 --port 8080`).
The console script `uv run tiberio` also starts the server, reading host/port
from your settings.

The server starts on `http://0.0.0.0:8080` by default. Verify it is healthy:

```bash
curl http://localhost:8080/health
# {"status":"ok","devices":{"channels":4,"blinds":2,"thermostats":2}}
```

## Development commands

All day-to-day operations go through the `task` runner:

```bash
task test         # run pytest with coverage report
task lint         # ruff lint check
task format       # ruff format (auto-fixes)
task typecheck    # mypy static type check
```

Run all quality gates at once before pushing:

```bash
task lint && task format && task typecheck && task test
```

## Sending a test directive

You can send a fake Alexa directive directly to the server without needing an actual Alexa device. `/alexa/directive` validates a **real** signed JWT in the `Bearer` token — there is no mock validator that accepts arbitrary strings, so the `test-token` below is rejected. Obtain a real access token by completing the OAuth flow (`/oauth/authorize` → `/oauth/token`) for a user you created with `tiberio-users add`, then put that token in the `scope`.

::: warning HMAC required when a shared secret is set
When `TIBERIO_SHARED_SECRET` is configured, `/alexa/directive` additionally requires `X-Tiberio-Timestamp` and `X-Tiberio-Signature` headers (HMAC-SHA256, 5-minute replay window). The bare `curl` below sends neither, so it returns 401 the moment a shared secret is present. Leave `TIBERIO_SHARED_SECRET` empty for this local test.
:::

```bash
# Discover all devices
curl -s -X POST http://localhost:8080/alexa/directive \
  -H "Content-Type: application/json" \
  -d '{
    "directive": {
      "header": {
        "namespace": "Alexa.Discovery",
        "name": "Discover",
        "messageId": "test-msg-1",
        "payloadVersion": "3"
      },
      "payload": {
        "scope": {
          "type": "BearerToken",
          "token": "<your-access-token>"
        }
      }
    }
  }' | uv run python -m json.tool
```

## Building the docs

The docs are wired through Task (see `taskfiles/Taskfile.docs.yml`):

```bash
task docs:install   # npm install in docs/
task docs:dev       # live preview at http://localhost:5173
task docs:build     # production build to docs/.vitepress/dist/
task docs:preview   # preview the production build locally
```
