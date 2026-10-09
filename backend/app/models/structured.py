"""Synthetic structured enterprise records for the structured-retrieval path (Part 8).

Access to these rows is decided inside the SQL that reads them
(``app/services/rag/structured.py``); nothing here grants access by itself.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import BigInteger, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A department project and its lead. Internal information: visible to active employees."""

    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class EmployeeCompensation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Confidential: readable only by the employee themselves and holders of hr:read."""

    __tablename__ = "employee_compensation"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    fiscal_year: Mapped[str] = mapped_column(String(20), nullable=False)
    annual_ctc_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
