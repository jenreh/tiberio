"""Tests: body-size limit and key-event logging on POST /alexa/directive."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.interfaces.alexa.conftest import directive

from pantau.api.app import create_app
from pantau.composition import build_test_container
from pantau.config.settings import Settings

_LOGGER_NAME = "pantau.interfaces.alexa.directive_router"


@pytest.fixture
def small_body_client(devices_config: Path) -> TestClient:
    container = build_test_container(devices_config)
    settings = Settings(dev_mode=True, max_directive_body_bytes=256)
    app = create_app(settings=settings, container=container)
    return TestClient(app)


class TestBodySizeLimit:
    def test_oversized_body_returns_413(self, small_body_client: TestClient) -> None:
        body = {"directive": {"padding": "x" * 1000}}
        resp = small_body_client.post("/alexa/directive", json=body)
        assert resp.status_code == 413

    def test_small_body_passes_size_check(self, small_body_client: TestClient) -> None:
        resp = small_body_client.post("/alexa/directive", json={"directive": {}})
        # Fails later (no bearer token) — but not with 413
        assert resp.status_code == 401


class TestDirectiveKeyEventLogging:
    def test_logs_received_and_outcome_without_token(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            resp = client.post(
                "/alexa/directive",
                json=directive("Alexa.PowerController", "TurnOn", endpoint_id="zdf"),
            )
        assert resp.status_code == 200
        messages = [r.getMessage() for r in caplog.records]
        received = [m for m in messages if "Directive received" in m]
        assert received, messages
        assert "Alexa.PowerController" in received[0]
        assert "TurnOn" in received[0]
        assert "zdf" in received[0]
        assert any("Directive handled" in m for m in messages)
        # The bearer token must never appear in any log line
        assert all("test-bearer-token" not in m for m in messages)

    def test_error_outcome_logged_as_warning(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            resp = client.post(
                "/alexa/directive",
                json=directive(
                    "Alexa.PowerController", "TurnOn", endpoint_id="no-such-device"
                ),
            )
        assert resp.status_code == 200
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ErrorResponse" in r.getMessage() for r in warnings)
