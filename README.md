# pantau-alexa

![Version](https://img.shields.io/badge/version-0.0.1-blue)

Alexa Smart Home Skill backend for home automation — controls TV (Harmony Hub), roller blinds (HomeKit), and heating thermostats (FRITZ!Box) via a self-hosted FastAPI server.

See [spec/KONZEPT.md](spec/KONZEPT.md) for the full architecture and implementation plan.

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
- **`POST /alexa/directive`** — Validates the Bearer JWT token before routing the directive

Users are stored in SQLite (`aiosqlite`). Passwords are hashed with `bcrypt`. Access tokens are short-lived signed JWTs (`python-jose`, HS256). Refresh tokens rotate on every use.

## Architecture

```
pantau/
├── domain/          # Pure domain models + value objects
├── application/     # Use-cases (commands)
├── commands/        # Organized by device: tv/, blinds/, heating/
├── ports/           # Abstract interfaces (Protocol)
├── adapters/        # Implementations: JWT, SQLite, Harmony, Fritz, HomeKit
├── interfaces/
│   ├── alexa/       # Directive router + capability handlers
│   └── oauth/       # Authorization Server endpoints
├── api/             # FastAPI app factory
├── config/          # pydantic-settings
└── composition.py   # Dependency injection root
```

## Running

```bash
uv run pantau
```

## Development

```bash
task test        # run tests with coverage
task lint        # ruff lint
task format      # ruff format
task typecheck   # mypy
```
