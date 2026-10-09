"""Centralized authorization: authenticated user context, RBAC and document access.

Access model (default deny):
- Roles and permissions come only from the database (user_roles -> role_permissions).
- A document is accessible only through an explicit grant: a document_role_access row
  for one of the user's roles, or a document_user_access row for the user.
- Department, classification, filename and ownership never grant access by themselves.
  SUPER_ADMIN has no bypass; it reaches documents through the same explicit grants.

``document_access_condition`` is the single definition of document access. It is a SQL
expression, so retrieval queries apply it inside the database before ORDER BY/LIMIT.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


@dataclass(frozen=True)
class AuthenticatedUser:
    """Server-side identity resolved from a validated token and the database."""

    id: UUID
    email: str
    full_name: str
    roles: frozenset[str]
    permissions: frozenset[str]

    def has_role(self, role_name: str) -> bool:
        return role_name in self.roles

    def has_permission(self, resource: str, action: str) -> bool:
        return f"{resource}:{action}" in self.permissions


async def load_authenticated_user(session: AsyncSession, user_id: UUID) -> AuthenticatedUser | None:
    """Load an active user with roles and permissions; None for unknown or inactive users."""
    user = await session.get(models.User, user_id)
    if user is None or not user.is_active:
        return None

    roles = await session.scalars(
        select(models.Role.name)
        .join(models.UserRole, models.UserRole.role_id == models.Role.id)
        .where(models.UserRole.user_id == user_id)
    )
    permissions = await session.execute(
        select(models.Permission.resource, models.Permission.action)
        .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
        .join(models.UserRole, models.UserRole.role_id == models.RolePermission.role_id)
        .where(models.UserRole.user_id == user_id)
        .distinct()
    )
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=frozenset(roles.all()),
        permissions=frozenset(f"{resource}:{action}" for resource, action in permissions.all()),
    )


def document_access_condition(user_id: UUID, document_id: ColumnElement) -> ColumnElement[bool]:
    """SQL predicate: true only when ``user_id`` (active) holds an explicit grant to ``document_id``.

    Roles are resolved inside the query from user_roles, so no client-supplied role or
    cached role list can widen access.
    """
    active_user = exists().where(models.User.id == user_id, models.User.is_active.is_(True))
    role_grant = (
        select(models.DocumentRoleAccess.document_id)
        .join(models.UserRole, models.UserRole.role_id == models.DocumentRoleAccess.role_id)
        .where(models.UserRole.user_id == user_id)
    )
    user_grant = select(models.DocumentUserAccess.document_id).where(
        models.DocumentUserAccess.user_id == user_id
    )
    return and_(active_user, or_(document_id.in_(role_grant), document_id.in_(user_grant)))


async def can_access_document(session: AsyncSession, user_id: UUID, document_id: UUID) -> bool:
    """Document-level check using the same predicate as retrieval."""
    result = await session.scalar(
        select(models.Document.id).where(
            models.Document.id == document_id,
            document_access_condition(user_id, models.Document.id),
        )
    )
    return result is not None
