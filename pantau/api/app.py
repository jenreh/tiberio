"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pantau.composition import Container, build_container
from pantau.config.settings import Settings, get_settings
from pantau.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

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

    _register_routes(app)

    log.info("pantau-alexa server created")
    return app


def _register_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["system"])
    async def health() -> JSONResponse:
        """Health check — returns 200 when the server is up."""
        container: Container = app.state.container
        registry = container.get(DeviceRegistryPort).get_registry()
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


def main() -> None:

    settings = get_settings()
    uvicorn.run(
        "pantau.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
