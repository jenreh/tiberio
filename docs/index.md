---
layout: home

hero:
  name: "pantau-alexa"
  text: "Voice-control your home — from your own server"
  tagline: "Alexa Smart Home backend that connects your TV, roller blinds, and heating over a self-hosted FastAPI server. No third-party cloud required for the actual device control."
  actions:
    - theme: brand
      text: Get Started
      link: /guide/
    - theme: alt
      text: Architecture
      link: /architecture/
    - theme: alt
      text: Modules
      link: /modules/domain

features:
  - icon: 📺
    title: TV via Harmony Hub
    details: "\"Alexa, switch to ZDF\" — activates the TV activity and tunes the channel via Logitech Harmony Hub over WebSocket. Each channel is its own Alexa endpoint."

  - icon: 🪟
    title: Roller Blinds via HomeKit
    details: "\"Alexa, open the blinds in the kitchen\" — drives HomeKit accessories via RangeController (0–100%). Open, close, or set an exact position by voice."

  - icon: 🌡️
    title: Heating via FRITZ!Box
    details: "\"Alexa, set the living room heating to 22 degrees\" — controls AVM FRITZ!DECT smart thermostats through the fritzctl library with built-in safety limits."

  - icon: 🔐
    title: Self-hosted OAuth2 IdP
    details: "Your home server is its own OAuth2 Authorization Server with PKCE. Credentials never leave your network. JWT access tokens are short-lived; refresh tokens rotate on every use."

  - icon: 🏗️
    title: Hexagonal Architecture
    details: "Domain → Commands → Ports ← Adapters. Use-cases are testable without hardware. Adding a new device or Alexa capability requires config or a single new file — not a rewrite."

  - icon: ⚙️
    title: Config-driven Device Registry
    details: "All devices and channels live in devices.yaml. Adding a new TV channel or thermostat is a one-line YAML change — zero code required."
---
