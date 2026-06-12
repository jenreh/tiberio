"""Request-correlation logging: contextvar, filter, JSON formatter, configure.

``configure_logging`` is called once at app startup (see ``create_app``).
Every log record gets a ``request_id`` attribute injected from the active
request context (set by ``RequestIdMiddleware``), so log lines can be
correlated across a single Alexa directive or OAuth request.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from pantau.config.settings import Settings

#: Correlation id of the request currently being handled ("-" outside requests).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_TEXT_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Configure the root logger from settings (idempotent).

    Replaces any handler previously installed by this function, so repeated
    calls (e.g. multiple ``create_app`` invocations in tests) never stack
    duplicate handlers. Handlers owned by others (pytest, uvicorn) are kept.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RequestIdFilter())
    formatter: logging.Formatter = (
        JsonFormatter() if settings.log_json else logging.Formatter(_TEXT_FORMAT)
    )
    handler.setFormatter(formatter)
    handler._pantau_handler = True  # ty: ignore[unresolved-attribute]  # noqa: SLF001

    root.handlers = [
        h for h in root.handlers if not getattr(h, "_pantau_handler", False)
    ]
    root.addHandler(handler)
