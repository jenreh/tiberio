"""Warm-container runtime helpers shared by both Lambda handlers.

Holds the module-global :class:`BeaconReader` cache (survives across
invocations of the same container) and the HTTP timeout configuration.
"""

from __future__ import annotations

import os

from shared.beacon import BeaconReader, create_reader_from_env

_DEFAULT_TIMEOUT_SECONDS = 6.0

# Warm-container cache (survives across invocations of the same container).
_beacon_reader: BeaconReader | None = None


def timeout_seconds() -> float:
    """Upstream HTTP timeout from PANTAU_HTTP_TIMEOUT_SECONDS (default 6 s)."""
    return float(
        os.environ.get("PANTAU_HTTP_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS)
    )


def get_beacon_reader() -> BeaconReader:
    """Return the cached beacon reader, creating it on the first call."""
    global _beacon_reader
    if _beacon_reader is None:
        _beacon_reader = create_reader_from_env()
    return _beacon_reader


def reset_beacon_cache() -> None:
    """Drop the cached beacon reader (cold-start state; used by tests)."""
    global _beacon_reader
    _beacon_reader = None
