# System Overview

pantau-alexa has two distinct runtime zones — **AWS Edge** (stable, public, planned in Phase 5) and the **Home Server** (dynamic IP, your LAN, implemented in Phases 0–4). Between them sits an S3 object that tells the Lambda where to find your home server right now.

## The big picture

```mermaid
graph TD
    User(["👤 User<br/>(voice command)"])

    subgraph AlexaCloud["Alexa Cloud"]
        AlexaSH["Smart Home NLU"]
    end

    subgraph AWS["AWS Edge — Phase 5 (planned)"]
        Lambda["Lambda<br/>Directive Proxy"]
        S3[("S3 Beacon<br/>endpoint.json")]
        APIGW["API Gateway<br/>OAuth Proxy"]
    end

    subgraph Home["Home Server — Phases 0–4 (implemented)"]
        FastAPI["FastAPI Server"]

        subgraph AlexaLayer["interfaces/alexa/"]
            Router["AlexaDirectiveRouter"]
            Handlers["Handlers<br/>(Power · Speaker · Thermostat · Range · Discovery)"]
        end

        subgraph OAuthLayer["interfaces/oauth/"]
            OAuthRouter["OAuth2 Router<br/>(authorize · token)"]
        end

        subgraph Commands["commands/"]
            ActivateChannel["ActivateChannelCommand"]
            SetBlind["SetBlindPositionCommand"]
            SetTemp["SetThermostatTemperatureCommand"]
            SetMute["SetTvMuteCommand"]
            Discover["DiscoverDevicesCommand"]
        end

        subgraph Ports["ports/"]
            TvPort["TvPort"]
            BlindPort["BlindPort"]
            ThermoPort["ThermostatPort"]
            RegPort["DeviceRegistryPort"]
            TokenPort["TokenValidatorPort"]
            UserPort["UserStorePort"]
        end

        subgraph Adapters["adapters/"]
            HarmonyAdapter["HarmonyTvAdapter"]
            HomeKitAdapter["HomeKitBlindAdapter"]
            FritzAdapter["FritzThermostatAdapter"]
            JwtSvc["JwtService"]
            SQLite["SqliteUserStore"]
            YamlReg["YamlDeviceRegistry"]
        end
    end

    subgraph Devices["Physical Devices (LAN)"]
        TV["Logitech Harmony Hub<br/>📺 TV"]
        Blinds["HomeKit Accessories<br/>🪟 Blinds"]
        Fritz["AVM FRITZ!Box<br/>🌡️ Thermostats"]
    end

    User -->|speaks to| AlexaCloud
    AlexaCloud -->|"POST directive + Bearer token"| Lambda
    Lambda -->|"GET (ETag cache)"| S3
    Lambda -->|"forward + Shared-Secret header"| FastAPI
    AlexaCloud -->|"OAuth browser flow"| APIGW
    APIGW -->|"proxy /oauth/*"| FastAPI

    FastAPI --> Router
    FastAPI --> OAuthRouter
    Router --> Handlers
    Handlers --> ActivateChannel & SetBlind & SetTemp & SetMute & Discover
    ActivateChannel & SetBlind & SetTemp & SetMute & Discover --> Ports
    Ports -.->|"implemented by"| Adapters
    OAuthRouter --> JwtSvc & SQLite

    HarmonyAdapter -->|"WebSocket"| TV
    HomeKitAdapter -->|"HomeKit protocol"| Blinds
    FritzAdapter -->|"HTTP API"| Fritz
    YamlReg -->|"reads"| RegPort

    style AWS fill:#FFF3E0,stroke:#FB8C00
    style Home fill:#E8F5E9,stroke:#43A047
    style AlexaCloud fill:#E3F2FD,stroke:#1E88E5
    style Devices fill:#F3E5F5,stroke:#8E24AA
```

## Zone responsibilities

### Alexa Cloud
Amazon's servers. They receive your voice command, determine the intent (e.g. "turn on ZDF"), and call your Lambda with a structured directive JSON payload. This zone is entirely outside your control.

### AWS Edge *(Phase 5, planned)*

| Component | Role |
|---|---|
| **Lambda: Directive Proxy** | The Alexa Skill's endpoint ARN. Reads current home server URL from S3, then forwards the directive. |
| **S3: endpoint.json** | The *beacon* — a small JSON file `{ "base_url": "...", "updated_at": "..." }` that the home server keeps updated via `BeaconPublisherPort`. |
| **API Gateway: OAuth Proxy** | Stable HTTPS URLs for Alexa Account Linking. Transparently proxies `/oauth/authorize` and `/oauth/token` to the home server. |

### Home Server *(Phases 0–4, implemented)*

This is where everything interesting happens. The server exposes three routes:

| Route | Purpose |
|---|---|
| `POST /alexa/directive` | Receives Smart Home directives; validates JWT; routes to handlers |
| `GET/POST /oauth/authorize` | Shows login form; validates credentials; issues auth code |
| `POST /oauth/token` | Exchanges auth code → JWT + refresh token; or rotates refresh token |
| `GET /health` | Returns server status and device counts |

### Physical Devices (LAN)

The three device libraries run directly inside the home server process. They need LAN access — this is exactly why the device control logic cannot run inside Lambda.

| Device | Library | Protocol |
|---|---|---|
| Logitech Harmony Hub | harmonyhub-py | WebSocket (persistent connection) |
| HomeKit Accessories | homekit-py | Apple HomeKit over LAN |
| FRITZ!Box thermostats | fritzctl-py | FRITZ!Box HTTP API |

## Dependency flow

```mermaid
graph LR
    A["interfaces/<br/>(delivery)"] -->|calls| B["commands/<br/>(use-cases)"]
    B -->|depends on| C["ports/<br/>(abstractions)"]
    D["adapters/<br/>(infrastructure)"] -->|implements| C
    B -->|reads| E["domain/<br/>(pure models)"]
    D -->|uses| E
    F["composition.py<br/>(DI root)"] -->|wires| C
    F -->|wires| D

    style A fill:#BBDEFB
    style B fill:#C8E6C9
    style C fill:#FFCCBC
    style D fill:#E1BEE7
    style E fill:#FFF9C4
    style F fill:#F5F5F5
```

The **golden rule**: imports only flow *inward* (toward the domain). Adapters know about the domain; the domain knows nothing about adapters. Use-cases know about ports; ports know nothing about adapters. The composition root is the only place that breaks this rule — intentionally.

## Phase roadmap

```mermaid
gantt
    title pantau-alexa — implementation phases
    dateFormat YYYY-MM-DD
    section Done
    Phase 0 · Scaffold       :done,  p0, 2026-01-01, 7d
    Phase 1 · Domain & Commands :done, p1, after p0, 14d
    Phase 2 · Real Adapters   :done,  p2, after p1, 14d
    Phase 3 · Alexa Layer     :done,  p3, after p2, 14d
    Phase 4 · OAuth2 / IdP    :done,  p4, after p3, 14d
    section Planned
    Phase 5 · AWS Edge        :active, p5, after p4, 21d
    Phase 6 · E2E Hardening   :p6, after p5, 14d
```
