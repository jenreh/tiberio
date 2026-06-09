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
git clone https://github.com/example/pantau-alexa
cd pantau-alexa

# Install Python dependencies (uv creates the venv automatically)
uv sync
```

## Configure devices

Copy the example config and edit it to match your setup:

```bash
cp config/devices.yaml config/devices.local.yaml
```

At minimum, set the correct IP address for your Harmony Hub and match the `watch_activity` name to the activity configured in your Harmony remote:

```yaml
# config/devices.yaml
tv:
  harmony_host: "192.168.178.50"   # ← your Harmony Hub LAN IP
  watch_activity: "Fernseher"      # ← exact activity name in Harmony app
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

```bash
# .env — never commit this file
JWT_SECRET=change-me-to-a-long-random-string-in-production
SHARED_SECRET=another-long-random-secret
DEVICES_CONFIG_PATH=config/devices.yaml
```

::: warning Production secrets
Generate real secrets before exposing the server to the internet:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
:::

## Create the first user

The OAuth2 login form requires at least one user in the SQLite database:

```bash
uv run pantau users create --username alice
# You will be prompted for a password
```

## Start the server

```bash
uv run pantau
```

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

You can send a fake Alexa directive directly to the server without needing an actual Alexa device. First, obtain a test token (the mock validator accepts any non-empty string during local dev if `JWT_SECRET` is not set):

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
          "token": "test-token"
        }
      }
    }
  }' | python -m json.tool
```

## Building the docs

```bash
cd docs
npm install
npm run docs:dev     # live preview at http://localhost:5173
npm run docs:build   # production build to docs/.vitepress/dist/
```
