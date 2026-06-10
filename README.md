# pantau-alexa

![Version](https://img.shields.io/badge/version-0.0.1-blue)
![Tests](https://img.shields.io/badge/tests-356%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)

Alexa Smart Home Skill backend for home automation — controls TV (Harmony Hub), roller blinds (HomeKit), and heating thermostats (FRITZ!Box) via a self-hosted FastAPI server.

See [spec/KONZEPT.md](spec/KONZEPT.md) for the full architecture and implementation plan.
See [Developer Documentation](https://pantau-alexa.readthedocs.io/en/latest/) for the full documentation of the project.

## Implementation status

| Phase | Description                                    | Status     |
| ----- | ---------------------------------------------- | ---------- |
| 0     | Project setup & skeleton                       | ✅ Done    |
| 1     | Domain, Device-Registry & Use-Cases            | ✅ Done    |
| 2     | Real device adapters (Harmony, Fritz, HomeKit) | ✅ Done    |
| 3     | Alexa Smart Home directive layer               | ✅ Done    |
| 4     | OAuth2 / Account Linking (IdP)                 | ✅ Done    |
| 5     | AWS Edge: Lambda-Proxy + S3-Beacon + Terraform | ⬜ Planned |
| 6     | Skill configuration & E2E hardening            | ⬜ Planned |

## Phase 4 — OAuth2 / Account Linking

The home server acts as a self-hosted OAuth2 Authorization Server with PKCE support:

- **`GET /oauth/authorize`** — HTML login form
- **`POST /oauth/authorize`** — Validates credentials, issues an authorization code, redirects
- **`POST /oauth/token`** — Exchanges code → access/refresh JWT pair (`authorization_code` grant), or rotates tokens (`refresh_token` grant)
- **`POST /alexa/directive`** — Validates the Bearer JWT token and optional HMAC signature before routing the directive
- **`GET /devices/connected`** — Lists connected devices (requires Bearer token)

Users are stored in SQLite (`aiosqlite`). Passwords are hashed with `bcrypt`. Access tokens are short-lived signed JWTs (`python-jose`, HS256). Refresh tokens rotate on every use and are stored as bcrypt hashes. OAuth flows enforce PKCE and a redirect-URI allowlist.

### Security

- **HMAC request signing** — When `PANTAU_SHARED_SECRET` is set, `/alexa/directive` requires `X-Pantau-Timestamp` and `X-Pantau-Signature` headers (HMAC-SHA256, 5-minute replay window).
- **Rate limiting** — Sliding-window limiter on login and token endpoints (per client IP / username).
- **JWT startup validation** — Server refuses to start when `PANTAU_JWT_SECRET` is absent or too short (unless `PANTAU_DEV_MODE=true`).

## Architecture

```text
pantau/
├── domain/          # Pure models, value objects, and domain errors
├── commands/        # Use-cases: one command per device capability
├── ports/           # Capability ports + auth/store abstractions (Protocol)
├── adapters/        # Implementations: JWT, SQLite, YAML, Harmony, Fritz, HomeKit
├── interfaces/
│   ├── alexa/       # Directive router, response builder, Alexa models
│   │   └── handlers/  # discovery, power, range, speaker, thermostat
│   ├── oauth/       # Authorization Server endpoints
│   ├── http_auth.py # Bearer-token FastAPI dependency
│   └── rate_limit.py # Sliding-window rate limiter
├── api/             # FastAPI app factory + lifespan
├── cli/             # pantau-users management CLI (Typer)
├── config/          # pydantic-settings + devices.yaml loader
└── composition.py   # Dependency injection root
```

### Capability ports

Each device capability is its own Protocol port (`PowerablePort`, `RangeControllablePort`, `TemperatureControllablePort`, `VolumeControllablePort`, `MuteControllablePort`). Adapters implement only the ports they support; the composition root resolves capabilities at startup.

### Domain errors

| Error                    | Meaning                               | Alexa mapping          |
| ------------------------ | ------------------------------------- | ---------------------- |
| `DeviceNotFoundError`    | Endpoint ID not in the device config  | `NO_SUCH_ENDPOINT`     |
| `DeviceUnavailableError` | Device unreachable (network/timeout)  | `ENDPOINT_UNREACHABLE` |
| `DeviceCapabilityError`  | Device lacks the requested capability | `INVALID_VALUE`        |

## Project setup

### Required tools

**uv** — Python package and project manager

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install uv
```

**task** — task runner ([taskfile.dev](https://taskfile.dev))

```bash
# macOS (Homebrew)
brew install go-task

# Linux / macOS (shell installer)
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b ~/.local/bin
```

### Setup

Install required Python version, dependencies and pre-commit

```bash
task init
```

## Running

Copy [.env.default](.env.default) to `.env`, fill in the required secrets, then:

```bash
task run
```

### Required environment variables (production)

| Variable                             | Description                                    |
| ------------------------------------ | ---------------------------------------------- |
| `PANTAU_JWT_SECRET`                  | HS256 signing key (min 32 chars)               |
| `PANTAU_SHARED_SECRET`               | HMAC key for Lambda→server request signing     |
| `PANTAU_OAUTH_ALLOWED_REDIRECT_URIS` | Comma-separated allowed OAuth redirect URIs    |

See [.env.default](.env.default) for all variables and their defaults.

### User management CLI

```bash
uv run pantau-users add <username>
uv run pantau-users list
uv run pantau-users passwd <username>
uv run pantau-users delete <username>
```

## Development

```bash
task test        # run tests with coverage
task lint        # ruff lint
task format      # ruff format
task typecheck   # mypy
```
