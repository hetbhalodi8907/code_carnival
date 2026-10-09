from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import AUTH_NOT_CONFIGURED, get_current_user
from app.core.security import AuthConfigurationError, create_access_token
from app.db.session import get_session_factory
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.authentication import authenticate_user
from app.services.authorization import AuthenticatedUser


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("app.auth")

INVALID_CREDENTIALS = "Invalid email or password."


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"description": "Invalid credentials or inactive account (indistinguishable)."},
        503: {"description": "Authentication is not configured on the server."},
    },
)
async def login(
    request: LoginRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> TokenResponse:
    """Exchange email and password for a short-lived bearer access token."""
    async with session_factory() as session:
        user = await authenticate_user(session, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token, expires_in = create_access_token(user.id)
    except AuthConfigurationError as exc:
        logger.error("Login unavailable reason=jwt_not_configured")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_NOT_CONFIGURED) from exc

    logger.info("Login succeeded user_id=%s", user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserResponse)
async def read_current_user(user: AuthenticatedUser = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the authenticated user's identity, roles and permissions from the database."""
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=sorted(user.roles),
        permissions=sorted(user.permissions),
    )
