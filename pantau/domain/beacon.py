"""Beacon — the endpoint announcement written to S3 (KONZEPT §9)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Beacon(BaseModel):
    """Public reachability record for the home server.

    Published as ``endpoint.json`` so the AWS edge (Lambda proxy) can
    discover the current tunnel URL. Never contains secrets.
    """

    model_config = ConfigDict(frozen=True)

    base_url: str
    updated_at: str  # ISO-8601 timestamp
    health: str = "ok"
