"""S3 beacon publisher — writes endpoint.json to the beacon bucket (KONZEPT §9)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from pantau.domain.errors import BeaconPublishError

if TYPE_CHECKING:
    from pantau.domain.beacon import Beacon

log = logging.getLogger(__name__)


class S3BeaconPublisher:
    """Implements BeaconPublisherPort via boto3 ``put_object``.

    boto3 is synchronous — calls run in a worker thread via
    ``asyncio.to_thread``. The object body never contains secrets.
    """

    def __init__(
        self,
        bucket: str,
        key: str,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._key = key
        self._client = client or boto3.client("s3", region_name=region)

    async def publish(self, beacon: Beacon) -> None:
        body = beacon.model_dump_json().encode("utf-8")
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=self._key,
                Body=body,
                ContentType="application/json",
            )
        except (BotoCoreError, ClientError) as exc:
            raise BeaconPublishError(
                f"Failed to publish beacon to s3://{self._bucket}/{self._key}: {exc}"
            ) from exc
        log.debug("Beacon written to s3://%s/%s", self._bucket, self._key)
