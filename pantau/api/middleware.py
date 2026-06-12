"""ASGI middleware: request correlation, security headers, body-size cap."""

from __future__ import annotations

import logging
import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pantau.api.logging_setup import request_id_var

log = logging.getLogger(__name__)

# Only ids that cannot break log lines or response headers are accepted;
# anything else (injection attempts, oversized values) is replaced.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_OAUTH_HEADERS = {
    # RFC 6749 §5.1: token responses must not be cached; the login page
    # carries credentials and PKCE parameters — never cache, never frame.
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Frame-Options": "DENY",
}


class RequestIdMiddleware:
    """Take X-Request-ID (or generate a uuid4) and expose it via contextvar.

    The id is echoed back in the ``X-Request-ID`` response header and is
    injected into every log record by ``RequestIdFilter``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = (
            incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
        )
        token = request_id_var.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)


class _BodyTooLarge(Exception):
    """Internal signal: the request stream exceeded the configured cap."""


class BodySizeLimitMiddleware:
    """Reject oversized request bodies at the boundary with HTTP 413.

    Rejects early on the Content-Length header and aborts while streaming
    once the accumulated size exceeds the limit — the body is never fully
    buffered, so the cap actually bounds memory usage.
    """

    def __init__(
        self, app: ASGIApp, max_body_bytes: int, path_prefix: str = "/alexa"
    ) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes
        self._path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(
            self._path_prefix
        ):
            await self._app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_body_bytes:
            log.warning("Request body too large: Content-Length=%s", declared)
            await self._send_413(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_body_bytes:
                    log.warning("Request body too large: %d bytes received", received)
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        body = b'{"detail":"Request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    """Add response-header hygiene: nosniff everywhere, no-store on /oauth."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        is_oauth = scope.get("path", "").startswith("/oauth")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                if is_oauth:
                    for name, value in _OAUTH_HEADERS.items():
                        headers.setdefault(name, value)
            await send(message)

        await self._app(scope, receive, send_with_headers)
