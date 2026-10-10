"""add document approval workflow

Revision ID: d4a7f1c8e2b5
Revises: c3f6e9b2d5a4
Create Date: 2026-10-10 00:00:00.000000

Adds ``document_submissions`` (files awaiting CEO approval) and two permissions:

- ``documents:submit``  : may submit a PDF or image for review. Granted to the six existing roles.
- ``documents:approve`` : may approve or reject submissions. Granted ONLY to SUPER_ADMIN.

Purely additive and idempotent: permissions and grants are inserted with ON CONFLICT DO NOTHING, no existing row
changes, and roles that do not exist are skipped. Permission IDs are the same deterministic IDs the demo dataset
uses, so ``generate_demo_dataset.py`` recognizes them as its own. Downgrade removes the two permissions (and with
them their grants) and drops the table.
"""

from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa


revision = 'd4a7f1c8e2b5'
down_revision = 'c3f6e9b2d5a4'
branch_labels = None
depends_on = None

# Must equal demo_dataset.spec (checked by tests): demo_id("permission", "<resource>:<action>").
_DEMO_NAMESPACE = UUID("6f1c2a9e-4b7d-5e3a-9c8f-0d2e4a6b8c10")
_ALL_ROLES = ("SUPER_ADMIN", "HR_MANAGER", "FINANCE_MANAGER", "ENGINEERING_MANAGER", "SECURITY_MANAGER", "EMPLOYEE")
_PERMISSIONS = (
    ("documents", "submit", "Submit a PDF or image for CEO approval.", _ALL_ROLES),
    ("documents", "approve", "Approve or reject submitted documents.", ("SUPER_ADMIN",)),
)


def _permission_id(resource: str, action: str) -> UUID:
    return uuid5(_DEMO_NAMESPACE, f"nexora-demo:permission:{resource}:{action}")


def upgrade() -> None:
    op.create_table(
        "document_submissions",
        sa.Column("submitter_user_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=300), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("quarantine_key", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_document_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        sa.Column("failure_message", sa.String(length=300), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'indexing', 'ready', 'rejected', 'failed')", name="ck_document_submissions_status"
        ),
        sa.CheckConstraint("source_type IN ('pdf', 'image')", name="ck_document_submissions_source_type"),
        sa.ForeignKeyConstraint(["submitter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_submissions_submitter_user_id"), "document_submissions", ["submitter_user_id"], unique=False)
    op.create_index("ix_document_submissions_status_created", "document_submissions", ["status", "created_at"], unique=False)

    bind = op.get_bind()
    for resource, action, description, roles in _PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, resource, action, description, created_at, updated_at) "
                "VALUES (:id, :resource, :action, :description, now(), now()) ON CONFLICT DO NOTHING"
            ),
            {"id": _permission_id(resource, action), "resource": resource, "action": action, "description": description},
        )
        # Join on (resource, action), so this works whatever ID the permission row has.
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.resource = :resource AND p.action = :action "
                "WHERE r.name = ANY(:roles) ON CONFLICT DO NOTHING"
            ),
            {"resource": resource, "action": action, "roles": list(roles)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for resource, action, _description, _roles in _PERMISSIONS:
        # Grants go with the permission (ON DELETE CASCADE).
        bind.execute(sa.text("DELETE FROM permissions WHERE resource = :resource AND action = :action"), {"resource": resource, "action": action})
    op.drop_index("ix_document_submissions_status_created", table_name="document_submissions")
    op.drop_index(op.f("ix_document_submissions_submitter_user_id"), table_name="document_submissions")
    op.drop_table("document_submissions")
