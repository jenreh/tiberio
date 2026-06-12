"""FastAPI router — POST /alexa/directive.

Bearer-token validation is applied as a per-route dependency so that
/oauth/* and /health endpoints remain accessible without a token.

When ``shared_secret`` is configured, requests must additionally carry a
timestamped HMAC-SHA256 signature (replay protection for AWS→home traffic):
``X-Pantau-Timestamp`` (unix seconds) and ``X-Pantau-Signature`` over
``f"{timestamp}." + raw_body``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from pantau.interfaces.alexa.router import AlexaDirectiveRouter
from pantau.ports.token_validator_port import TokenValidatorPort

log = logging.getLogger(__name__)

alexa_router = APIRouter(prefix="/alexa", tags=["alexa"])

_REQUIRED_SCOPE = "alexa"


def _require_valid_hmac(
    request: Request, raw_body: bytes, secret: str, tolerance_seconds: int
) -> None:
    """Verify the request HMAC headers; raises HTTP 401 on any mismatch."""
    timestamp_header = request.headers.get("X-Pantau-Timestamp")
    signature = request.headers.get("X-Pantau-Signature")
    if not timestamp_header or not signature:
        raise HTTPException(status_code=401, detail="Missing HMAC headers")

    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid HMAC timestamp") from exc

    if abs(time.time() - timestamp) > tolerance_seconds:
        log.warning("HMAC timestamp outside accepted window: %d", timestamp)
        raise HTTPException(status_code=401, detail="HMAC timestamp expired")

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        log.warning("HMAC signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")


def _extract_bearer_token(body: dict) -> str | None:
    """Extract the bearer token from the Alexa directive JSON body."""
    try:
        directive = body.get("directive", {})
        # Regular directives carry the token under endpoint.scope
        scope = directive.get("endpoint", {}).get("scope") or {}
        if token := scope.get("token"):
            return token
        # Discovery directives carry the token under payload.scope
        scope = directive.get("payload", {}).get("scope") or {}
        return scope.get("token")
    except AttributeError, TypeError:
        return None


def _directive_summary(body: dict) -> tuple[str, str, str | None]:
    """Extract (namespace, name, endpointId) for logging — never the token."""
    try:
        directive = body.get("directive", {})
        header = directive.get("header") or {}
        endpoint = directive.get("endpoint") or {}
        return (
            header.get("namespace", "?"),
            header.get("name", "?"),
            endpoint.get("endpointId"),
        )
    except AttributeError, TypeError:
        return "?", "?", None


def _log_directive_outcome(
    response: dict, namespace: str, name: str, endpoint_id: str | None
) -> None:
    try:
        event_header = response.get("event", {}).get("header", {})
        outcome = event_header.get("name", "?")
        error_type = response.get("event", {}).get("payload", {}).get("type")
    except AttributeError, TypeError:
        outcome, error_type = "?", None

    if outcome == "ErrorResponse":
        log.warning(
            "Directive failed: %s.%s endpoint=%s -> ErrorResponse(%s)",
            namespace,
            name,
            endpoint_id,
            error_type,
        )
    else:
        log.info(
            "Directive handled: %s.%s endpoint=%s -> %s",
            namespace,
            name,
            endpoint_id,
            outcome,
        )


@alexa_router.post("/directive")
async def handle_directive(request: Request) -> JSONResponse:
    """Receive an Alexa Smart Home directive and return an Alexa response."""
    # Body size is capped at the boundary by BodySizeLimitMiddleware.
    raw_body = await request.body()

    settings = request.app.state.settings
    shared_secret = settings.shared_secret.get_secret_value()
    if shared_secret:
        _require_valid_hmac(
            request, raw_body, shared_secret, settings.hmac_tolerance_seconds
        )

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    token = _extract_bearer_token(body)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    validator: TokenValidatorPort = request.app.state.container.get(TokenValidatorPort)  # type: ignore[type-abstract]
    try:
        claims = validator.validate(token)
    except ValueError as exc:
        log.warning("Bearer token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if claims.scope != _REQUIRED_SCOPE:
        log.warning(
            "Token scope %r lacks required scope %r", claims.scope, _REQUIRED_SCOPE
        )
        raise HTTPException(status_code=403, detail="Insufficient scope")

    namespace, name, endpoint_id = _directive_summary(body)
    log.info("Directive received: %s.%s endpoint=%s", namespace, name, endpoint_id)

    router: AlexaDirectiveRouter = request.app.state.container.get(AlexaDirectiveRouter)
    response = await router.route(body)
    _log_directive_outcome(response, namespace, name, endpoint_id)
    return JSONResponse(response)
