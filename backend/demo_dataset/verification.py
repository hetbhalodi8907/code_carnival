"""Independent verification of the generated demo dataset.

The database is compared against the manifest files on disk, the manifests against a
fresh build from the spec, and the PDFs against the existing PDF validation and
extraction services. Every function returns a list of problems; empty means verified.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from fitz import open as open_pdf
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.services.pdf.extractor import extract_pdf_pages
from app.services.pdf.validator import PDFValidationError, validate_pdf_upload
from demo_dataset.manifests import (
    ACCESS_MATRIX,
    DATASET_MANIFEST,
    build_manifests,
    load_manifest,
    render_json,
)
from demo_dataset.seeder import build_all_pdfs, documents_dir, manifests_dir, stored_pdf_path
from demo_dataset.spec import DOCUMENTS


_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace so wrapped PDF lines compare equal to source sentences."""
    return _WHITESPACE.sub(" ", text).strip()


def extract_page_texts(content: bytes) -> list[str]:
    """Normalized text of every page, using the existing extraction service."""
    extraction = extract_pdf_pages(content)
    return [normalize(str(page["cleaned_text"])) for page in extraction["pages"]]


def verify_pdfs(output_dir: Path) -> list[str]:
    problems: list[str] = []
    expected_bytes = build_all_pdfs()
    for spec in DOCUMENTS:
        path = documents_dir(output_dir) / spec.filename
        label = spec.filename
        if not path.is_file():
            problems.append(f"{label}: generated PDF is missing")
            continue
        content = path.read_bytes()
        if content != expected_bytes[spec.filename]:
            problems.append(f"{label}: file differs from a deterministic rebuild")
        try:
            validate_pdf_upload(spec.filename, "application/pdf", content)
        except PDFValidationError as exc:
            problems.append(f"{label}: invalid PDF ({exc})")
            continue

        pages = extract_page_texts(content)
        if len(pages) != len(spec.pages):
            problems.append(f"{label}: has {len(pages)} pages, expected {len(spec.pages)}")
            continue
        for number, (text, page) in enumerate(zip(pages, spec.pages, strict=True), start=1):
            if not text:
                problems.append(f"{label}: page {number} has no extractable text")
            if normalize(page.heading) not in text:
                problems.append(f"{label}: page {number} is missing heading '{page.heading}'")
        if normalize(spec.title) not in pages[0]:
            problems.append(f"{label}: first page is missing the title")
        for fact in spec.key_facts:
            found_on = [n for n, text in enumerate(pages, start=1) if normalize(fact.text) in text]
            if found_on != [fact.page_number]:
                problems.append(
                    f"{label}: key fact '{fact.text}' found on pages {found_on}, "
                    f"expected only page {fact.page_number}"
                )

        pdf = open_pdf(stream=content, filetype="pdf")
        try:
            if pdf.metadata.get("title") != spec.title:
                problems.append(f"{label}: PDF metadata title does not match")
        finally:
            pdf.close()
    return problems


def verify_manifests(output_dir: Path) -> list[str]:
    problems: list[str] = []
    for name, manifest in build_manifests(build_all_pdfs()).items():
        path = manifests_dir(output_dir) / name
        if not path.is_file():
            problems.append(f"{name}: manifest file is missing")
        elif path.read_text(encoding="utf-8") != render_json(manifest):
            problems.append(f"{name}: manifest differs from the dataset specification")
    return problems


async def _pairs(session: AsyncSession, model: type, owner: str, other: str, owners: list[UUID]) -> dict:
    owner_column = getattr(model, owner)
    result = await session.execute(
        select(owner_column, getattr(model, other)).where(owner_column.in_(owners))
    )
    grouped: dict[UUID, set[UUID]] = defaultdict(set)
    for owner_id, other_id in result.all():
        grouped[owner_id].add(other_id)
    return grouped


def _compare(problems: list[str], label: str, record: Any, expected: dict[str, Any]) -> None:
    if record is None:
        problems.append(f"{label}: missing from the database")
        return
    for name, value in expected.items():
        if getattr(record, name) != value:
            problems.append(f"{label}: {name} is {getattr(record, name)!r}, expected {value!r}")


async def verify_database(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    output_dir: Path,
) -> list[str]:
    """Compare database state with the manifest files on disk."""
    manifest = load_manifest(manifests_dir(output_dir), DATASET_MANIFEST)
    access = load_manifest(manifests_dir(output_dir), ACCESS_MATRIX)
    problems: list[str] = []

    department_ids = {d["code"]: UUID(d["id"]) for d in manifest["departments"]}
    permission_ids = {p["key"]: UUID(p["id"]) for p in manifest["permissions"]}
    role_ids = {r["name"]: UUID(r["id"]) for r in manifest["roles"]}
    user_ids = {u["email"]: UUID(u["id"]) for u in manifest["users"]}

    async with session_factory() as session:
        for entry in manifest["departments"]:
            record = await session.get(models.Department, UUID(entry["id"]))
            _compare(problems, f"department {entry['code']}", record,
                     {"code": entry["code"], "name": entry["name"]})
        for entry in manifest["permissions"]:
            record = await session.get(models.Permission, UUID(entry["id"]))
            _compare(problems, f"permission {entry['key']}", record,
                     {"resource": entry["resource"], "action": entry["action"]})
        for entry in manifest["roles"]:
            record = await session.get(models.Role, UUID(entry["id"]))
            _compare(problems, f"role {entry['name']}", record, {"name": entry["name"]})
        for entry in manifest["users"]:
            record = await session.get(models.User, UUID(entry["id"]))
            _compare(problems, f"user {entry['email']}", record, {
                "email": entry["email"],
                "full_name": entry["full_name"],
                "department_id": department_ids[entry["department_code"]],
                "is_active": entry["is_active"],
            })

        role_permissions = await _pairs(
            session, models.RolePermission, "role_id", "permission_id", list(role_ids.values())
        )
        for entry in manifest["roles"]:
            expected = {permission_ids[key] for key in entry["permissions"]}
            if role_permissions.get(role_ids[entry["name"]], set()) != expected:
                problems.append(f"role {entry['name']}: permissions do not match the manifest")

        user_roles = await _pairs(session, models.UserRole, "user_id", "role_id", list(user_ids.values()))
        for entry in manifest["users"]:
            if user_roles.get(user_ids[entry["email"]], set()) != {role_ids[entry["role"]]}:
                problems.append(f"user {entry['email']}: role assignment does not match the manifest")

        problems.extend(await _verify_documents(session, manifest, access, department_ids, role_ids, user_ids))
    return problems


async def _verify_documents(
    session: AsyncSession,
    manifest: dict[str, Any],
    access: dict[str, Any],
    department_ids: dict[str, UUID],
    role_ids: dict[str, UUID],
    user_ids: dict[str, UUID],
) -> list[str]:
    problems: list[str] = []
    document_ids = [UUID(entry["id"]) for entry in manifest["documents"]]
    role_grants = await _pairs(session, models.DocumentRoleAccess, "document_id", "role_id", document_ids)
    user_grants = await _pairs(session, models.DocumentUserAccess, "document_id", "user_id", document_ids)
    access_by_id = {UUID(entry["document_id"]): entry for entry in access["documents"]}

    for entry in manifest["documents"]:
        document_id = UUID(entry["id"])
        label = f"document {entry['filename']}"
        record = await session.get(models.Document, document_id)
        _compare(problems, label, record, {
            "title": entry["title"],
            "source_type": entry["source_type"],
            "classification": entry["classification"],
            "status": "processed",
            "department_id": department_ids.get(entry["department_code"]),
            "source_path": f"{document_id}.pdf",
        })
        if record is None:
            continue

        duplicates = await session.scalar(
            select(func.count()).select_from(models.Document).where(models.Document.title == entry["title"])
        )
        if duplicates != 1:
            problems.append(f"{label}: {duplicates} documents share the demo title")

        stored = stored_pdf_path(document_id)
        if not stored.is_file():
            problems.append(f"{label}: stored PDF {stored.name} is missing")
        elif hashlib.sha256(stored.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"{label}: stored PDF does not match the manifest checksum")

        chunks = (
            await session.execute(
                select(models.DocumentChunk)
                .where(models.DocumentChunk.document_id == document_id)
                .order_by(models.DocumentChunk.chunk_index)
            )
        ).scalars().all()
        if not chunks:
            problems.append(f"{label}: has no chunks")
        if [chunk.chunk_index for chunk in chunks] != list(range(len(chunks))):
            problems.append(f"{label}: chunk indexes are not contiguous")
        if any(not chunk.content.strip() for chunk in chunks):
            problems.append(f"{label}: has an empty chunk")
        if {chunk.page_number for chunk in chunks} != set(range(1, entry["page_count"] + 1)):
            problems.append(f"{label}: chunk page numbers do not cover every page")

        matrix = access_by_id.get(document_id)
        if matrix is None:
            problems.append(f"{label}: missing from the access matrix")
            continue
        if set(entry["intended_roles"]) != set(matrix["allowed_roles"]):
            problems.append(f"{label}: manifest roles disagree with the access matrix")
        if role_grants.get(document_id, set()) != {role_ids[name] for name in matrix["allowed_roles"]}:
            problems.append(f"{label}: role grants in the database differ from the access matrix")
        if user_grants.get(document_id, set()) != {user_ids[email] for email in matrix["allowed_users"]}:
            problems.append(f"{label}: user grants in the database differ from the access matrix")
    return problems


async def verify_dataset(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    output_dir: Path,
) -> list[str]:
    problems = await asyncio.to_thread(verify_pdfs, output_dir)
    problems += await asyncio.to_thread(verify_manifests, output_dir)
    if not all((manifests_dir(output_dir) / name).is_file() for name in (DATASET_MANIFEST, ACCESS_MATRIX)):
        return problems
    return problems + await verify_database(session_factory, output_dir=output_dir)
