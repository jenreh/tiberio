"""Tests for request-correlation logging setup (filter, formatter, configure)."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator

import pytest

from pantau.api.logging_setup import (
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    request_id_var,
)
from pantau.config.settings import Settings


def _make_record(
    msg: str = "hello %s", args: tuple = ("world",), level: int = logging.INFO
) -> logging.LogRecord:
    return logging.LogRecord("test.logger", level, __file__, 1, msg, args, None)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    level = root.level
    handlers = list(root.handlers)
    yield
    root.setLevel(level)
    root.handlers = handlers


class TestRequestIdFilter:
    def test_injects_request_id_from_contextvar(self) -> None:
        token = request_id_var.set("req-123")
        try:
            record = _make_record()
            assert RequestIdFilter().filter(record) is True
            assert record.request_id == "req-123"  # ty: ignore[unresolved-attribute]
        finally:
            request_id_var.reset(token)

    def test_default_when_no_request_active(self) -> None:
        record = _make_record()
        RequestIdFilter().filter(record)
        assert record.request_id == "-"  # ty: ignore[unresolved-attribute]


class TestJsonFormatter:
    def test_outputs_json_with_expected_fields(self) -> None:
        record = _make_record()
        record.request_id = "abc"
        out = json.loads(JsonFormatter().format(record))
        assert out["message"] == "hello world"
        assert out["level"] == "INFO"
        assert out["logger"] == "test.logger"
        assert out["request_id"] == "abc"
        assert "timestamp" in out

    def test_missing_request_id_defaults(self) -> None:
        out = json.loads(JsonFormatter().format(_make_record()))
        assert out["request_id"] == "-"

    def test_includes_exception_info(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                "test.logger",
                logging.ERROR,
                __file__,
                1,
                "failed",
                None,
                sys.exc_info(),
            )
        out = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in out["exc_info"]


class TestConfigureLogging:
    def _pantau_handlers(self) -> list[logging.Handler]:
        return [
            h
            for h in logging.getLogger().handlers
            if getattr(h, "_pantau_handler", False)
        ]

    def test_sets_level_from_settings(self) -> None:
        configure_logging(Settings(log_level="DEBUG"))
        assert logging.getLogger().level == logging.DEBUG

    def test_plain_formatter_by_default(self) -> None:
        configure_logging(Settings())
        (handler,) = self._pantau_handlers()
        assert not isinstance(handler.formatter, JsonFormatter)

    def test_json_flag_enables_json_formatter(self) -> None:
        configure_logging(Settings(log_json=True))
        (handler,) = self._pantau_handlers()
        assert isinstance(handler.formatter, JsonFormatter)

    def test_idempotent_no_duplicate_handlers(self) -> None:
        configure_logging(Settings())
        configure_logging(Settings())
        assert len(self._pantau_handlers()) == 1

    def test_handler_has_request_id_filter(self) -> None:
        configure_logging(Settings())
        (handler,) = self._pantau_handlers()
        assert any(isinstance(f, RequestIdFilter) for f in handler.filters)

    def test_plain_format_renders_request_id(self) -> None:
        configure_logging(Settings())
        (handler,) = self._pantau_handlers()
        token = request_id_var.set("req-fmt-1")
        try:
            record = _make_record()
            for f in handler.filters:
                f.filter(record)  # ty: ignore[unresolved-attribute]
            assert handler.formatter is not None
            assert "req-fmt-1" in handler.formatter.format(record)
        finally:
            request_id_var.reset(token)


class TestSettingsFlags:
    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.log_json is False
        assert settings.log_level == "INFO"
        assert settings.max_directive_body_bytes == 65536
