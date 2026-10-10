"""add dashboard demo tables

Revision ID: c3f6e9b2d5a4
Revises: b2e5d8a1c4f3
Create Date: 2026-10-10 00:00:00.000000

Adds ``project_budgets``, ``project_expenses``, ``project_members`` and ``project_milestones``
for the role-aware dashboard. Purely additive: no existing table, column or row changes.
Downgrade drops only these four tables.
"""

from alembic import op
import sqlalchemy as sa


revision = 'c3f6e9b2d5a4'
down_revision = 'b2e5d8a1c4f3'
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "project_budgets",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.String(length=20), nullable=False),
        sa.Column("approved_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        *_base_columns(),
        sa.CheckConstraint("approved_amount >= 0", name="ck_project_budgets_amount_nonneg"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "project_expenses",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_base_columns(),
        sa.CheckConstraint("amount >= 0", name="ck_project_expenses_amount_nonneg"),
        sa.CheckConstraint("status IN ('Approved', 'Pending', 'Rejected')", name="ck_project_expenses_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_expenses_project_id"), "project_expenses", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_expenses_expense_date"), "project_expenses", ["expense_date"], unique=False)
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_title", sa.String(length=80), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index(op.f("ix_project_members_project_id"), "project_members", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"], unique=False)
    op.create_table(
        "project_milestones",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("blocker_note", sa.String(length=300), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "status IN ('Completed', 'In progress', 'Not started', 'Blocked')", name="ck_project_milestones_status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_milestones_project_id"), "project_milestones", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_milestones_project_id"), table_name="project_milestones")
    op.drop_table("project_milestones")
    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")
    op.drop_index(op.f("ix_project_expenses_expense_date"), table_name="project_expenses")
    op.drop_index(op.f("ix_project_expenses_project_id"), table_name="project_expenses")
    op.drop_table("project_expenses")
    op.drop_table("project_budgets")
