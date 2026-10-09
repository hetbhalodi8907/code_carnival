"""Initial database schema baseline.

Revision ID: 0001
Revises:
Create Date: 2026-10-08 00:00:00.000000
"""

from alembic import op


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial schema when Part 2.2 adds its models."""
    pass


def downgrade() -> None:
    pass
