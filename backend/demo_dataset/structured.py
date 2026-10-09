"""Deterministic synthetic structured data for the structured-retrieval demo (Part 8).

Minimum data for a working demonstration, keyed to the existing demo users and departments:
8 projects and the compensation of the two employees whose compensation statements already
exist as documents (Kabir Sethi INR 11.4 lakh, Rahul Gupta INR 6.2 lakh), so the structured
and document paths agree. IDs are UUIDv5, so reruns create nothing and change nothing.
Existing users, passwords, roles, permissions, documents and grants are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from demo_dataset.seeder import DemoDatasetError
from demo_dataset.spec import department_by_code, demo_id, user_by_email


@dataclass(frozen=True)
class ProjectSpec:
    code: str
    name: str
    department_code: str
    lead_email: str
    status: str
    target_date: date
    description: str


@dataclass(frozen=True)
class CompensationSpec:
    email: str
    annual_ctc_inr: int


FISCAL_YEAR = "FY 2025-26"
EFFECTIVE_DATE = date(2025, 4, 1)

PROJECTS: tuple[ProjectSpec, ...] = (
    ProjectSpec("PRJ-ENG-01", "Platform Reliability Programme", "ENG", "ananya.rao@nexora.example",
                "In progress", date(2026, 12, 15), "Raise production availability and incident response."),
    ProjectSpec("PRJ-ENG-02", "Internal Developer Portal", "ENG", "kabir.sethi@nexora.example",
                "In progress", date(2026, 11, 30), "A single portal for services, docs and runbooks."),
    ProjectSpec("PRJ-FIN-01", "FY 2026-27 Budget Planning", "FIN", "vikram.nair@nexora.example",
                "Planning", date(2027, 1, 31), "Annual budget cycle for all departments."),
    ProjectSpec("PRJ-FIN-02", "Vendor Payment Automation", "FIN", "sneha.reddy@nexora.example",
                "In progress", date(2026, 12, 1), "Automate three-way matching and vendor payments."),
    ProjectSpec("PRJ-HR-01", "Performance Review Revamp", "HR", "meera.iyer@nexora.example",
                "In progress", date(2026, 11, 15), "A new review cycle and calibration process."),
    ProjectSpec("PRJ-SEC-01", "Zero-Trust Access Rollout", "SEC", "devika.krishnan@nexora.example",
                "In progress", date(2027, 2, 28), "Enforce device and identity checks for every system."),
    ProjectSpec("PRJ-OPS-01", "Pune Office Expansion", "OPS", "rahul.gupta@nexora.example",
                "Planning", date(2027, 3, 31), "Add a second floor to the Pune office."),
    ProjectSpec("PRJ-OPS-02", "Vendor Consolidation", "OPS", "priya.saxena@nexora.example",
                "Completed", date(2026, 9, 30), "Reduce the number of hardware and software vendors."),
)

# Matches backend/demo_dataset/content.py compensation statements.
COMPENSATION: tuple[CompensationSpec, ...] = (
    CompensationSpec("kabir.sethi@nexora.example", 1_140_000),
    CompensationSpec("rahul.gupta@nexora.example", 620_000),
)


@dataclass
class StructuredSeedReport:
    created: dict[str, int] = field(default_factory=lambda: {"projects": 0, "employee_compensation": 0})
    unchanged: dict[str, int] = field(default_factory=lambda: {"projects": 0, "employee_compensation": 0})


async def seed_structured_data(session_factory: async_sessionmaker[AsyncSession]) -> StructuredSeedReport:
    """Create the synthetic structured rows that are missing. Safe to rerun."""
    report = StructuredSeedReport()
    departments, users = department_by_code(), user_by_email()
    async with session_factory() as session:
        present_departments = set(await session.scalars(select(models.Department.id)))
        present_users = set(await session.scalars(select(models.User.id)))
        for spec in PROJECTS:
            department, lead = departments[spec.department_code], users[spec.lead_email]
            if department.id not in present_departments or lead.id not in present_users:
                raise DemoDatasetError("The demo departments and users must exist first (generate_demo_dataset.py).")
            project_id = demo_id("project", spec.code)
            if await session.get(models.Project, project_id) is not None:
                report.unchanged["projects"] += 1
                continue
            session.add(models.Project(
                id=project_id, code=spec.code, name=spec.name, description=spec.description, status=spec.status,
                target_date=spec.target_date, department_id=department.id, lead_user_id=lead.id,
            ))
            report.created["projects"] += 1
        for spec in COMPENSATION:
            user = users[spec.email]
            if user.id not in present_users:
                raise DemoDatasetError("The demo users must exist first (generate_demo_dataset.py).")
            record_id = demo_id("compensation", spec.email)
            if await session.get(models.EmployeeCompensation, record_id) is not None:
                report.unchanged["employee_compensation"] += 1
                continue
            session.add(models.EmployeeCompensation(
                id=record_id, user_id=user.id, fiscal_year=FISCAL_YEAR, annual_ctc_inr=spec.annual_ctc_inr,
                effective_date=EFFECTIVE_DATE,
            ))
            report.created["employee_compensation"] += 1
        await session.commit()
    return report
