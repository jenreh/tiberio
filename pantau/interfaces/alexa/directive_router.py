"""FastAPI router — POST /alexa/directive.

Bearer-token validation is applied as a per-route dependency so that
/oauth/* and /health endpoints remain accessible without a token.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from pantau.interfaces.alexa.router import AlexaDirectiveRouter
from pantau.ports.token_validator_port import TokenValidatorPort

log = logging.getLogger(__name__)

alexa_router = APIRouter(prefix="/alexa", tags=["alexa"])


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


@alexa_router.post("/directive")
async def handle_directive(request: Request) -> JSONResponse:
    """Receive an Alexa Smart Home directive and return an Alexa response."""
    body = await request.json()

    token = _extract_bearer_token(body)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    validator: TokenValidatorPort = request.app.state.container.get(TokenValidatorPort)  # type: ignore[type-abstract]
    try:
        validator.validate(token)
    except ValueError as exc:
        log.warning("Bearer token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    router: AlexaDirectiveRouter = request.app.state.container.get(AlexaDirectiveRouter)
    response = await router.route(body)
    return JSONResponse(response)
