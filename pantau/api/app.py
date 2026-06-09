"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pantau.commands.list_connected_devices import ListConnectedDevicesCommand
from pantau.composition import Container, build_container
from pantau.config.settings import Settings, get_settings
from pantau.interfaces.alexa.directive_router import alexa_router
from pantau.interfaces.oauth.router import oauth_router
from pantau.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    container: Container | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        # Only load from environment when building the container ourselves
        settings = get_settings() if container is None else Settings()

    if container is None:
        container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[return]
        adapters = container.lifecycle_adapters
        for adapter in adapters:
            await adapter.start()
        yield
        for adapter in reversed(adapters):
            await adapter.stop()

    app = FastAPI(
        title="pantau-alexa",
        description="Alexa Smart Home Skill backend — home automation server.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.container = container
    app.state.settings = settings

    if not settings.oauth_allowed_redirect_uris:
        if settings.dev_mode:
            log.warning(
                "DEV_MODE is on and oauth_allowed_redirect_uris is empty — "
                "all redirect_uris will be accepted. Do NOT use in production."
            )
        else:
            log.error(
                "oauth_allowed_redirect_uris is empty and DEV_MODE is off — "
                "all /oauth/authorize requests will return 503. "
                "Set PANTAU_OAUTH_ALLOWED_REDIRECT_URIS or PANTAU_DEV_MODE=true."
            )

    _register_routes(app)

    log.info("pantau-alexa server created")
    return app


def _register_routes(app: FastAPI) -> None:
    app.include_router(alexa_router)
    app.include_router(oauth_router)

    @app.get("/health", tags=["system"])
    async def health() -> JSONResponse:
        """Health check — returns 200 when the server is up."""
        container: Container = app.state.container
        registry = container.get(DeviceRegistryPort).get_registry()  # type: ignore[type-abstract]
        return JSONResponse(
            {
                "status": "ok",
                "devices": {
                    "channels": len(registry.tv.channels),
                    "blinds": len(registry.blinds),
                    "thermostats": len(registry.thermostats),
                },
            }
        )

    @app.get("/devices/connected", tags=["system"])
    async def connected_devices() -> JSONResponse:
        """Live device scan — queries Harmony Hub, HomeKit, and FRITZ!Box in parallel.

        Each backend reports independently: an offline hub yields
        ``status="unavailable"`` for that section while the rest succeed.
        """
        container: Container = app.state.container
        command = container.get(ListConnectedDevicesCommand)
        result = await command.execute()

        def _harmony() -> dict:
            r = result.harmony
            base: dict = {"status": r.status}
            if r.error:
                base["error"] = r.error
            else:
                base["activities"] = [
                    {"id": a.id, "label": a.label, "is_power_off": a.is_power_off}
                    for a in r.activities
                ]
                base["devices"] = [
                    {
                        "id": d.id,
                        "label": d.label,
                        "manufacturer": d.manufacturer,
                        "model": d.model,
                    }
                    for d in r.devices
                ]
            return base

        def _homekit() -> dict:
            r = result.homekit
            base: dict = {"status": r.status}
            if r.error:
                base["error"] = r.error
            else:
                base["devices"] = [
                    {
                        "entity_id": e.entity_id,
                        "name": e.name,
                        "domain": e.domain,
                        "room": e.room,
                    }
                    for e in r.devices
                ]
            return base

        def _fritz() -> dict:
            r = result.fritz
            base: dict = {"status": r.status}
            if r.error:
                base["error"] = r.error
            else:
                base["devices"] = [
                    {
                        "id": d.id,
                        "name": d.name,
                        "online": d.online,
                        "current_temp": d.current_temp,
                        "target_temp": d.target_temp,
                        "battery_level": d.battery_level,
                        "battery_low": d.battery_low,
                    }
                    for d in r.devices
                ]
            return base

        return JSONResponse(
            {"harmony": _harmony(), "homekit": _homekit(), "fritz": _fritz()}
        )


def main() -> None:

    settings = get_settings()
    uvicorn.run(
        "pantau.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
