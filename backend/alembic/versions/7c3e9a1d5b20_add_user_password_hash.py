"""add user password hash

Revision ID: 7c3e9a1d5b20
Revises: 466650ac5b92
Create Date: 2026-10-09 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = '7c3e9a1d5b20'
down_revision = '466650ac5b92'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
