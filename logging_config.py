"""Centralized logging configuration for the FastAPI app.

Standard-library only (no extra dependencies). Configures logging via
``logging.config.dictConfig`` with:

- Console + size-based rotating file handlers.
- JSON structured output by default (configurable to plain text).
- A request-ID correlation id, propagated into every log record emitted during
  a request via :mod:`contextvars`, so a whole request can be traced end-to-end.
- Unified uvicorn loggers (they propagate to the root handlers).

This module deliberately avoids importing FastAPI/Starlette so it stays cheap to
import very early (before the app is created).
"""

from __future__ import annotations

import contextvars
import json
import logging
import logging.config
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Request-id context
# ---------------------------------------------------------------------------
# contextvars are async-task-safe: each request runs in its own context, so the
# value set at middleware entry is visible to every awaited coroutine in that
# request and isolated from concurrent requests.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def set_request_id(value: str) -> contextvars.Token[str]:
    """Set the request id for the current context and return a reset token."""
    return request_id_ctx.set(value)


def get_request_id() -> str:
    """Return the request id for the current context (``"-"`` if unset)."""
    return request_id_ctx.get()


def reset_request_id(token: contextvars.Token[str]) -> None:
    """Restore the previous request id using the token from :func:`set_request_id`."""
    request_id_ctx.reset(token)


# ---------------------------------------------------------------------------
# Filter: stamp every record with the current request id
# ---------------------------------------------------------------------------
class RequestIdFilter(logging.Filter):
    """Attach ``request_id`` to every log record.

    Attached to all handlers so the attribute always exists, even for records
    emitted outside a request (startup, uvicorn boot, etc.), which get ``"-"``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


# ---------------------------------------------------------------------------
# JSON formatter (stdlib only)
# ---------------------------------------------------------------------------
# Fields already present on a fresh LogRecord; anything extra passed via
# ``logger.info(..., extra={...})`` will be merged into the JSON payload.
_RESERVED_RECORD_ATTRS = frozenset(
    logging.makeLogRecord({}).__dict__.keys()
) | {"request_id", "message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render each log record as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Merge any user-supplied `extra=` fields.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# dictConfig builder
# ---------------------------------------------------------------------------
_PLAIN_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "req=%(request_id)s | %(message)s"
)


def build_logging_config(settings: Any) -> dict[str, Any]:
    """Build the ``logging.config.dictConfig`` dictionary from settings."""
    formatter_name = "json" if settings.log_format == "json" else "plain"

    root_handlers: list[str] = []
    if settings.log_to_console:
        root_handlers.append("console")
    if settings.log_to_file:
        root_handlers.append("file")

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.log_level,
            "formatter": formatter_name,
            "filters": ["request_id"],
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": settings.log_level,
            "formatter": formatter_name,
            "filters": ["request_id"],
            "filename": str(Path(settings.log_dir) / settings.log_file_name),
            "maxBytes": settings.log_max_bytes,
            "backupCount": settings.log_backup_count,
            "encoding": "utf-8",
            "delay": True,  # don't open the file until the first emit
        },
    }

    access_level = settings.log_level if settings.log_uvicorn_access else "WARNING"

    return {
        "version": 1,
        # Keep loggers that were created before dictConfig (e.g. email_utils').
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "logging_config.RequestIdFilter"},
        },
        "formatters": {
            "plain": {
                "format": _PLAIN_FORMAT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {"()": "logging_config.JsonFormatter"},
        },
        "handlers": handlers,
        # Handlers live ONLY on root; named loggers propagate to it. This
        # guarantees a single emission per record (no double-logging).
        "root": {
            "level": settings.log_level,
            "handlers": root_handlers,
        },
        "loggers": {
            "uvicorn": {"level": settings.log_level, "handlers": [], "propagate": True},
            "uvicorn.error": {
                "level": settings.log_level,
                "handlers": [],
                "propagate": True,
            },
            "uvicorn.access": {
                "level": access_level,
                "handlers": [],
                "propagate": True,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": [],
                "propagate": True,
            },
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def setup_logging(settings: Any = None) -> None:
    """Configure application-wide logging.

    Call this once at process startup, before the app is created and before any
    log records are emitted. Safe to call again (dictConfig replaces config),
    which happens under ``fastapi dev --reload``.
    """
    if settings is None:
        from config import settings as _settings

        settings = _settings

    if settings.log_to_file:
        # The RotatingFileHandler needs the directory to exist before its first
        # emit; create it up front (delay=True defers file creation only).
        Path(settings.log_dir).mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(build_logging_config(settings))
