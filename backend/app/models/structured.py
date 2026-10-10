"""Synthetic structured enterprise records for the structured-retrieval path (Part 8).

Access to these rows is decided inside the SQL that reads them
(``app/services/rag/structured.py``); nothing here grants access by itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
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


# --- Dashboard demo data (fictional Nexora records; see backend/demo_dataset/dashboard.py) ---------
# Read by the dashboard API (app/services/dashboard) behind explicit permission checks. Nothing
# here grants access by itself, and nothing here holds credentials or personal compensation.


class ProjectBudget(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The approved budget of one project, in the currency recorded on the row."""

    __tablename__ = "project_budgets"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    fiscal_year: Mapped[str] = mapped_column(String(20), nullable=False)
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    __table_args__ = (CheckConstraint("approved_amount >= 0", name="ck_project_budgets_amount_nonneg"),)


class ProjectExpense(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One recorded expense. Only ``Approved`` expenses count as actual spending."""

    __tablename__ = "project_expenses"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_project_expenses_amount_nonneg"),
        CheckConstraint("status IN ('Approved', 'Pending', 'Rejected')", name="ck_project_expenses_status"),
    )


class ProjectMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An employee assigned to a project (the project lead is recorded on ``projects``)."""

    __tablename__ = "project_members"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_title: Mapped[str] = mapped_column(String(80), nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),)


class ProjectMilestone(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A dated project milestone; ``Blocked`` rows carry the recorded reason."""

    __tablename__ = "project_milestones"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    blocker_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('Completed', 'In progress', 'Not started', 'Blocked')", name="ck_project_milestones_status"
        ),
    )
