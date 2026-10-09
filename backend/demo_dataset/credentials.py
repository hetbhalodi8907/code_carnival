"""Development-only password setup for the synthetic demo users.

Only users whose identifiers are demo identifiers are touched, and passwords are
stored only as Argon2id hashes (the application's normal hashing). Two modes:

- a shared, operator-chosen password for all demo users (DEMO_USER_PASSWORD);
- the six fixed HACKATHON demo accounts below: one active seeded user per role, with
  intentionally public passwords for local presentations. They are not production
  credentials, and setup refuses to run when APP_ENV is production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.core.config import settings
from app.core.security import hash_password, verify_password
from demo_dataset.seeder import DemoDatasetError
from demo_dataset.spec import ROLES, USERS, user_by_email


MIN_DEMO_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class HackathonAccount:
    role: str
    label: str
    email: str
    password: str
    demonstrates: str


# LOCAL / HACKATHON DEMO USE ONLY. Mirrored by frontend/src/config/demoAccounts.ts
# (a test keeps the two in sync). Each email is a real, active seeded demo user.
HACKATHON_ACCOUNTS: tuple[HackathonAccount, ...] = (
    HackathonAccount(
        "SUPER_ADMIN",
        "CEO / Super Admin",
        "ishaan.malhotra@nexora.example",
        "DemoCEO@2026",
        "Broad access, granted only through explicit document grants (no hidden bypass).",
    ),
    HackathonAccount(
        "HR_MANAGER",
        "HR Manager",
        "meera.iyer@nexora.example",
        "DemoHR@2026",
        "HR policy and compensation statements; Finance reports are not retrieved.",
    ),
    HackathonAccount(
        "FINANCE_MANAGER",
        "Finance Manager",
        "vikram.nair@nexora.example",
        "DemoFinance@2026",
        "Finance and procurement reports; the confidential HR policy is not retrieved.",
    ),
    HackathonAccount(
        "ENGINEERING_MANAGER",
        "Engineering Manager",
        "ananya.rao@nexora.example",
        "DemoEngineering@2026",
        "Engineering guidelines and IT access policy; the Security policy is not retrieved.",
    ),
    HackathonAccount(
        "SECURITY_MANAGER",
        "Security Manager",
        "devika.krishnan@nexora.example",
        "DemoSecurity@2026",
        "Security and IT access-control policies; HR and Finance are not retrieved.",
    ),
    HackathonAccount(
        "EMPLOYEE",
        "Employee",
        "kabir.sethi@nexora.example",
        "DemoEmployee@2026",
        "Company-wide documents and his own compensation statement; a colleague's is not.",
    ),
)

MIN_HACKATHON_PASSWORD_LENGTH = 10
_PASSWORD_CLASSES = (r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9]")


@dataclass
class CredentialReport:
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)


def _refuse_production() -> None:
    if settings.app_env.lower() == "production":
        raise DemoDatasetError("Demo credentials cannot be managed when APP_ENV is production.")


async def set_demo_passwords(
    session_factory: async_sessionmaker[AsyncSession],
    password: str,
) -> CredentialReport:
    """Give every demo user the operator-supplied password (hashed). Idempotent."""
    _refuse_production()
    if len(password) < MIN_DEMO_PASSWORD_LENGTH:
        raise DemoDatasetError(
            f"The demo password must be at least {MIN_DEMO_PASSWORD_LENGTH} characters."
        )

    report = CredentialReport()
    async with session_factory() as session:
        for spec in USERS:
            user = await session.get(models.User, spec.id)
            if user is None or user.email != spec.email:
                raise DemoDatasetError(
                    "Demo users are missing or altered; run scripts/generate_demo_dataset.py first."
                )
            if verify_password(password, user.password_hash):
                report.unchanged.append(spec.email)
                continue
            user.password_hash = hash_password(password)
            report.updated.append(spec.email)
        await session.commit()
    return report


def validate_hackathon_accounts(accounts: tuple[HackathonAccount, ...] = HACKATHON_ACCOUNTS) -> None:
    """Check the fixed accounts against the dataset spec: one ACTIVE user per role."""
    users = user_by_email()
    roles = [account.role for account in accounts]
    if sorted(roles) != sorted(role.name for role in ROLES):
        raise DemoDatasetError("Hackathon accounts must cover every role exactly once.")
    for account in accounts:
        user = users.get(account.email)
        if user is None:
            raise DemoDatasetError(f"{account.email} is not a seeded demo user.")
        if user.role != account.role:
            raise DemoDatasetError(f"{account.email} does not hold the {account.role} role.")
        if not user.is_active:
            raise DemoDatasetError(f"{account.email} is inactive and cannot be a demo account.")
        if len(account.password) < MIN_HACKATHON_PASSWORD_LENGTH or not all(
            re.search(pattern, account.password) for pattern in _PASSWORD_CLASSES
        ):
            raise DemoDatasetError(f"The demo password for {account.label} is too weak.")


async def set_hackathon_passwords(
    session_factory: async_sessionmaker[AsyncSession],
    accounts: tuple[HackathonAccount, ...] = HACKATHON_ACCOUNTS,
) -> CredentialReport:
    """Hash and store the fixed demo passwords for the six hackathon accounts. Idempotent.

    Each account is re-checked against the database (exists, active, holds the role)
    before its password is set; no other user is touched.
    """
    _refuse_production()
    validate_hackathon_accounts(accounts)
    users = user_by_email()

    report = CredentialReport()
    async with session_factory() as session:
        for account in accounts:
            spec = users[account.email]
            user = await session.get(models.User, spec.id)
            if user is None or user.email != account.email or not user.is_active:
                raise DemoDatasetError(
                    f"{account.email} is missing or inactive; run scripts/generate_demo_dataset.py first."
                )
            roles = set(
                await session.scalars(
                    select(models.Role.name)
                    .join(models.UserRole, models.UserRole.role_id == models.Role.id)
                    .where(models.UserRole.user_id == user.id)
                )
            )
            if roles != {account.role}:
                raise DemoDatasetError(f"{account.email} does not hold exactly the {account.role} role.")
            if verify_password(account.password, user.password_hash):
                report.unchanged.append(account.email)
                continue
            user.password_hash = hash_password(account.password)
            report.updated.append(account.email)
        await session.commit()
    return report


async def clear_demo_passwords(session_factory: async_sessionmaker[AsyncSession]) -> CredentialReport:
    """Remove password hashes from demo users so they can no longer sign in."""
    _refuse_production()
    report = CredentialReport()
    async with session_factory() as session:
        for spec in USERS:
            user = await session.get(models.User, spec.id)
            if user is not None and user.password_hash is not None:
                user.password_hash = None
                report.cleared.append(spec.email)
        await session.commit()
    return report
