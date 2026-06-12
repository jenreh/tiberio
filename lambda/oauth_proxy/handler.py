"""OAuth catch-all proxy Lambda (API Gateway HTTP API, payload v2).

Forwards ``/oauth/*`` requests transparently to the home server resolved from
the S3 beacon: method, path, query string, filtered headers, cookies and body
(base64-aware) pass through both ways. Redirects are never followed so the
browser receives 302 + ``Location`` and ``Set-Cookie`` untouched.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any

from shared.beacon import BeaconError
from shared.runtime import get_beacon_reader, reset_beacon_cache, timeout_seconds

log = logging.getLogger(__name__)

_DROPPED_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "expect",
    }
)
_DROPPED_RESPONSE_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "content-length",
        "trailer",
        "upgrade",
        "proxy-authenticate",
        "te",
    }
)
_TEXT_CONTENT_HINTS = (
    "text/",
    "json",
    "xml",
    "x-www-form-urlencoded",
    "javascript",
)
_BODYLESS_METHODS = frozenset({"GET", "HEAD"})


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that refuses to follow redirects (302 passes through)."""

    def redirect_request(
        self,
        *args: object,  # noqa: ARG002
        **kwargs: object,  # noqa: ARG002
    ) -> None:
        # Fixed urllib override signature; arguments are intentionally unused.
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point: proxy one /oauth/* request to the home server."""
    try:
        base_url = get_beacon_reader().get_base_url()
    except (BeaconError, KeyError) as exc:
        log.error("Could not resolve home server base URL: %s", exc)
        return _error_response(502, "Home server address unavailable")

    request = _build_request(event, base_url)
    try:
        response = _opener.open(request, timeout=timeout_seconds())
    except urllib.error.HTTPError as exc:
        # Redirects and upstream error statuses pass through unchanged.
        return _build_result(exc.code, exc.headers.items(), exc.read())
    except OSError as exc:
        log.error("Forwarding %s to home server failed: %s", event.get("rawPath"), exc)
        return _error_response(502, "Home server did not respond")
    with response:
        return _build_result(response.status, response.headers.items(), response.read())


def _build_request(event: dict[str, Any], base_url: str) -> urllib.request.Request:
    method = (
        event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
    )
    path = event.get("rawPath", "/")
    query = event.get("rawQueryString", "")
    url = base_url + path + (f"?{query}" if query else "")

    headers = {
        name: value
        for name, value in (event.get("headers") or {}).items()
        if name.lower() not in _DROPPED_REQUEST_HEADERS
    }
    cookies = event.get("cookies") or []
    if cookies:
        headers["Cookie"] = "; ".join(cookies)

    data = None if method in _BODYLESS_METHODS else _decode_request_body(event)
    # base_url scheme is validated as https by BeaconReader.get_base_url.
    return urllib.request.Request(  # noqa: S310
        url=url, data=data, headers=headers, method=method
    )


def _decode_request_body(event: dict[str, Any]) -> bytes | None:
    body = event.get("body")
    if not body:
        return None
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _build_result(
    status: int, header_items: Iterable[tuple[str, str]], body: bytes
) -> dict[str, Any]:
    """Map an upstream response onto the API Gateway v2 response shape."""
    headers: dict[str, str] = {}
    cookies: list[str] = []
    content_type = ""
    for name, value in header_items:
        lowered = name.lower()
        if lowered in _DROPPED_RESPONSE_HEADERS:
            continue
        if lowered == "set-cookie":
            cookies.append(value)
            continue
        if lowered == "content-type":
            content_type = value
        headers[name] = value

    encoded_body, is_base64 = _encode_body(body, content_type)
    result: dict[str, Any] = {
        "statusCode": status,
        "headers": headers,
        "body": encoded_body,
        "isBase64Encoded": is_base64,
    }
    if cookies:
        result["cookies"] = cookies
    return result


def _encode_body(body: bytes, content_type: str) -> tuple[str, bool]:
    if _looks_textual(content_type):
        try:
            return body.decode("utf-8"), False
        except UnicodeDecodeError:
            log.debug("Body of type %s is not UTF-8; using base64", content_type)
    return base64.b64encode(body).decode("ascii"), True


def _looks_textual(content_type: str) -> bool:
    if not content_type:
        return True
    lowered = content_type.lower()
    return any(hint in lowered for hint in _TEXT_CONTENT_HINTS)


def _error_response(status: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
        "isBase64Encoded": False,
    }


def reset_warm_cache() -> None:
    """Drop warm-container caches (cold-start state; used by tests)."""
    reset_beacon_cache()
