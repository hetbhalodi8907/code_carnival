"""Password hashing and JWT access tokens.

Passwords are hashed with Argon2id (argon2-cffi defaults, RFC 9106). Access tokens are
HMAC-signed JWTs that carry only the user identifier and timing claims; roles,
permissions and document grants are always resolved server-side from the database.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from functools import cache
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings


ACCESS_TOKEN_TYPE = "access"
REQUIRED_CLAIMS = ("sub", "type", "iat", "exp")

_password_hasher = PasswordHasher()


class AuthConfigurationError(RuntimeError):
    """Raised when authentication is used without a configured JWT secret."""


class InvalidTokenError(ValueError):
    """Raised for any token that is missing, malformed, tampered with or expired."""


def hash_password(password: str) -> str:
    """Return an Argon2id hash in PHC string format (salt and parameters included)."""
    if not password:
        raise ValueError("Password must not be empty.")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time verification; unknown or malformed hashes never verify."""
    if not password or not password_hash:
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return _password_hasher.hash(secrets.token_urlsafe(32))


def burn_password_check(password: str) -> None:
    """Spend the same work as a real check so unknown emails are not revealed by timing."""
    verify_password(password or "x", _dummy_hash())


def _secret() -> str:
    secret = settings.jwt_secret_key.get_secret_value() if settings.jwt_secret_key else ""
    if not secret:
        # An empty JWT_SECRET_KEY= line counts as not configured, never as an empty key.
        raise AuthConfigurationError("JWT_SECRET_KEY is not configured.")
    return secret


def create_access_token(user_id: UUID, *, now: datetime | None = None) -> tuple[str, int]:
    """Issue a signed access token; returns the token and its lifetime in seconds."""
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
    }
    token = jwt.encode(payload, _secret(), algorithm=settings.jwt_algorithm)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> UUID:
    """Validate signature, algorithm, expiry and token type; return the user identifier."""
    secret = _secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            # Only the configured algorithm is accepted, which rejects "none" and swaps.
            algorithms=[settings.jwt_algorithm],
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("The access token is invalid or expired.") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("The token is not an access token.")
    try:
        return UUID(str(payload["sub"]))
    except ValueError as exc:
        raise InvalidTokenError("The token subject is invalid.") from exc
