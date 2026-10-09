"""use 384-dimension local embeddings

Revision ID: a1d4c7e9f3b2
Revises: 7c3e9a1d5b20
Create Date: 2026-10-09 00:00:00.000000

Embeddings move from OpenAI text-embedding-3-small (1536 dimensions) to the local
sentence-transformers/all-MiniLM-L6-v2 model (384 dimensions).

Vectors from different models can never be compared, and pgvector cannot cast a vector
to another dimension. Both directions therefore clear existing embeddings, and their
model labels, before resizing the column. Documents, chunks, access grants, users and
roles are untouched. Re-embed afterwards:

    scripts/generate_demo_dataset.py --with-embeddings
"""

from alembic import op


revision = 'a1d4c7e9f3b2'
down_revision = '7c3e9a1d5b20'
branch_labels = None
depends_on = None

EMBEDDING_VECTOR_DIMENSION = 384
PREVIOUS_EMBEDDING_VECTOR_DIMENSION = 1536


def _resize_embedding_column(dimension: int) -> None:
    op.execute(
        "UPDATE document_chunks SET embedding = NULL, embedding_model = NULL "
        "WHERE embedding IS NOT NULL OR embedding_model IS NOT NULL"
    )
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({dimension})")


def upgrade() -> None:
    _resize_embedding_column(EMBEDDING_VECTOR_DIMENSION)


def downgrade() -> None:
    _resize_embedding_column(PREVIOUS_EMBEDDING_VECTOR_DIMENSION)
