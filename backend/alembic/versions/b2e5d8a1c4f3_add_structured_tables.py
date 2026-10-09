"""add structured enterprise tables

Revision ID: b2e5d8a1c4f3
Revises: a1d4c7e9f3b2
Create Date: 2026-10-09 00:00:00.000000

Adds ``projects`` and ``employee_compensation`` for the structured-retrieval path. Purely
additive: no existing table or row changes. Downgrade drops the two new tables.
"""

from alembic import op
import sqlalchemy as sa


revision = 'b2e5d8a1c4f3'
down_revision = 'a1d4c7e9f3b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("lead_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_projects_department_id"), "projects", ["department_id"], unique=False)
    op.create_index(op.f("ix_projects_lead_user_id"), "projects", ["lead_user_id"], unique=False)
    op.create_table(
        "employee_compensation",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.String(length=20), nullable=False),
        sa.Column("annual_ctc_inr", sa.BigInteger(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("employee_compensation")
    op.drop_index(op.f("ix_projects_lead_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_department_id"), table_name="projects")
    op.drop_table("projects")
