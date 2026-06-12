"""Beacon publisher wiring in the composition root.

Pins the production branch: enabled settings must wire the real S3 adapter
with the configured bucket/key (a typo here would ship silently otherwise).
boto3 is stubbed so no credential chain or AWS call is involved.
"""

from __future__ import annotations

import pytest

import pantau.adapters.s3_beacon_publisher as s3_module
from pantau.adapters.mock_beacon_publisher import MockBeaconPublisher
from pantau.adapters.s3_beacon_publisher import S3BeaconPublisher
from pantau.composition import _build_beacon_publisher
from pantau.config.settings import Settings


class _FakeBoto3:
    @staticmethod
    def client(
        service_name: str,  # noqa: ARG004
        region_name: str | None = None,  # noqa: ARG004
    ) -> object:
        return object()


def test_enabled_beacon_wires_s3_publisher_with_configured_bucket_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(s3_module, "boto3", _FakeBoto3)
    settings = Settings(
        beacon_enabled=True,
        public_base_url="https://tunnel.example.com",
        s3_beacon_bucket="my-beacon-bucket",
        s3_beacon_key="my-endpoint.json",
    )

    publisher = _build_beacon_publisher(settings)

    assert isinstance(publisher, S3BeaconPublisher)
    assert publisher._bucket == "my-beacon-bucket"  # noqa: SLF001
    assert publisher._key == "my-endpoint.json"  # noqa: SLF001


def test_disabled_beacon_wires_mock_publisher() -> None:
    publisher = _build_beacon_publisher(Settings(beacon_enabled=False))

    assert isinstance(publisher, MockBeaconPublisher)
