"""Alexa Smart-Home directive proxy Lambda.

Receives the Smart-Home event from Alexa, resolves the home-server base URL
from the S3 beacon (conditional GET, ETag cached in the warm container) and
forwards the directive JSON unchanged to ``{base_url}/alexa/directive``.

The request carries the timestamped HMAC-SHA256 headers the home server
verifies (see ``pantau/interfaces/alexa/directive_router.py``):
``X-Pantau-Timestamp`` (unix seconds) and ``X-Pantau-Signature`` over
``f"{timestamp}." + raw_body``. The shared secret comes from the
``PANTAU_SHARED_SECRET`` env var or — if ``PANTAU_SHARED_SECRET_SSM_PARAM``
is set — from SSM Parameter Store (decrypted, cached in the warm container).

On S3 or connection-level home-server failures a valid Alexa
``ErrorResponse`` event of type ``BRIDGE_UNREACHABLE`` is returned; a 401/403
from the home server maps to ``INVALID_AUTHORIZATION_CREDENTIAL`` so Alexa
prompts the user to re-link the account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

import boto3
from shared.beacon import BeaconError
from shared.runtime import get_beacon_reader, reset_beacon_cache, timeout_seconds

log = logging.getLogger(__name__)

_AUTH_FAILURE_STATUSES = (401, 403)

# Warm-container cache (survives across invocations of the same container).
_shared_secret: str | None = None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point: proxy one Alexa directive to the home server."""
    try:
        base_url = get_beacon_reader().get_base_url()
    except (BeaconError, KeyError) as exc:
        log.error("Could not resolve home server base URL: %s", exc)
        return _bridge_unreachable(event, "Home server address unavailable")

    body = json.dumps(event).encode("utf-8")
    # base_url scheme is validated as https by BeaconReader.get_base_url.
    request = urllib.request.Request(  # noqa: S310
        url=base_url + "/alexa/directive",
        data=body,
        headers=_build_headers(body),
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=timeout_seconds()
        ) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in _AUTH_FAILURE_STATUSES:
            log.warning("Home server rejected directive credentials: HTTP %d", exc.code)
            return _error_response(
                event,
                "INVALID_AUTHORIZATION_CREDENTIAL",
                "Home server rejected the account-linking credentials",
            )
        log.error("Home server returned HTTP %d for directive", exc.code)
        return _bridge_unreachable(event, "Home server did not respond")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.error("Forwarding directive to home server failed: %s", exc)
        return _bridge_unreachable(event, "Home server did not respond")


def _build_headers(body: bytes) -> dict[str, str]:
    """Content type plus the HMAC headers the home server verifies."""
    headers = {"Content-Type": "application/json"}
    secret = _get_shared_secret()
    if not secret:
        log.warning(
            "No shared secret configured; forwarding directive WITHOUT HMAC headers"
        )
        return headers
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    headers["X-Pantau-Timestamp"] = str(timestamp)
    headers["X-Pantau-Signature"] = signature
    return headers


def _get_shared_secret() -> str:
    global _shared_secret
    if _shared_secret is None:
        _shared_secret = _load_shared_secret()
    return _shared_secret


def _load_shared_secret() -> str:
    ssm_param = os.environ.get("PANTAU_SHARED_SECRET_SSM_PARAM")
    if ssm_param:
        log.info("Loading shared secret from SSM Parameter Store")
        response = boto3.client("ssm").get_parameter(
            Name=ssm_param, WithDecryption=True
        )
        return str(response["Parameter"]["Value"])
    return os.environ.get("PANTAU_SHARED_SECRET", "")


def _bridge_unreachable(event: dict[str, Any], message: str) -> dict[str, Any]:
    """Build an Alexa ErrorResponse event of type BRIDGE_UNREACHABLE."""
    return _error_response(event, "BRIDGE_UNREACHABLE", message)


def _error_response(
    event: dict[str, Any], error_type: str, message: str
) -> dict[str, Any]:
    """Build an Alexa ErrorResponse event of the given *error_type*."""
    directive = event.get("directive") if isinstance(event, dict) else None
    directive = directive if isinstance(directive, dict) else {}
    header = directive.get("header") or {}
    endpoint = directive.get("endpoint") or {}

    error_header: dict[str, Any] = {
        "namespace": "Alexa",
        "name": "ErrorResponse",
        "messageId": str(uuid.uuid4()),
        "payloadVersion": "3",
    }
    correlation_token = header.get("correlationToken")
    if correlation_token is not None:
        error_header["correlationToken"] = correlation_token

    error_event: dict[str, Any] = {
        "header": error_header,
        "payload": {"type": error_type, "message": message},
    }
    endpoint_id = endpoint.get("endpointId")
    if endpoint_id is not None:
        error_event["endpoint"] = {"endpointId": endpoint_id}

    return {"event": error_event}


def reset_warm_cache() -> None:
    """Drop warm-container caches (cold-start state; used by tests)."""
    global _shared_secret
    reset_beacon_cache()
    _shared_secret = None
