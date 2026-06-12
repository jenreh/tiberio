"""S3BeaconPublisher — put_object payload, content type, and error mapping."""

from __future__ import annotations

import json
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from pantau.adapters.s3_beacon_publisher import S3BeaconPublisher
from pantau.domain.beacon import Beacon
from pantau.domain.errors import BeaconPublishError

BEACON = Beacon(
    base_url="https://tunnel.example.com",
    updated_at="2026-06-11T12:00:00+00:00",
)


class FakeS3Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {}


async def test_publish_puts_json_object_with_content_type() -> None:
    client = FakeS3Client()
    publisher = S3BeaconPublisher(
        bucket="pantau-alexa-beacon", key="endpoint.json", client=client
    )

    await publisher.publish(BEACON)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["Bucket"] == "pantau-alexa-beacon"
    assert call["Key"] == "endpoint.json"
    assert call["ContentType"] == "application/json"
    body = json.loads(call["Body"])
    assert body == {
        "base_url": "https://tunnel.example.com",
        "updated_at": "2026-06-11T12:00:00+00:00",
        "health": "ok",
    }


async def test_publish_maps_client_error_to_domain_error() -> None:
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
    )
    publisher = S3BeaconPublisher(bucket="b", key="k", client=FakeS3Client(error=error))

    with pytest.raises(BeaconPublishError):
        await publisher.publish(BEACON)


async def test_publish_maps_botocore_error_to_domain_error() -> None:
    publisher = S3BeaconPublisher(
        bucket="b", key="k", client=FakeS3Client(error=BotoCoreError())
    )

    with pytest.raises(BeaconPublishError):
        await publisher.publish(BEACON)
