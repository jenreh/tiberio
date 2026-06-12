# What is Tiberio?

Tiberio is a self-hosted Alexa Smart Home Skill backend that lets you control your **TV** (Logitech Harmony Hub), **roller blinds** (HomeKit), and **heating thermostats** (AVM FRITZ!Box) by speaking to an Amazon Echo device — entirely through infrastructure you own and operate.

## The problem it solves

You want to say things like:

| Voice command | What happens |
|---|---|
| "Alexa, switch to ZDF" | TV turns on and changes to channel 2 |
| "Alexa, mute the TV" | Sends an IR mute toggle to the Harmony Hub |
| "Alexa, set the living room heating to 22 degrees" | Sets the FRITZ!DECT thermostat to 22 °C |
| "Alexa, open the blinds in the kitchen" | HomeKit accessory moves the blind to 100% |
| "Alexa, lower the living room blinds by 20%" | Adjusts blind position by a relative delta |

Off-the-shelf Alexa integrations for these devices either don't exist, require paid subscriptions, or route all commands through a third-party cloud service. Tiberio puts the orchestration logic on a FastAPI server in your own home network — Alexa just becomes the voice interface.

## Two constraints that shape everything

Understanding these two constraints makes the entire architecture immediately obvious:

### 1. The home server has no stable public IP

Home internet connections get a different IP every time they reconnect, and many use CGNAT (no direct inbound connections at all). The home server is only reliably reachable *from the inside* (LAN) or through a tunnel.

**Solution:** A small JSON file on Amazon S3 — the *S3 beacon* — always contains the home server's current reachable URL. Before forwarding any command, the AWS Lambda proxy reads this file to find the current address.

### 2. Alexa Account Linking requires a stable OAuth2 server

Before an Alexa Smart Home Skill can control your devices, the user must complete *Account Linking* — an OAuth2 Authorization Code flow that pairs your Amazon account with your home server. Amazon's servers need to reach the OAuth endpoints at a *stable, public HTTPS URL*.

**Solution:** The home server *is* the OAuth2 Identity Provider, but the stable public URLs (used in the Alexa Skill configuration) point to a Lambda Function URL on AWS. That AWS endpoint transparently proxies all OAuth traffic to the home server using the same S3-beacon address lookup.

## How it all fits together

```
  You speak
     │
     ▼
Alexa Cloud
     │ Smart Home Directive
     ▼
AWS Lambda (stable ARN)          ← Alexa requires Lambda as endpoint
     │ reads current URL
     ├──► S3 endpoint.json
     │ forwards directive
     ▼
FastAPI Home Server (dynamic URL)
     │
     ├──► Harmony Hub  (TV via WebSocket)
     ├──► HomeKit      (blinds)
     └──► FRITZ!Box    (thermostats via fritzctl)
```

AWS is a *dumb proxy*. It only knows where to forward requests. All device intelligence — capability routing, command orchestration, device registry, OAuth token issuance — lives in the FastAPI server on your LAN.

## Implementation status

| Phase | What it delivers | Status |
|---|---|---|
| 0 | Project scaffold, FastAPI app, health endpoint | ✅ Done |
| 1 | Domain models, device registry, all use-case commands | ✅ Done |
| 2 | Real device adapters (Harmony, Fritz, HomeKit) | ✅ Done |
| 3 | Alexa Smart Home directive layer (all capabilities) | ✅ Done |
| 4 | OAuth2 Authorization Server + PKCE + JWT + SQLite user store | ✅ Done |
| 5 | AWS Edge: Lambda proxy + S3 beacon + Terraform | ✅ Done |
| 6 | Skill manifest, Account Linking config, E2E hardening | ✅ Done |

All six phases are implemented and tested. The FastAPI server runs on your LAN; the AWS edge — a directive Lambda, an OAuth proxy on a Lambda Function URL, and the S3 beacon bucket — is provisioned by Terraform (`terraform/`) and makes the server reachable from Alexa. The Smart Home skill manifest, account-linking template, and Alexa test events ship in the repo too.

## The AWS edge

Terraform provisions the stable AWS front for the skill:

- **Directive Lambda** (`lambda/directive_proxy/`) — resolves the home server's tunnel URL from the S3 beacon (conditional GET, ETag cached) and forwards the directive with HMAC headers.
- **OAuth proxy** (`lambda/oauth_proxy/` behind a Lambda Function URL) — stable `/oauth/*` URLs for account linking, transparently proxied to the home server.
- **S3 beacon bucket** — versioned, encrypted `endpoint.json`; the home server publishes its current tunnel URL here.

## Skill configuration assets

The completed delivery layer ships in the repo:

- **`skill-package/skill.json`** — de-DE Smart Home skill manifest.
- **`skill-package/accountLinking.json`** — account-linking template with placeholders for the Terraform outputs (rendered into `skill-package/build/`).
- **`scripts/sample-events/`** — Alexa v3 directive test events for the directive Lambda (`aws lambda invoke` / `sam local`).
- **[Skill setup runbook](/skill-setup)** — Terraform outputs → Alexa console, account linking, device discovery, and the German E2E verification checklist.

## Operating it: the CLIs

Three Typer CLIs (registered in `pyproject.toml`) run the system:

- **`tiberio-users`** — manage OAuth users in the SQLite store (`add`, `list`, `passwd`, `delete`).
- **`tiberio-beacon`** — publish the current tunnel URL to the S3 beacon (`tiberio-beacon publish --base-url https://your-tunnel.example.com`).
- **`tiberio-setup`** — end-to-end automation: generates secrets, drives the Terraform two-phase deploy (`terraform/deploy-aws.sh`), renders the skill-package templates from Terraform outputs, and pushes the manifest + account-linking config to the skill via the ASK CLI.

## Security hardening

The OAuth surface and the AWS→home traffic are hardened:

- **HMAC request signing** — when `TIBERIO_SHARED_SECRET` is set, `/alexa/directive` requires `X-Tiberio-Timestamp` and `X-Tiberio-Signature` headers (HMAC-SHA256, 5-minute replay window).
- **Rate limiting** — sliding-window limiter on the login and token endpoints (per client IP / username).
- **JWT startup validation** — the server refuses to start when `TIBERIO_JWT_SECRET` is absent or too short (unless `TIBERIO_DEV_MODE=true`).

## Stack

| Layer | Technology |
|---|---|
| Server | Python 3.14, FastAPI, Uvicorn |
| Settings | pydantic-settings (env vars + `.env`) |
| Device registry | YAML (`config/devices.yaml`) |
| TV control | harmonyhub-py (WebSocket, per-operation) |
| Blind control | homekit-py (HomeKit protocol) |
| Thermostat control | fritzctl-py (FRITZ!Box HTTP API) |
| Auth tokens | python-jose (HS256 JWTs) |
| User store | aiosqlite (SQLite, async) |
| Testing | pytest, pytest-asyncio, coverage ≥ 80% |
| Code quality | ruff (lint + format), mypy |
| Task runner | Task (Taskfile.dist.yml) |
| AWS edge | Lambda (directive proxy + OAuth proxy via Function URL), S3 beacon |
| Infrastructure | Terraform (`terraform/`, `deploy-aws.sh`) |
| Skill assets | `skill-package/` (skill.json, accountLinking.json), ASK CLI |
| Tooling CLIs | Typer (`tiberio-users`, `tiberio-beacon`, `tiberio-setup`) |
