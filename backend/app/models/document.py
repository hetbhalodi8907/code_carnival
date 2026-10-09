from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.document_chunk import DocumentChunk
    from app.models.role import Role
    from app.models.user import User


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    department: Mapped[Department | None] = relationship(back_populates="documents")
    owner: Mapped[User | None] = relationship(back_populates="owned_documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    role_access: Mapped[list[DocumentRoleAccess]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    user_access: Mapped[list[DocumentUserAccess]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("documents_source_type_status_idx", "source_type", "status"),)


class DocumentRoleAccess(Base):
    __tablename__ = "document_role_access"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    document: Mapped[Document] = relationship(back_populates="role_access")
    role: Mapped[Role] = relationship(back_populates="document_access")

    __table_args__ = (UniqueConstraint("document_id", "role_id"),)


class DocumentUserAccess(Base):
    __tablename__ = "document_user_access"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    document: Mapped[Document] = relationship(back_populates="user_access")
    user: Mapped[User] = relationship(back_populates="direct_document_access")

    __table_args__ = (UniqueConstraint("document_id", "user_id"),)
