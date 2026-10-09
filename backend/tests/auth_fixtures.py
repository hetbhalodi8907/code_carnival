"""Authentication helpers for tests.

The JWT secret is random per test run, so no weak deterministic secret can become a
default anywhere.
"""

import secrets
from unittest.mock import patch
from uuid import UUID

from pydantic import SecretStr

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.services.authorization import AuthenticatedUser


TEST_JWT_SECRET = SecretStr(secrets.token_urlsafe(48))


def jwt_secret_patch() -> object:
    return patch.object(settings, "jwt_secret_key", TEST_JWT_SECRET)


def bearer_headers(user_id: UUID) -> dict[str, str]:
    with jwt_secret_patch():
        token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def principal(user_id: UUID, *permissions: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        email=f"principal-{user_id}@example.invalid",
        full_name="Test Principal",
        roles=frozenset(),
        permissions=frozenset(permissions),
    )


def override_current_user(user: AuthenticatedUser) -> None:
    """Stand in for token validation in tests that exercise endpoint behaviour.

    Authentication itself is covered by tests/test_auth.py. Document access is still
    enforced by the database for ``user.id``.
    """
    app.dependency_overrides[get_current_user] = lambda: user


def clear_current_user_override() -> None:
    app.dependency_overrides.pop(get_current_user, None)
