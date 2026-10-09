from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.document import Document
    from app.models.document import DocumentUserAccess
    from app.models.user_role import UserRole


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Argon2id PHC string; NULL means the user cannot sign in with a password.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    department: Mapped[Department | None] = relationship(back_populates="users")
    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    owned_documents: Mapped[list[Document]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    direct_document_access: Mapped[list[DocumentUserAccess]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (UniqueConstraint("email"),)
