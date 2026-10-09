"""Reusable FastAPI security dependencies.

Identity comes only from a validated bearer token; roles and permissions come only
from the database. Request bodies, query parameters and headers other than
Authorization are never consulted for identity.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import AuthConfigurationError, InvalidTokenError, decode_access_token
from app.db.session import get_session_factory
from app.services.authorization import AuthenticatedUser, load_authenticated_user


logger = logging.getLogger("app.auth")

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Access token from POST /api/v1/auth/login, sent as `Authorization: Bearer <token>`.",
)

AUTHENTICATION_REQUIRED = "Authentication is required."
INVALID_TOKEN = "The access token is invalid or expired."
AUTH_NOT_CONFIGURED = "Authentication is not configured."
PERMISSION_DENIED = "You do not have permission to perform this action."


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AuthenticatedUser:
    """Validate the bearer token and return the active user's server-side context."""
    if credentials is None or not credentials.credentials:
        logger.info("Authentication failed reason=missing_token request_id=%s", _request_id(request))
        raise _unauthorized(AUTHENTICATION_REQUIRED)

    try:
        user_id = decode_access_token(credentials.credentials)
    except AuthConfigurationError as exc:
        logger.error("Authentication unavailable reason=jwt_not_configured")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_NOT_CONFIGURED) from exc
    except InvalidTokenError as exc:
        logger.info("Authentication failed reason=invalid_token request_id=%s", _request_id(request))
        raise _unauthorized(INVALID_TOKEN) from exc

    async with session_factory() as session:
        user = await load_authenticated_user(session, user_id)
    if user is None:
        # Unknown or deactivated accounts cannot keep using previously issued tokens.
        logger.info("Authentication failed reason=inactive_or_unknown_user request_id=%s", _request_id(request))
        raise _unauthorized(INVALID_TOKEN)
    return user


def require_permission(resource: str, action: str) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Dependency factory: the current user must hold ``resource:action`` via a role."""

    async def dependency(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not user.has_permission(resource, action):
            logger.info(
                "Authorization denied permission=%s:%s user_id=%s request_id=%s",
                resource,
                action,
                user.id,
                _request_id(request),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERMISSION_DENIED)
        return user

    return dependency
