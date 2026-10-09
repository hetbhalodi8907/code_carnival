import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.db.session import check_database_connection


router = APIRouter()
logger = logging.getLogger("app.database")


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready")
async def ready() -> Response:
    try:
        await check_database_connection()
    except Exception:
        logger.error("PostgreSQL readiness check failed")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": settings.app_name,
                "version": settings.app_version,
                "database": "unavailable",
            },
        )

    return {
        "status": "ready",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "available",
    }
