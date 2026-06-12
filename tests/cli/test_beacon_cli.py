"""Tests for the pantau-beacon CLI."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import pantau.cli.beacon as beacon_cli
from pantau.config.settings import Settings
from pantau.domain.beacon import Beacon
from pantau.domain.errors import BeaconPublishError

runner = CliRunner()


class _FakePublisher:
    """Records the published beacon instead of writing to S3."""

    def __init__(self, *, bucket: str, key: str, region: str | None = None) -> None:
        self.bucket = bucket
        self.key = key
        self.region = region
        self.published: Beacon | None = None

    async def publish(self, beacon: Beacon) -> None:
        self.published = beacon


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, _FakePublisher]:
    """Patch the S3 publisher with a recording fake; expose the instance."""
    holder: dict[str, _FakePublisher] = {}

    def _factory(*, bucket: str, key: str, region: str | None = None) -> _FakePublisher:
        holder["publisher"] = _FakePublisher(bucket=bucket, key=key, region=region)
        return holder["publisher"]

    monkeypatch.setattr(beacon_cli, "S3BeaconPublisher", _factory)
    return holder


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> None:
    monkeypatch.setattr(beacon_cli, "get_settings", lambda: Settings(**kwargs))


class TestPublishCommand:
    def test_publish_with_explicit_options(
        self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, _FakePublisher]
    ) -> None:
        _patch_settings(monkeypatch)
        result = runner.invoke(
            beacon_cli.app,
            [
                "publish",
                "--base-url",
                "https://tunnel.example.com",
                "--bucket",
                "my-bucket",
                "--key",
                "ep.json",
                "--region",
                "us-east-1",
            ],
        )
        assert result.exit_code == 0
        publisher = captured["publisher"]
        assert publisher.published is not None
        assert publisher.published.base_url == "https://tunnel.example.com"
        assert (publisher.bucket, publisher.key, publisher.region) == (
            "my-bucket",
            "ep.json",
            "us-east-1",
        )
        assert "s3://my-bucket/ep.json" in result.output

    def test_publish_falls_back_to_settings(
        self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, _FakePublisher]
    ) -> None:
        _patch_settings(
            monkeypatch,
            public_base_url="https://home.example.com",
            s3_beacon_bucket="settings-bucket",
            s3_beacon_key="endpoint.json",
        )
        result = runner.invoke(beacon_cli.app, ["publish"])
        assert result.exit_code == 0
        publisher = captured["publisher"]
        assert publisher.published is not None
        assert publisher.published.base_url == "https://home.example.com"
        assert publisher.bucket == "settings-bucket"

    def test_publish_without_base_url_fails(
        self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, _FakePublisher]
    ) -> None:
        _patch_settings(monkeypatch, public_base_url="")
        result = runner.invoke(beacon_cli.app, ["publish"])
        assert result.exit_code == 1
        assert "no base URL" in result.output
        assert "publisher" not in captured

    def test_publish_error_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_settings(monkeypatch)

        class _FailingPublisher:
            def __init__(self, **_: object) -> None: ...

            async def publish(self, beacon: Beacon) -> None:
                raise BeaconPublishError("s3 boom")

        monkeypatch.setattr(beacon_cli, "S3BeaconPublisher", _FailingPublisher)
        result = runner.invoke(
            beacon_cli.app, ["publish", "--base-url", "https://x.example.com"]
        )
        assert result.exit_code == 1
        assert "s3 boom" in result.output
