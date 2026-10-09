"""Credential verification. Every failure is reported identically to callers."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.security import burn_password_check, verify_password


logger = logging.getLogger("app.auth")


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def authenticate_user(session: AsyncSession, email: str, password: str) -> models.User | None:
    """Return the active user whose password matches, otherwise None.

    Unknown emails, wrong passwords, inactive accounts and accounts without a password
    all return None, and unknown emails still spend a full hash verification so the
    response time does not reveal which emails exist. Only the failure category is
    logged, never the email or password.
    """
    user = await session.scalar(
        select(models.User).where(func.lower(models.User.email) == normalize_email(email))
    )
    if user is None:
        burn_password_check(password)
        logger.info("Login failed reason=unknown_account")
        return None
    if not verify_password(password, user.password_hash):
        logger.info("Login failed reason=invalid_credentials user_id=%s", user.id)
        return None
    if not user.is_active:
        logger.info("Login failed reason=inactive_account user_id=%s", user.id)
        return None
    return user
