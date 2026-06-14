"""HTTP middleware that traces every request.

Assigns each request a correlation id (honoring an inbound ``X-Request-ID`` from
a proxy, otherwise generating one), propagates it into the logging context so
every log line emitted while handling the request carries the same id, and logs
the request start/end with method, path, status, and duration.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from logging_config import reset_request_id, set_request_id

logger = logging.getLogger("app.request")

RequestIdHeader = "X-Request-ID"


async def request_context_log_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Trace a request end-to-end with a propagated request id."""
    request_id = request.headers.get(RequestIdHeader) or uuid.uuid4().hex
    token = set_request_id(request_id)
    start = time.perf_counter()

    logger.info(
        "request.start method=%s path=%s",
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "request.error method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        # Re-raise so FastAPI's registered exception handlers still run.
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request.end method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers[RequestIdHeader] = request_id
        return response
    finally:
        # Always reset so the id never bleeds into another request's context.
        reset_request_id(token)
