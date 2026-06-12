"""Cached reader for the S3 endpoint beacon (``endpoint.json``).

The reader keeps the last ETag and the parsed beacon body in memory so warm
Lambda containers re-validate with a conditional GET (``If-None-Match``)
instead of re-downloading the object on every invocation. A 304 answer serves
the cached body; anything else refreshes the cache.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

log = logging.getLogger(__name__)

_DEFAULT_KEY = "endpoint.json"


class BeaconError(Exception):
    """Raised when the endpoint beacon cannot be read or is invalid."""


class BeaconReader:
    """Reads ``endpoint.json`` from S3 with warm-container ETag caching."""

    def __init__(self, s3_client: Any, bucket: str, key: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._key = key
        self._etag: str | None = None
        self._cached: dict[str, Any] | None = None

    def get_base_url(self) -> str:
        """Return the home-server base URL (no trailing slash) from the beacon.

        Only ``https://`` URLs are accepted (KONZEPT §9: the AWS→home leg
        carries bearer tokens and credentials). ``http://`` is allowed only
        when ``PANTAU_ALLOW_INSECURE_BEACON=true`` (local testing).
        """
        beacon = self._read_beacon()
        base_url = beacon.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise BeaconError("Beacon is missing a usable 'base_url'")
        insecure_ok = base_url.startswith("http://") and _allow_insecure_beacon()
        if not base_url.startswith("https://") and not insecure_ok:
            raise BeaconError(
                "Beacon 'base_url' must be an https URL "
                "(set PANTAU_ALLOW_INSECURE_BEACON=true to allow http)"
            )
        return base_url.rstrip("/")

    def _read_beacon(self) -> dict[str, Any]:
        request: dict[str, str] = {"Bucket": self._bucket, "Key": self._key}
        if self._etag is not None and self._cached is not None:
            request["IfNoneMatch"] = self._etag
        try:
            response = self._s3.get_object(**request)
        except ClientError as exc:
            if self._cached is not None and _is_not_modified(exc):
                log.debug("Beacon unchanged (ETag %s), using cached body", self._etag)
                return self._cached
            raise BeaconError("Failed to read beacon from S3") from exc
        except BotoCoreError as exc:
            raise BeaconError("Failed to read beacon from S3") from exc

        try:
            body = json.loads(response["Body"].read())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BeaconError("Beacon object is not valid JSON") from exc
        if not isinstance(body, dict):
            raise BeaconError("Beacon object is not a JSON object")

        self._etag = response.get("ETag")
        self._cached = body
        log.debug("Beacon refreshed (ETag %s)", self._etag)
        return body


def create_reader_from_env() -> BeaconReader:
    """Build a reader from PANTAU_BEACON_BUCKET / PANTAU_BEACON_KEY env vars."""
    bucket = os.environ["PANTAU_BEACON_BUCKET"]
    key = os.environ.get("PANTAU_BEACON_KEY", _DEFAULT_KEY)
    return BeaconReader(boto3.client("s3"), bucket, key)


def _allow_insecure_beacon() -> bool:
    value = os.environ.get("PANTAU_ALLOW_INSECURE_BEACON", "")
    return value.strip().lower() in ("1", "true", "yes")


def _is_not_modified(exc: ClientError) -> bool:
    error_code = exc.response.get("Error", {}).get("Code")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error_code in ("304", "NotModified") or status == 304
