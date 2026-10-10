"""GET /api/v1/dashboard/overview: the signed-in account's role-aware dashboard (read-only)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_current_user
from app.db.session import get_session_factory
from app.schemas.dashboard import DashboardOverview
from app.services.authorization import AuthenticatedUser
from app.services.dashboard.service import DashboardService


logger = logging.getLogger("app.dashboard")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_UNAVAILABLE = "The dashboard is temporarily unavailable."


@router.get(
    "/overview",
    response_model=DashboardOverview,
    responses={
        401: {"description": "Authentication is required or the token is invalid."},
        503: {"description": "The dashboard data could not be read."},
    },
)
async def dashboard_overview(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> DashboardOverview:
    """Aggregates computed by the database for the account in the bearer token.

    Identity, roles and permissions come only from the verified token and the database; the
    request has no parameters. Sections the account may not read are ``null``. No LLM is used.
    """
    try:
        return await DashboardService(session_factory).overview(user)
    except SQLAlchemyError as exc:
        logger.error(
            "Dashboard query failed error_type=%s request_id=%s", type(exc).__name__, getattr(request.state, "request_id", "unknown")
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=DASHBOARD_UNAVAILABLE) from None
