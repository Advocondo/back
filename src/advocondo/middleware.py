import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

import sentry_sdk
from fastapi import Request, Response

from advocondo.logging_config import request_id_var

logger = logging.getLogger("advocondo.requests")

# Aceita o X-Request-ID de um proxy só se for um identificador simples.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Health checks rodam a cada poucos segundos; não poluem os logs em INFO.
_QUIET_PATHS = {"/health", "/health/ready"}


def resolve_request_id(header: str | None) -> str:
    if header and _VALID_REQUEST_ID.match(header):
        return header
    return uuid.uuid4().hex


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = resolve_request_id(request.headers.get("x-request-id"))
    token = request_id_var.set(request_id)
    sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
    start = time.perf_counter()
    fields = {"method": request.method, "path": request.url.path}
    try:
        response = await call_next(request)
    except Exception:
        # O Sentry e o handler padrão do Starlette (500) cuidam do resto.
        logger.exception(
            "request failed",
            extra={**fields, "status_code": 500, "duration_ms": _ms_since(start)},
        )
        raise
    finally:
        request_id_var.reset(token)

    response.headers["X-Request-ID"] = request_id
    level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
    if response.status_code >= 500:
        level = logging.ERROR
    logger.log(
        level,
        "request",
        extra={
            **fields,
            "status_code": response.status_code,
            "duration_ms": _ms_since(start),
            "request_id": request_id,
        },
    )
    return response


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
