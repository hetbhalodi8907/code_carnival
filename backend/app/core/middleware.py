import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.exceptions import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)


REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LOG_KEY = "request_id"


def generate_request_id() -> str:
    """Create a safe, opaque identifier for request tracing."""
    return str(uuid.uuid4())


def get_request_id(request: Request) -> str:
    """Return a valid supplied request ID or a newly generated safe ID."""
    supplied_id = request.headers.get(REQUEST_ID_HEADER)
    if supplied_id is None:
        return generate_request_id()

    try:
        return str(uuid.UUID(supplied_id))
    except (ValueError, AttributeError):
        return generate_request_id()


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and measure request duration without logging bodies."""

    def __init__(self, app: Callable[[Request], Awaitable[Response]]) -> None:
        super().__init__(app)
        self.logger = logging.getLogger("app.middleware")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = get_request_id(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = 500
        response: Response

        try:
            response = await call_next(request)
            status_code = response.status_code
        except RequestValidationError as exc:
            status_code = 422
            response = validation_exception_handler(request, exc)
        except HTTPException as exc:
            status_code = exc.status_code
            response = http_exception_handler(request, exc)
        except Exception as exc:
            status_code = 500
            response = unexpected_exception_handler(request, exc)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            self.logger.info(
                "HTTP request completed method=%s path=%s status=%s "
                "duration_ms=%.2f request_id=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                request_id,
            )

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
