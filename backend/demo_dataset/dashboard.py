"""Fictional Nexora dashboard demo data: budgets, expenses, project members and milestones.

Every record here is SYNTHETIC. It exists only so the role-aware dashboard has real rows to
aggregate; none of it describes a real organisation, vendor or person. The rows reference the
existing demo projects and users by code and email. IDs are UUIDv5, so a rerun creates nothing
and changes nothing; existing rows (also in the four new tables) are never updated or deleted.
Users, passwords, roles, permissions, document grants, files, chunks and embeddings are not touched.

Needs the migration ``c3f6e9b2d5a4`` and the structured demo data (``seed_structured_data``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from demo_dataset.seeder import DemoDatasetError
from demo_dataset.spec import demo_id, user_by_email


CURRENCY = "INR"
FISCAL_YEAR = "FY 2026-27"

# project code -> approved budget (INR)
BUDGETS: dict[str, int] = {
    "PRJ-ENG-01": 12_000_000,
    "PRJ-ENG-02": 4_500_000,
    "PRJ-FIN-01": 1_800_000,
    "PRJ-FIN-02": 6_000_000,
    "PRJ-HR-01": 2_500_000,
    "PRJ-SEC-01": 9_000_000,
    "PRJ-OPS-01": 20_000_000,
    "PRJ-OPS-02": 3_500_000,
}

A, P, R = "Approved", "Pending", "Rejected"

# (project, date, category, description, amount INR, status)
EXPENSES: tuple[tuple[str, date, str, str, int, str], ...] = (
    ("PRJ-ENG-01", date(2026, 4, 22), "Cloud & Infrastructure", "Observability platform annual subscription", 1_850_000, A),
    ("PRJ-ENG-01", date(2026, 5, 14), "Contractors", "SRE contractor engagement (Q1)", 2_400_000, A),
    ("PRJ-ENG-01", date(2026, 6, 20), "Hardware", "Load-testing rig", 960_000, A),
    ("PRJ-ENG-01", date(2026, 7, 18), "Cloud & Infrastructure", "Multi-region failover environment", 2_100_000, A),
    ("PRJ-ENG-01", date(2026, 8, 25), "Training", "Incident-response training", 340_000, A),
    ("PRJ-ENG-01", date(2026, 9, 12), "Contractors", "SRE contractor engagement (Q2)", 2_400_000, A),
    ("PRJ-ENG-01", date(2026, 10, 5), "Cloud & Infrastructure", "Chaos-testing tooling licence", 780_000, P),
    ("PRJ-ENG-02", date(2026, 5, 9), "Software Licences", "Developer portal framework licence", 620_000, A),
    ("PRJ-ENG-02", date(2026, 6, 11), "Contractors", "UI contractor (6 weeks)", 1_350_000, A),
    ("PRJ-ENG-02", date(2026, 7, 30), "Cloud & Infrastructure", "Portal hosting", 480_000, A),
    ("PRJ-ENG-02", date(2026, 9, 3), "Contractors", "Documentation migration contractor", 1_150_000, A),
    ("PRJ-ENG-02", date(2026, 9, 28), "Software Licences", "Search add-on", 540_000, A),
    ("PRJ-ENG-02", date(2026, 10, 7), "Training", "Platform-team workshop", 260_000, R),
    ("PRJ-FIN-01", date(2026, 6, 2), "Software Licences", "Planning tool licences", 540_000, A),
    ("PRJ-FIN-01", date(2026, 7, 21), "Contractors", "Budget modelling consultant", 720_000, A),
    ("PRJ-FIN-01", date(2026, 9, 15), "Training", "Finance modelling course", 150_000, A),
    ("PRJ-FIN-01", date(2026, 10, 2), "Contractors", "Consultant extension", 360_000, P),
    ("PRJ-FIN-02", date(2026, 4, 30), "Software Licences", "Invoice-matching platform setup", 1_900_000, A),
    ("PRJ-FIN-02", date(2026, 6, 18), "Contractors", "Integration engineers", 2_250_000, A),
    ("PRJ-FIN-02", date(2026, 8, 8), "Vendor Services", "Bank API connectivity", 980_000, A),
    ("PRJ-FIN-02", date(2026, 9, 19), "Contractors", "Integration engineers (extension)", 1_350_000, A),
    ("PRJ-FIN-02", date(2026, 10, 6), "Software Licences", "Additional vendor-portal seats", 280_000, P),
    ("PRJ-HR-01", date(2026, 5, 26), "Software Licences", "Review-cycle software", 840_000, A),
    ("PRJ-HR-01", date(2026, 7, 9), "Training", "Manager calibration workshops", 410_000, A),
    ("PRJ-HR-01", date(2026, 8, 27), "Vendor Services", "Employee survey vendor", 330_000, A),
    ("PRJ-HR-01", date(2026, 10, 1), "Travel", "Regional calibration travel", 120_000, P),
    ("PRJ-SEC-01", date(2026, 4, 15), "Software Licences", "Zero-trust gateway licences", 3_100_000, A),
    ("PRJ-SEC-01", date(2026, 6, 5), "Hardware", "Security keys for all staff", 1_450_000, A),
    ("PRJ-SEC-01", date(2026, 7, 28), "Contractors", "Identity architecture consultants", 1_900_000, A),
    ("PRJ-SEC-01", date(2026, 9, 9), "Vendor Services", "Penetration test", 850_000, A),
    ("PRJ-SEC-01", date(2026, 9, 30), "Hardware", "Device attestation agents", 640_000, A),
    ("PRJ-SEC-01", date(2026, 10, 8), "Contractors", "Rollout support (Q3)", 900_000, P),
    ("PRJ-OPS-01", date(2026, 6, 24), "Facilities", "Architectural design", 1_200_000, A),
    ("PRJ-OPS-01", date(2026, 8, 14), "Facilities", "Structural survey", 450_000, A),
    ("PRJ-OPS-01", date(2026, 9, 22), "Legal", "Lease and permit review", 380_000, A),
    ("PRJ-OPS-01", date(2026, 10, 3), "Facilities", "Contractor tender deposit", 2_500_000, P),
    ("PRJ-OPS-02", date(2026, 4, 20), "Vendor Services", "Vendor audit", 420_000, A),
    ("PRJ-OPS-02", date(2026, 6, 3), "Contractors", "Procurement analyst", 900_000, A),
    ("PRJ-OPS-02", date(2026, 7, 15), "Software Licences", "Contract-management tool", 760_000, A),
    ("PRJ-OPS-02", date(2026, 8, 20), "Legal", "Contract renegotiation support", 520_000, A),
    ("PRJ-OPS-02", date(2026, 9, 18), "Travel", "Vendor site visits", 110_000, A),
)

# (project, member email, role on the project). Project leads are recorded on `projects`, not here.
MEMBERS: tuple[tuple[str, str, str], ...] = (
    ("PRJ-ENG-01", "nisha.pillai@nexora.example", "Site reliability engineer"),
    ("PRJ-ENG-01", "pooja.banerjee@nexora.example", "Backend engineer"),
    ("PRJ-ENG-01", "siddharth.verma@nexora.example", "Platform engineer"),
    ("PRJ-ENG-01", "kabir.sethi@nexora.example", "Backend engineer"),
    ("PRJ-ENG-01", "lavanya.hegde@nexora.example", "Security reviewer"),
    ("PRJ-ENG-02", "nisha.pillai@nexora.example", "Frontend engineer"),
    ("PRJ-ENG-02", "siddharth.verma@nexora.example", "Backend engineer"),
    ("PRJ-ENG-02", "pooja.banerjee@nexora.example", "Technical writer"),
    ("PRJ-ENG-02", "farhan.qureshi@nexora.example", "Backend engineer"),
    ("PRJ-FIN-01", "arjun.menon@nexora.example", "Budget analyst"),
    ("PRJ-FIN-01", "sneha.reddy@nexora.example", "Financial analyst"),
    ("PRJ-FIN-02", "arjun.menon@nexora.example", "Process analyst"),
    ("PRJ-HR-01", "rohan.bhatt@nexora.example", "HR business partner"),
    ("PRJ-HR-01", "tanvi.kulkarni@nexora.example", "Learning and development"),
    ("PRJ-SEC-01", "aditya.chauhan@nexora.example", "Security engineer"),
    ("PRJ-SEC-01", "lavanya.hegde@nexora.example", "Security analyst"),
    ("PRJ-OPS-01", "zoya.ansari@nexora.example", "Facilities coordinator"),
    ("PRJ-OPS-01", "priya.saxena@nexora.example", "Procurement"),
    ("PRJ-OPS-02", "zoya.ansari@nexora.example", "Vendor coordinator"),
)

C, I, N, B = "Completed", "In progress", "Not started", "Blocked"

# (project, title, due, status, completed on, blocker note)
MILESTONES: tuple[tuple[str, str, date, str, date | None, str | None], ...] = (
    ("PRJ-ENG-01", "Baseline SLOs agreed", date(2026, 5, 29), C, date(2026, 5, 27), None),
    ("PRJ-ENG-01", "Observability rollout", date(2026, 7, 31), C, date(2026, 8, 4), None),
    ("PRJ-ENG-01", "Failover drill sign-off", date(2026, 10, 20), B, None, "Waiting for the vendor datacentre maintenance window."),
    ("PRJ-ENG-01", "Availability target review", date(2026, 12, 15), N, None, None),
    ("PRJ-ENG-02", "Portal alpha", date(2026, 8, 14), C, date(2026, 8, 12), None),
    ("PRJ-ENG-02", "Service catalogue import", date(2026, 10, 5), I, None, None),
    ("PRJ-ENG-02", "Beta to all engineers", date(2026, 11, 30), N, None, None),
    ("PRJ-FIN-01", "Department budget inputs collected", date(2026, 10, 30), I, None, None),
    ("PRJ-FIN-01", "Consolidated draft budget", date(2026, 12, 15), N, None, None),
    ("PRJ-FIN-01", "Board approval", date(2027, 1, 31), N, None, None),
    ("PRJ-FIN-02", "Vendor onboarding batch 1", date(2026, 7, 15), C, date(2026, 7, 14), None),
    ("PRJ-FIN-02", "Vendor onboarding batch 2", date(2026, 9, 25), I, None, None),
    ("PRJ-FIN-02", "Three-way matching go-live", date(2026, 12, 1), N, None, None),
    ("PRJ-HR-01", "Review framework approved", date(2026, 8, 31), C, date(2026, 8, 28), None),
    ("PRJ-HR-01", "Manager training", date(2026, 10, 31), I, None, None),
    ("PRJ-HR-01", "Calibration round", date(2026, 11, 15), N, None, None),
    ("PRJ-SEC-01", "Identity provider integration", date(2026, 7, 31), C, date(2026, 7, 29), None),
    ("PRJ-SEC-01", "Device attestation pilot", date(2026, 10, 25), I, None, None),
    ("PRJ-SEC-01", "Full rollout", date(2027, 2, 28), N, None, None),
    ("PRJ-OPS-01", "Design approved", date(2026, 11, 20), I, None, None),
    ("PRJ-OPS-01", "Construction tender", date(2027, 1, 15), N, None, None),
    ("PRJ-OPS-01", "Floor handover", date(2027, 3, 31), N, None, None),
    ("PRJ-OPS-02", "Vendor shortlist", date(2026, 6, 30), C, date(2026, 6, 28), None),
    ("PRJ-OPS-02", "Contracts consolidated", date(2026, 9, 30), C, date(2026, 9, 26), None),
)

TABLES = ("project_budgets", "project_expenses", "project_members", "project_milestones")


@dataclass
class DashboardSeedReport:
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TABLES, 0))
    unchanged: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TABLES, 0))


async def seed_dashboard_data(session_factory: async_sessionmaker[AsyncSession]) -> DashboardSeedReport:
    """Create the fictional dashboard rows that are missing. Safe to rerun; never updates a row."""
    report = DashboardSeedReport()
    users = user_by_email()
    async with session_factory() as session:
        projects = {code: pid for code, pid in (await session.execute(select(models.Project.code, models.Project.id)))}
        missing = {code for code in BUDGETS if code not in projects}
        if missing:
            raise DemoDatasetError("The demo projects must exist first (seed_structured_data.py): " + ", ".join(sorted(missing)))
        present_users = set(await session.scalars(select(models.User.id)))

        async def add(table: str, model: type, record_id, **values: object) -> None:
            if await session.get(model, record_id) is not None:
                report.unchanged[table] += 1
                return
            session.add(model(id=record_id, **values))
            report.created[table] += 1

        for code, amount in BUDGETS.items():
            await add("project_budgets", models.ProjectBudget, demo_id("project-budget", code),
                      project_id=projects[code], fiscal_year=FISCAL_YEAR, approved_amount=Decimal(amount), currency=CURRENCY)
        for code, spent_on, category, description, amount, status in EXPENSES:
            await add("project_expenses", models.ProjectExpense, demo_id("project-expense", f"{code}|{spent_on}|{description}"),
                      project_id=projects[code], expense_date=spent_on, category=category, description=description,
                      amount=Decimal(amount), currency=CURRENCY, status=status)
        for code, email, role_title in MEMBERS:
            user = users[email]
            if user.id not in present_users:
                raise DemoDatasetError("The demo users must exist first (generate_demo_dataset.py).")
            await add("project_members", models.ProjectMember, demo_id("project-member", f"{code}|{email}"),
                      project_id=projects[code], user_id=user.id, role_title=role_title)
        for code, title, due, status, completed_on, note in MILESTONES:
            await add("project_milestones", models.ProjectMilestone, demo_id("project-milestone", f"{code}|{title}"),
                      project_id=projects[code], title=title, due_date=due, status=status, completed_on=completed_on, blocker_note=note)
        await session.commit()
    return report
