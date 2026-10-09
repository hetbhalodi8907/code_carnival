import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger("app.exceptions")


def error_response(
    code: str,
    message: str,
    request_id: str,
    *,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        error["details"] = details

    return JSONResponse(status_code=500, content={"error": error})


def http_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
        headers=headers,
    )


def validation_error_response(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details: list[dict[str, Any]] = []
    for validation_error in exc.errors():
        location = validation_error.get("loc", [])
        location_text = ".".join(str(part) for part in location) or "request"
        details.append(
            {
                "location": location_text,
                "message": validation_error.get("msg", "Invalid request value"),
            }
        )

    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "request_id": request_id,
                "details": details,
            }
        },
    )


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    code = "HTTP_ERROR"
    return http_error_response(
        exc.status_code,
        code,
        exc.detail if isinstance(exc.detail, str) else "Request failed.",
        request_id,
        # Preserves e.g. WWW-Authenticate on 401 responses.
        headers=getattr(exc, "headers", None),
    )


def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.info(
        "Request validation failed method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        getattr(request.state, "request_id", "unknown"),
    )
    return validation_error_response(request, exc)


def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "Unhandled exception method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        request_id,
        exc_info=exc,
    )
    return error_response(
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
        request_id,
    )
