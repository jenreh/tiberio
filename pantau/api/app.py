"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from pantau.api.logging_setup import configure_logging
from pantau.api.middleware import (
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from pantau.application.publish_beacon import BeaconPublisher
from pantau.commands.list_connected_devices import ListConnectedDevicesCommand
from pantau.composition import Container, build_container
from pantau.config.settings import Settings, get_settings
from pantau.interfaces.alexa.directive_router import alexa_router
from pantau.interfaces.http_auth import require_bearer_token
from pantau.interfaces.oauth.router import oauth_router
from pantau.interfaces.rate_limit import SlidingWindowRateLimiter
from pantau.ports.device_registry_port import DeviceRegistryPort

log = logging.getLogger(__name__)


_MIN_JWT_SECRET_LENGTH = 32


def _validate_security_settings(settings: Settings) -> None:
    """Fail fast on insecure secrets unless running in dev mode.

    An empty jwt_secret would let anyone forge HS256 tokens offline and
    drive every device through /alexa/directive.
    """
    if settings.dev_mode:
        log.warning(
            "DEV_MODE is enabled — redirect_uri and secret checks are "
            "relaxed. Do NOT use in production."
        )
        if not settings.jwt_secret.get_secret_value():
            log.warning(
                "DEV_MODE is on and jwt_secret is empty — "
                "tokens are forgeable. Do NOT use in production."
            )
        return

    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise RuntimeError(
            "PANTAU_JWT_SECRET is not set. Refusing to start: an empty JWT "
            "secret makes every access token forgeable. Set PANTAU_JWT_SECRET "
            "or PANTAU_DEV_MODE=true for local development."
        )
    if len(secret) < _MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            "PANTAU_JWT_SECRET is too short for HS256: "
            f"need at least {_MIN_JWT_SECRET_LENGTH} characters."
        )
    if not settings.shared_secret.get_secret_value():
        log.warning(
            "PANTAU_SHARED_SECRET is not set — HMAC request signing on "
            "/alexa/directive is disabled (bearer-token auth only)."
        )


def _validate_beacon_settings(settings: Settings) -> None:
    """Fail fast on beacon misconfiguration (KONZEPT §9).

    The S3 beacon is the sole mechanism by which the AWS edge resolves the
    home server. Enabling it without a publishable HTTPS base URL would
    silently defeat the whole edge path while the updater loop logs success.
    """
    if not settings.beacon_enabled:
        return
    url = settings.public_base_url
    if not url:
        raise RuntimeError(
            "PANTAU_BEACON_ENABLED is true but PANTAU_PUBLIC_BASE_URL is not "
            "set. Refusing to start: the beacon would never announce a "
            "reachable home-server address."
        )
    allowed = ("https://", "http://") if settings.dev_mode else ("https://",)
    if not url.startswith(allowed):
        raise RuntimeError(
            "PANTAU_PUBLIC_BASE_URL must start with https:// "
            "(http:// is allowed only with PANTAU_DEV_MODE=true): "
            f"got {url!r}."
        )


async def _publish_beacon_safely(publisher: BeaconPublisher) -> None:
    """Publish the beacon; failures are logged and never propagate."""
    try:
        await publisher.execute()
    except Exception:
        log.warning("Beacon publish failed", exc_info=True)


async def _beacon_loop(publisher: BeaconPublisher, interval_seconds: int) -> None:
    """Re-publish the beacon every *interval_seconds* until cancelled."""
    while True:
        await asyncio.sleep(interval_seconds)
        await _publish_beacon_safely(publisher)


def create_app(
    settings: Settings | None = None,
    container: Container | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        # Only load from environment when building the container ourselves
        settings = get_settings() if container is None else Settings()

    configure_logging(settings)
    _validate_security_settings(settings)
    _validate_beacon_settings(settings)

    if container is None:
        container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[return]
        started = []
        beacon_task: asyncio.Task[None] | None = None
        try:
            for adapter in container.lifecycle_adapters:
                await adapter.start()
                started.append(adapter)
            if settings.beacon_enabled:
                publisher = container.get(BeaconPublisher)
                await _publish_beacon_safely(publisher)
                beacon_task = asyncio.create_task(
                    _beacon_loop(publisher, settings.beacon_update_interval_seconds)
                )
                log.info(
                    "Beacon updater started (interval=%ds)",
                    settings.beacon_update_interval_seconds,
                )
            yield
        finally:
            if beacon_task is not None:
                beacon_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await beacon_task
                log.debug("Beacon updater stopped")
            # Stop only what actually started — a partial-start failure must
            # not leave earlier adapters holding connections (zombies).
            for adapter in reversed(started):
                try:
                    await adapter.stop()
                except Exception:
                    log.exception("Error stopping adapter %s", type(adapter).__name__)

    app = FastAPI(
        title="pantau-alexa",
        description="Alexa Smart Home Skill backend — home automation server.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Outermost first: the request id must already be set while the
    # security-headers middleware (and everything inside) runs and logs.
    # The body-size cap is innermost so its 413 still gets id + headers.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_directive_body_bytes,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.state.container = container
    app.state.settings = settings
    app.state.login_rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_max_attempts, settings.rate_limit_window_seconds
    )
    # Wider per-IP bucket: blocks spraying many usernames from one address,
    # which the per-(ip, username) bucket alone would never throttle.
    app.state.login_ip_rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_max_attempts * 3, settings.rate_limit_window_seconds
    )
    app.state.token_rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_max_attempts, settings.rate_limit_window_seconds
    )

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

    @app.get(
        "/devices/connected",
        tags=["system"],
        dependencies=[Depends(require_bearer_token)],
    )
    async def connected_devices() -> JSONResponse:
        """Live device scan — queries all registered backends.

        Requires a valid bearer token: the response exposes the full home
        inventory and triggers live scans of every backend.

        Each backend reports independently: an offline adapter yields
        ``status="unavailable"`` for that section while the rest succeed.
        New adapters (Hue, Sonos, …) appear automatically when registered.
        """
        container: Container = app.state.container
        command = container.get(ListConnectedDevicesCommand)
        result = await command.execute()
        return JSONResponse(result)


def main() -> None:
    from dotenv import load_dotenv  # noqa: PLC0415

    from pantau.config.settings import _PROJECT_ROOT  # noqa: PLC0415

    env_file = _PROJECT_ROOT / ".env"
    loaded = load_dotenv(env_file)
    if loaded:
        log.info("Loaded environment from %s", env_file)
    else:
        log.info(
            "No .env file found at %s — using environment variables only", env_file
        )

    settings = get_settings()
    uvicorn.run(
        "pantau.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
