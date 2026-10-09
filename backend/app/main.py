from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestTracingMiddleware
from app.db.session import dispose_database_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger = configure_logging(settings.log_level)
    logger.info("Application started")
    try:
        yield
    finally:
        await dispose_database_engine()
        logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(RequestTracingMiddleware)
app.include_router(api_v1_router)
app.exception_handler(HTTPException)(http_exception_handler)
app.exception_handler(RequestValidationError)(validation_exception_handler)
app.exception_handler(Exception)(unexpected_exception_handler)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Backend is running"}
