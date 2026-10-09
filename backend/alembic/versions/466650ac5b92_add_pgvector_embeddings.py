"""add pgvector embeddings

Revision ID: 466650ac5b92
Revises: 623078a250c3
Create Date: 2026-10-08 17:58:21.214220

"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision = '466650ac5b92'
down_revision = '623078a250c3'
branch_labels = None
depends_on = None

# Fixed at migration time; must equal app.models.document_chunk.EMBEDDING_VECTOR_DIMENSION.
EMBEDDING_VECTOR_DIMENSION = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(dim=EMBEDDING_VECTOR_DIMENSION), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    # The vector extension is a database-level prerequisite that may be owned by a
    # superuser, so it is intentionally left installed.
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
