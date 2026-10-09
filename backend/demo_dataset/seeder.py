"""Generate, embed and reset the Nexora demo dataset.

Safety rules:
- Generation never deletes anything. It creates missing demo records, corrects
  scalar fields of existing demo records and adds missing relationship rows.
- A natural-key collision with a non-demo record (same role name, email, ...) aborts
  generation before any write.
- Reset deletes only rows whose identifiers are demo identifiers, and refuses to run
  while any non-demo record is linked to demo data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.core.config import settings
from app.services.embeddings.service import EmbeddingService
from app.services.embeddings.storage import store_document_embeddings
from app.services.pdf.ingestion import ingest_pdf
from demo_dataset.manifests import build_manifests, render_json
from demo_dataset.pdf_builder import build_pdf
from demo_dataset.spec import (
    DEPARTMENTS,
    DOCUMENTS,
    PERMISSIONS,
    ROLES,
    USERS,
    demo_ids,
    department_by_code,
    permission_by_key,
    role_by_name,
    user_by_email,
)


class DemoDatasetError(RuntimeError):
    """Raised when the demo dataset cannot be generated or reset safely."""


class DemoDatasetConflictError(DemoDatasetError):
    """Raised when a non-demo record already uses a demo natural key."""


class DemoResetBlockedError(DemoDatasetError):
    """Raised when non-demo records are linked to demo records."""


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def record(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)


@dataclass
class GenerationReport:
    counts: dict[str, EntityCounts] = field(default_factory=dict)
    files_written: list[str] = field(default_factory=list)
    files_unchanged: list[str] = field(default_factory=list)
    orphan_files_removed: list[str] = field(default_factory=list)
    documents_embedded: list[str] = field(default_factory=list)
    documents_already_embedded: list[str] = field(default_factory=list)
    embeddings_requested: bool = False

    @property
    def created_anything(self) -> bool:
        return any(counts.created or counts.updated for counts in self.counts.values())


@dataclass
class ResetReport:
    deleted: dict[str, int] = field(default_factory=dict)
    files_removed: list[str] = field(default_factory=list)


def documents_dir(output_dir: Path) -> Path:
    return output_dir / "documents"


def manifests_dir(output_dir: Path) -> Path:
    return output_dir / "manifests"


def stored_pdf_path(document_id: UUID) -> Path:
    """Location the existing ingestion pipeline uses for a document's PDF."""
    return Path(settings.document_storage_path) / f"{document_id}.pdf"


def build_all_pdfs() -> dict[str, bytes]:
    return {document.filename: build_pdf(document) for document in DOCUMENTS}


def _write_if_changed(path: Path, content: bytes, report: GenerationReport) -> None:
    if path.exists() and path.read_bytes() == content:
        report.files_unchanged.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    report.files_written.append(str(path))


def write_dataset_files(output_dir: Path, report: GenerationReport) -> dict[str, bytes]:
    """Write the PDFs and manifests; identical files are left untouched."""
    pdf_bytes = build_all_pdfs()
    for filename, content in pdf_bytes.items():
        _write_if_changed(documents_dir(output_dir) / filename, content, report)
    for name, manifest in build_manifests(pdf_bytes).items():
        _write_if_changed(manifests_dir(output_dir) / name, render_json(manifest).encode(), report)
    return pdf_bytes


async def find_conflicts(session: AsyncSession) -> list[str]:
    """Return natural-key collisions between demo records and non-demo records."""
    ids = {key: sorted(values, key=str) for key, values in demo_ids().items()}
    checks: list[tuple[str, Any, Any, list[UUID]]] = [
        (
            "department code",
            models.Department.code,
            models.Department.code.in_([d.code for d in DEPARTMENTS]),
            ids["departments"],
        ),
        (
            "role name",
            models.Role.name,
            models.Role.name.in_([r.name for r in ROLES]),
            ids["roles"],
        ),
        (
            "user email",
            models.User.email,
            models.User.email.in_([u.email for u in USERS]),
            ids["users"],
        ),
    ]
    conflicts: list[str] = []
    for label, column, condition, allowed_ids in checks:
        model = column.class_
        result = await session.execute(
            select(column).where(condition, not_(model.id.in_(allowed_ids)))
        )
        conflicts.extend(f"{label} '{value}' belongs to a non-demo record" for value in result.scalars())

    permission_keys = {(p.resource, p.action) for p in PERMISSIONS}
    result = await session.execute(
        select(models.Permission.resource, models.Permission.action).where(
            not_(models.Permission.id.in_(ids["permissions"]))
        )
    )
    conflicts.extend(
        f"permission '{resource}:{action}' belongs to a non-demo record"
        for resource, action in result.all()
        if (resource, action) in permission_keys
    )
    return conflicts


async def _ensure(
    session: AsyncSession,
    model: type,
    record_id: UUID,
    fields: dict[str, Any],
) -> str:
    """Create a demo record or align its scalar fields; return the outcome."""
    record = await session.get(model, record_id)
    if record is None:
        session.add(model(id=record_id, **fields))
        return "created"
    changed = False
    for name, value in fields.items():
        if getattr(record, name) != value:
            setattr(record, name, value)
            changed = True
    return "updated" if changed else "unchanged"


async def _add_missing_links(
    session: AsyncSession,
    model: type,
    owner_column: str,
    owner_ids: Iterable[UUID],
    desired: set[tuple[UUID, UUID]],
    other_column: str,
) -> EntityCounts:
    """Insert missing association rows; existing rows are never deleted here."""
    counts = EntityCounts()
    owner_attr = getattr(model, owner_column)
    result = await session.execute(
        select(owner_attr, getattr(model, other_column)).where(owner_attr.in_(list(owner_ids)))
    )
    existing = {tuple(row) for row in result.all()}
    for owner_id, other_id in sorted(desired, key=str):
        if (owner_id, other_id) in existing:
            counts.record("unchanged")
        else:
            session.add(model(**{owner_column: owner_id, other_column: other_id}))
            counts.record("created")
    return counts


async def seed_identity(session_factory: async_sessionmaker[AsyncSession], report: GenerationReport) -> None:
    """Seed departments, permissions, roles, users and their assignments in one transaction."""
    departments = department_by_code()
    permissions = permission_by_key()
    roles = role_by_name()
    async with session_factory() as session:
        for key, model, specs, fields in (
            ("departments", models.Department, DEPARTMENTS,
             lambda d: {"code": d.code, "name": d.name, "description": d.description}),
            ("permissions", models.Permission, PERMISSIONS,
             lambda p: {"resource": p.resource, "action": p.action, "description": p.description}),
            ("roles", models.Role, ROLES,
             lambda r: {"name": r.name, "description": r.description}),
            ("users", models.User, USERS,
             lambda u: {
                 "email": u.email,
                 "full_name": u.full_name,
                 "department_id": departments[u.department_code].id,
                 "is_active": u.is_active,
             }),
        ):
            counts = report.counts.setdefault(key, EntityCounts())
            for spec in specs:
                counts.record(await _ensure(session, model, spec.id, fields(spec)))
            await session.flush()

        report.counts["role_permissions"] = await _add_missing_links(
            session,
            models.RolePermission,
            "role_id",
            [role.id for role in ROLES],
            {(role.id, permissions[key].id) for role in ROLES for key in role.permissions},
            "permission_id",
        )
        report.counts["user_roles"] = await _add_missing_links(
            session,
            models.UserRole,
            "user_id",
            [user.id for user in USERS],
            {(user.id, roles[user.role].id) for user in USERS},
            "role_id",
        )
        await session.commit()


async def seed_documents(
    session_factory: async_sessionmaker[AsyncSession],
    pdf_bytes: dict[str, bytes],
    report: GenerationReport,
) -> None:
    """Ingest each demo PDF through the existing pipeline, then attach metadata and grants."""
    departments = department_by_code()
    roles = role_by_name()
    users = user_by_email()
    document_counts = report.counts.setdefault("documents", EntityCounts())
    role_access = report.counts.setdefault("document_role_access", EntityCounts())
    user_access = report.counts.setdefault("document_user_access", EntityCounts())

    for spec in DOCUMENTS:
        async with session_factory() as session:
            exists = await session.get(models.Document, spec.id) is not None

        created = False
        if not exists:
            orphan = stored_pdf_path(spec.id)
            if orphan.exists():
                # A file named after a demo identifier without a database row is demo-owned.
                orphan.unlink()
                report.orphan_files_removed.append(str(orphan))
            await ingest_pdf(
                filename=spec.filename,
                content_type="application/pdf",
                content=pdf_bytes[spec.filename],
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                session_factory=session_factory,
                document_id=spec.id,
            )
            created = True

        async with session_factory() as session:
            outcome = await _ensure(
                session,
                models.Document,
                spec.id,
                {
                    "title": spec.title,
                    "classification": spec.classification,
                    "department_id": (
                        departments[spec.department_code].id if spec.department_code else None
                    ),
                },
            )
            document_counts.record("created" if created else outcome)

            for counts, model, column, desired in (
                (role_access, models.DocumentRoleAccess, "role_id",
                 {(spec.id, roles[name].id) for name in spec.allowed_roles}),
                (user_access, models.DocumentUserAccess, "user_id",
                 {(spec.id, users[email].id) for email in spec.allowed_users}),
            ):
                added = await _add_missing_links(session, model, "document_id", [spec.id], desired, column)
                counts.created += added.created
                counts.unchanged += added.unchanged
            await session.commit()


async def _is_fully_embedded(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    model_name: str,
) -> bool:
    async with session_factory() as session:
        missing = await session.scalar(
            select(func.count())
            .select_from(models.DocumentChunk)
            .where(
                models.DocumentChunk.document_id == document_id,
                (models.DocumentChunk.embedding.is_(None))
                | (models.DocumentChunk.embedding_model.is_distinct_from(model_name)),
            )
        )
    return missing == 0


async def embed_documents(
    session_factory: async_sessionmaker[AsyncSession],
    service: EmbeddingService,
    report: GenerationReport,
) -> None:
    """Embed demo documents with the existing Part 4 service, skipping finished ones."""
    for spec in DOCUMENTS:
        if await _is_fully_embedded(session_factory, spec.id, service.model):
            report.documents_already_embedded.append(spec.filename)
            continue
        await store_document_embeddings(
            document_id=spec.id,
            session_factory=session_factory,
            service=service,
        )
        report.documents_embedded.append(spec.filename)


async def generate_dataset(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    output_dir: Path,
    with_embeddings: bool = False,
    embedding_service_factory: Callable[[], EmbeddingService] | None = None,
) -> GenerationReport:
    """Create the demo dataset, or complete it if parts already exist."""
    report = GenerationReport(embeddings_requested=with_embeddings)

    embedding_service: EmbeddingService | None = None
    if with_embeddings:
        if embedding_service_factory is None:
            from app.services.embeddings.service import create_embedding_service

            embedding_service_factory = create_embedding_service
        # Fails on missing configuration before anything is written.
        embedding_service = embedding_service_factory()

    async with session_factory() as session:
        conflicts = await find_conflicts(session)
    if conflicts:
        raise DemoDatasetConflictError("; ".join(conflicts))

    # PDF rendering is CPU-bound; keep it off the event loop.
    pdf_bytes = await asyncio.to_thread(write_dataset_files, output_dir, report)
    await seed_identity(session_factory, report)
    await seed_documents(session_factory, pdf_bytes, report)
    if embedding_service is not None:
        await embed_documents(session_factory, embedding_service, report)
    return report


async def find_reset_blockers(session: AsyncSession) -> list[str]:
    """Find links between demo and non-demo records that a reset would break."""
    ids = {key: sorted(values, key=str) for key, values in demo_ids().items()}
    departments, roles, permissions = ids["departments"], ids["roles"], ids["permissions"]
    users, documents = ids["users"], ids["documents"]

    def mixed(a: Any, a_ids: list[UUID], b: Any, b_ids: list[UUID]) -> Any:
        """Rows where exactly one side is a demo record."""
        return (a.in_(a_ids) & not_(b.in_(b_ids))) | (not_(a.in_(a_ids)) & b.in_(b_ids))

    checks = (
        ("non-demo users in demo departments", models.User,
         and_(models.User.department_id.in_(departments), not_(models.User.id.in_(users)))),
        ("non-demo documents in demo departments", models.Document,
         and_(models.Document.department_id.in_(departments), not_(models.Document.id.in_(documents)))),
        ("non-demo documents owned by demo users", models.Document,
         and_(models.Document.owner_user_id.in_(users), not_(models.Document.id.in_(documents)))),
        ("mixed user-role assignments", models.UserRole,
         mixed(models.UserRole.user_id, users, models.UserRole.role_id, roles)),
        ("mixed role-permission assignments", models.RolePermission,
         mixed(models.RolePermission.role_id, roles, models.RolePermission.permission_id, permissions)),
        ("mixed document role grants", models.DocumentRoleAccess,
         mixed(models.DocumentRoleAccess.document_id, documents, models.DocumentRoleAccess.role_id, roles)),
        ("mixed document user grants", models.DocumentUserAccess,
         mixed(models.DocumentUserAccess.document_id, documents, models.DocumentUserAccess.user_id, users)),
    )
    blockers: list[str] = []
    for label, model, condition in checks:
        count = await session.scalar(select(func.count()).select_from(model).where(condition))
        if count:
            blockers.append(f"{count} {label}")
    return blockers


async def reset_dataset(session_factory: async_sessionmaker[AsyncSession]) -> ResetReport:
    """Delete only demo records (and their stored PDFs). Never drops tables or touches migrations."""
    ids = {key: sorted(values, key=str) for key, values in demo_ids().items()}
    report = ResetReport()
    async with session_factory() as session:
        blockers = await find_reset_blockers(session)
        if blockers:
            raise DemoResetBlockedError(
                "Reset refused because non-demo data is linked to demo data: " + "; ".join(blockers)
            )
        # Documents first: chunks and access grants cascade with them.
        for key, model in (
            ("documents", models.Document),
            ("users", models.User),
            ("roles", models.Role),
            ("permissions", models.Permission),
            ("departments", models.Department),
        ):
            result = await session.execute(delete(model).where(model.id.in_(ids[key])))
            report.deleted[key] = result.rowcount
        await session.commit()

    for document_id in ids["documents"]:
        path = stored_pdf_path(document_id)
        if path.exists():
            path.unlink()
            report.files_removed.append(str(path))
    return report
