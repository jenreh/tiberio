# What is pantau-alexa?

pantau-alexa is a self-hosted Alexa Smart Home Skill backend that lets you control your **TV** (Logitech Harmony Hub), **roller blinds** (HomeKit), and **heating thermostats** (AVM FRITZ!Box) by speaking to an Amazon Echo device — entirely through infrastructure you own and operate.

## The problem it solves

You want to say things like:

| Voice command | What happens |
|---|---|
| "Alexa, switch to ZDF" | TV turns on and changes to channel 2 |
| "Alexa, mute the TV" | Sends an IR mute toggle to the Harmony Hub |
| "Alexa, set the living room heating to 22 degrees" | Sets the FRITZ!DECT thermostat to 22 °C |
| "Alexa, open the blinds in the kitchen" | HomeKit accessory moves the blind to 100% |
| "Alexa, lower the living room blinds by 20%" | Adjusts blind position by a relative delta |

Off-the-shelf Alexa integrations for these devices either don't exist, require paid subscriptions, or route all commands through a third-party cloud service. pantau-alexa puts the orchestration logic on a FastAPI server in your own home network — Alexa just becomes the voice interface.

## Two constraints that shape everything

Understanding these two constraints makes the entire architecture immediately obvious:

### 1. The home server has no stable public IP

Home internet connections get a different IP every time they reconnect, and many use CGNAT (no direct inbound connections at all). The home server is only reliably reachable *from the inside* (LAN) or through a tunnel.

**Solution:** A small JSON file on Amazon S3 — the *S3 beacon* — always contains the home server's current reachable URL. Before forwarding any command, the AWS Lambda proxy reads this file to find the current address.

### 2. Alexa Account Linking requires a stable OAuth2 server

Before an Alexa Smart Home Skill can control your devices, the user must complete *Account Linking* — an OAuth2 Authorization Code flow that pairs your Amazon account with your home server. Amazon's servers need to reach the OAuth endpoints at a *stable, public HTTPS URL*.

**Solution:** The home server *is* the OAuth2 Identity Provider, but the stable public URLs (used in the Alexa Skill configuration) point to API Gateway endpoints on AWS. Those AWS endpoints transparently proxy all OAuth traffic to the home server using the same S3-beacon address lookup.

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
| 5 | AWS Edge: Lambda proxy + S3 beacon + Terraform | ⬜ Planned |
| 6 | Skill manifest, Account Linking config, E2E hardening | ⬜ Planned |

Phases 0–4 are fully implemented and tested. The server is production-ready as a local HTTP endpoint. Phases 5–6 will wrap it in the AWS edge that makes it reachable from Alexa.

## Stack

| Layer | Technology |
|---|---|
| Server | Python 3.14, FastAPI, Uvicorn |
| Settings | pydantic-settings (env vars + `.env`) |
| Device registry | YAML (`config/devices.yaml`) |
| TV control | harmonyhub-py (WebSocket) |
| Blind control | homekit-py (HomeKit protocol) |
| Thermostat control | fritzctl-py (FRITZ!Box HTTP API) |
| Auth tokens | python-jose (HS256 JWTs) |
| User store | aiosqlite (SQLite, async) |
| Testing | pytest, pytest-asyncio, coverage ≥ 80% |
| Code quality | ruff (lint + format), mypy |
| Task runner | Task (Taskfile.dist.yml) |
| Infrastructure | Terraform (planned, Phase 5) |
