"""Part 8: structured database retrieval with row-level authorization.

Questions are routed to one of a FINITE set of intents by a deterministic router. The LLM
never writes or runs SQL: each intent is a fixed, parameterized SQLAlchemy statement.

Access rules (explicit, evaluated INSIDE each statement's WHERE clause, so a row the user
may not read is never selected, never reaches Python and never reaches the model):

- directory-style data (headcount, project list, employee directory): an active user holding
  ``documents:read`` (every demo role). Only active employees are listed; no compensation,
  password hashes or secrets are ever selected.
- own profile: an active user reading their own row.
- compensation (confidential): an active user reading their OWN row (needs
  ``employee:self_read``), or an active user holding ``hr:read`` (HR Manager, SUPER_ADMIN).
  A finance, engineering or security permission grants nothing here, and an employee
  cannot read a colleague's row.

The structured path mirrors the document access matrix: the compensation statements are
granted to HR_MANAGER, SUPER_ADMIN and the employee themselves.

Each result row becomes one ``ContextItem`` (``source_type="structured"``), so it flows
through the same context budget, prompt boundaries, generation and citation validation as
document passages.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid5

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.services.rag.context import ContextItem


logger = logging.getLogger("app.rag")

IntentName = Literal[
    "headcount_by_department",
    "department_projects",
    "employee_directory",
    "my_profile",
    "my_compensation",
    "employee_compensation",
]

_NAMESPACE = UUID("6c1f0d52-8f7e-5b6a-9d3c-5e9a2b7c4d10")
MAX_ROWS = 50
STRUCTURED_SOURCE = "structured"

TABLE_TITLES: dict[str, str] = {
    "headcount": "Structured data: headcount by department",
    "projects": "Structured data: department projects",
    "directory": "Structured data: employee directory",
    "profile": "Structured data: your employee profile",
    "compensation": "Structured data: employee compensation (confidential)",
}


@dataclass(frozen=True)
class StructuredIntent:
    name: IntentName
    department_code: str | None = None
    target_user_id: UUID | None = None
    """For ``employee_compensation``: the person named in the question. Resolving a name
    reveals nothing; the compensation statement still enforces access in SQL."""


# --------------------------------------------------------------------------------------
# Routing (deterministic, no LLM)
# --------------------------------------------------------------------------------------

_COMPENSATION = re.compile(r"\b(compensation|ctc|salary|salaries|pay|package|remuneration)\b")
_FIRST_PERSON = re.compile(r"\b(my|mine|own|i)\b")
_PROJECTS = re.compile(r"\b(projects?|initiatives?|programmes?|programs?)\b")
_HEADCOUNT = re.compile(
    r"\bheadcount\b|\bhead count\b|\b(employee|staff|people) count\b"
    r"|\b(how many|number of|count of|total)\b.{0,40}\b(employees?|people|staff|members|engineers|team)\b"
)
_DIRECTORY = re.compile(
    r"\bwho (works|is working|are the (employees|people|members))\b"
    r"|\b(list|show|name)\b.{0,30}\b(employees|people|staff|members|team)\b"
    r"|\b(team members|employees in|staff in|members of|people in)\b"
)
_PROFILE = re.compile(r"\b(my (department|role|team|profile|details|email|information)|who am i)\b")


@dataclass(frozen=True)
class Directory:
    """Non-sensitive lookup data used only to interpret a question."""

    departments: tuple[tuple[str, str], ...]
    """(code, name) pairs."""
    people: tuple[tuple[UUID, str], ...]
    """(user_id, full_name) of active users."""


def _department_in(text: str, directory: Directory) -> str | None:
    for code, name in directory.departments:
        if re.search(rf"\b{re.escape(name.lower())}\b", text) or re.search(rf"\b{re.escape(code.lower())}\b", text):
            return code
    # "HR" is the usual spelling for Human Resources.
    return next((code for code, _ in directory.departments if code == "HR"), None) if re.search(r"\bhr\b", text) else None


def _person_in(text: str, directory: Directory) -> UUID | None:
    """A named employee: full name, or an unambiguous first name (with optional 's)."""
    first_names: dict[str, list[UUID]] = {}
    for user_id, full_name in directory.people:
        lowered = full_name.lower()
        if re.search(rf"\b{re.escape(lowered)}\b", text):
            return user_id
        first_names.setdefault(lowered.split()[0], []).append(user_id)
    for first, ids in first_names.items():
        if len(ids) == 1 and re.search(rf"\b{re.escape(first)}\b", text):
            return ids[0]
    return None


def classify_question(question: str, directory: Directory) -> StructuredIntent | None:
    """Pick a structured intent for ``question``, or None to use document retrieval."""
    text = question.lower()
    if _COMPENSATION.search(text):
        if _FIRST_PERSON.search(text):
            return StructuredIntent("my_compensation")
        target = _person_in(text, directory)
        return StructuredIntent("employee_compensation", target_user_id=target) if target else None
    if _PROJECTS.search(text):
        return StructuredIntent("department_projects", department_code=_department_in(text, directory))
    if _HEADCOUNT.search(text):
        return StructuredIntent("headcount_by_department", department_code=_department_in(text, directory))
    if _PROFILE.search(text):
        return StructuredIntent("my_profile")
    if _DIRECTORY.search(text):
        return StructuredIntent("employee_directory", department_code=_department_in(text, directory))
    return None


# --------------------------------------------------------------------------------------
# Row-level access rules, as SQL
# --------------------------------------------------------------------------------------


def _active(user_id: UUID) -> ColumnElement[bool]:
    return exists().where(models.User.id == user_id, models.User.is_active.is_(True))


def _has_permission(user_id: UUID, resource: str, action: str) -> ColumnElement[bool]:
    return exists(
        select(models.Permission.id)
        .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
        .join(models.UserRole, models.UserRole.role_id == models.RolePermission.role_id)
        .where(
            models.UserRole.user_id == user_id,
            models.Permission.resource == resource,
            models.Permission.action == action,
        )
    )


def directory_access(user_id: UUID) -> ColumnElement[bool]:
    """Internal directory data: any active user who may read documents."""
    return and_(_active(user_id), _has_permission(user_id, "documents", "read"))


def compensation_access(user_id: UUID, owner_column: ColumnElement) -> ColumnElement[bool]:
    """Compensation rows: the employee themselves, or an active holder of hr:read."""
    own_row = and_(owner_column == user_id, _has_permission(user_id, "employee", "self_read"))
    return and_(_active(user_id), or_(own_row, _has_permission(user_id, "hr", "read")))


# --------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------


def _item(rank: int, table: str, key: str, content: str) -> ContextItem:
    return ContextItem(
        rank=rank,
        chunk_id=uuid5(_NAMESPACE, f"{table}:{key}"),
        document_id=uuid5(_NAMESPACE, f"table:{table}"),
        document_title=TABLE_TITLES[table],
        chunk_index=rank - 1,
        page_number=None,
        source_locator=f"table:{table};row:{key}",
        content=content,
        distance=0.0,
        similarity=1.0,
        source_type=STRUCTURED_SOURCE,
    )


def _lakh(amount: int) -> str:
    return f"INR {amount / 100000:g} lakh ({amount:,} per year)"


class StructuredRetriever:
    """Runs the fixed structured queries on behalf of one user."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_directory(self) -> Directory:
        """Department and employee names for interpreting a question (no sensitive fields)."""
        async with self._session_factory() as session:
            departments = (await session.execute(
                select(models.Department.code, models.Department.name).order_by(models.Department.code)
            )).all()
            people = (await session.execute(
                select(models.User.id, models.User.full_name).where(models.User.is_active.is_(True))
            )).all()
        return Directory(
            departments=tuple((code, name) for code, name in departments),
            people=tuple((user_id, name) for user_id, name in people),
        )

    async def retrieve(self, intent: StructuredIntent, user_id: UUID) -> list[ContextItem]:
        """Authorized rows for ``intent`` as ranked context items (possibly empty)."""
        started = time.perf_counter()
        async with self._session_factory() as session:
            items = await getattr(self, f"_{intent.name}")(session, intent, user_id)
        logger.info(
            "Structured retrieval intent=%s user_id=%s rows=%d duration_ms=%.2f",
            intent.name, user_id, len(items), (time.perf_counter() - started) * 1000,
        )
        return items

    async def _headcount_by_department(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        statement = (
            select(models.Department.code, models.Department.name, func.count(models.User.id))
            .join(models.User, and_(models.User.department_id == models.Department.id, models.User.is_active.is_(True)),
                  isouter=True)
            .where(directory_access(user_id))
            .group_by(models.Department.code, models.Department.name)
            .order_by(models.Department.name)
        )
        if intent.department_code:
            statement = statement.where(models.Department.code == intent.department_code)
        rows = (await session.execute(statement)).all()
        return [
            _item(rank, "headcount", code, f"Department: {name} | Active employees: {count}")
            for rank, (code, name, count) in enumerate(rows, start=1)
        ]

    async def _department_projects(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        statement = (
            select(models.Project, models.Department.name, models.User.full_name)
            .join(models.Department, models.Department.id == models.Project.department_id)
            .join(models.User, models.User.id == models.Project.lead_user_id, isouter=True)
            .where(directory_access(user_id))
            .order_by(models.Department.name, models.Project.code)
            .limit(MAX_ROWS)
        )
        if intent.department_code:
            statement = statement.where(models.Department.code == intent.department_code)
        rows = (await session.execute(statement)).all()
        return [
            _item(
                rank, "projects", project.code,
                f"Project {project.code}: {project.name} | Department: {department} | "
                f"Lead: {lead or 'unassigned'} | Status: {project.status} | "
                f"Target date: {project.target_date.isoformat() if project.target_date else 'not set'}"
                + (f" | {project.description}" if project.description else ""),
            )
            for rank, (project, department, lead) in enumerate(rows, start=1)
        ]

    async def _employee_directory(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        statement = (
            select(models.User.id, models.User.full_name, models.User.email, models.Department.name)
            .join(models.Department, models.Department.id == models.User.department_id)
            .where(models.User.is_active.is_(True), directory_access(user_id))
            .order_by(models.Department.name, models.User.full_name)
            .limit(MAX_ROWS)
        )
        if intent.department_code:
            statement = statement.where(models.Department.code == intent.department_code)
        rows = (await session.execute(statement)).all()
        return [
            _item(rank, "directory", str(identifier), f"Employee: {name} | Department: {department} | Email: {email}")
            for rank, (identifier, name, email, department) in enumerate(rows, start=1)
        ]

    async def _my_profile(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        roles = (
            select(func.string_agg(models.Role.name, ", "))
            .join(models.UserRole, models.UserRole.role_id == models.Role.id)
            .where(models.UserRole.user_id == models.User.id)
            .scalar_subquery()
        )
        led = (
            select(func.string_agg(models.Project.name, "; "))
            .where(models.Project.lead_user_id == models.User.id)
            .scalar_subquery()
        )
        statement = (
            select(models.User.full_name, models.User.email, models.Department.name, roles, led)
            .join(models.Department, models.Department.id == models.User.department_id, isouter=True)
            .where(models.User.id == user_id, models.User.is_active.is_(True))
        )
        rows = (await session.execute(statement)).all()
        return [
            _item(
                rank, "profile", str(user_id),
                f"Name: {name} | Email: {email} | Department: {department or 'none'} | "
                f"Roles: {role_names or 'none'} | Projects led: {led_projects or 'none'}",
            )
            for rank, (name, email, department, role_names, led_projects) in enumerate(rows, start=1)
        ]

    async def _compensation(self, session: AsyncSession, user_id: UUID, owner_filter: ColumnElement[bool]):
        statement = (
            select(models.EmployeeCompensation, models.User.full_name, models.Department.name)
            .join(models.User, models.User.id == models.EmployeeCompensation.user_id)
            .join(models.Department, models.Department.id == models.User.department_id, isouter=True)
            .where(owner_filter, compensation_access(user_id, models.EmployeeCompensation.user_id))
            .order_by(models.User.full_name)
        )
        rows = (await session.execute(statement)).all()
        return [
            _item(
                rank, "compensation", str(record.user_id),
                f"Employee: {name} | Department: {department or 'none'} | Fiscal year: {record.fiscal_year} | "
                f"Annual CTC: {_lakh(record.annual_ctc_inr)} | Effective: {record.effective_date.isoformat()}",
            )
            for rank, (record, name, department) in enumerate(rows, start=1)
        ]

    async def _my_compensation(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        return await self._compensation(session, user_id, models.EmployeeCompensation.user_id == user_id)

    async def _employee_compensation(self, session: AsyncSession, intent: StructuredIntent, user_id: UUID):
        if intent.target_user_id is None:
            return []
        return await self._compensation(
            session, user_id, models.EmployeeCompensation.user_id == intent.target_user_id
        )


def structured_items(items: Sequence[ContextItem]) -> list[ContextItem]:
    """Only structured items (helper for tests and callers that merge sources)."""
    return [item for item in items if item.source_type == STRUCTURED_SOURCE]
