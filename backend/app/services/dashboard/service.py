"""Role-aware dashboard aggregation (read-only, no LLM).

Which sections an account receives is decided here, from the roles and permissions the server
loaded from the database for the verified token; the request carries no role or scope. Each
aggregate is computed by the database over rows the account may read:

- documents: only documents the account is granted (``document_access_condition``), the same
  single definition of document access that retrieval uses.
- projects: SUPER_ADMIN sees every project; an ``engineering:read`` holder sees Engineering plus
  projects they lead or belong to; everyone else sees only projects they lead or belong to.
- finance (``finance:read``): budgets and expenses, aggregated per currency (never mixed).
- workforce (``hr:read``): headcount and distributions; compensation is a record COUNT only.
- security (``security:read``): role/permission summaries and grant counts, never document text,
  password hashes or tokens.

A section the account may not read is ``None`` in the response; nothing is fetched for it.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, desc, distinct, func, or_, select, true, union
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.schemas.dashboard import (
    DashboardOverview,
    DashboardUser,
    DashboardVariant,
    DepartmentCount,
    DocumentRef,
    DocumentsSection,
    ExpenseItem,
    FinanceCurrency,
    FinanceSection,
    GrantSummary,
    LabelAmount,
    LabelCount,
    MilestoneItem,
    MilestoneSummary,
    MonthAmount,
    MyWorkSection,
    ProjectCard,
    ProjectSpend,
    ProjectsSection,
    RoleSummary,
    SecuritySection,
    UnavailableMetric,
    WorkforceSection,
    WorkloadRow,
)
from app.services.authorization import AuthenticatedUser, document_access_condition


logger = logging.getLogger("app.dashboard")

DATASET_NOTE = "Demo dataset: fictional Nexora records created for demonstration."
COMPLETED = "Completed"
IN_PROGRESS = "In progress"
APPROVED = "Approved"
PENDING = "Pending"
STATUS_ORDER = ("Planning", IN_PROGRESS, COMPLETED)
MAX_PROJECTS = 100


def _money(value: object) -> float:
    return float(round(Decimal(value or 0), 2))


def _percent(part: float, whole: float) -> float | None:
    return round(part / whole * 100, 1) if whole > 0 else None


def variant_for(user: AuthenticatedUser) -> DashboardVariant:
    """Presentation hint only; the sections returned depend on permissions, not on this."""
    if user.has_role("SUPER_ADMIN"):
        return "ceo"
    for role, variant in (
        ("FINANCE_MANAGER", "finance"),
        ("HR_MANAGER", "hr"),
        ("ENGINEERING_MANAGER", "engineering"),
        ("SECURITY_MANAGER", "security"),
    ):
        if user.has_role(role):
            return variant  # type: ignore[return-value]
    return "employee"


def _involved(user_id: UUID) -> ColumnElement[bool]:
    """Projects the user leads or is a recorded member of."""
    return or_(
        models.Project.lead_user_id == user_id,
        models.Project.id.in_(select(models.ProjectMember.project_id).where(models.ProjectMember.user_id == user_id)),
    )


def _project_scope(user: AuthenticatedUser) -> tuple[str, str, ColumnElement[bool]] | None:
    if user.has_role("SUPER_ADMIN"):
        return "organization", "All departments", true()
    if user.has_permission("engineering", "read"):
        engineering = models.Project.department_id.in_(
            select(models.Department.id).where(models.Department.code == "ENG")
        )
        return "department", "Engineering and projects you belong to", or_(engineering, _involved(user.id))
    return None


class DashboardService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def overview(
        self, user: AuthenticatedUser, *, today: date | None = None, now: datetime | None = None
    ) -> DashboardOverview:
        today = today or date.today()
        async with self._session_factory() as session:
            scope = _project_scope(user)
            result = DashboardOverview(
                generated_at=now or datetime.now(UTC),
                dataset_note=DATASET_NOTE,
                variant=variant_for(user),
                user=await self._profile(session, user),
                documents=await self._documents(session, user),
                my_work=await self._my_work(session, user, today),
                projects=await self._projects(session, scope, today) if scope else None,
                finance=await self._finance(session) if user.has_permission("finance", "read") else None,
                workforce=await self._workforce(session, user) if user.has_permission("hr", "read") else None,
                security=await self._security(session) if user.has_permission("security", "read") else None,
                unavailable=_unavailable(user),
            )
        logger.info(
            "Dashboard built user_id=%s variant=%s sections=%s",
            user.id,
            result.variant,
            ",".join(name for name in ("projects", "finance", "workforce", "security") if getattr(result, name)),
        )
        return result

    # ---- identity ---------------------------------------------------------------------------

    async def _profile(self, session: AsyncSession, user: AuthenticatedUser) -> DashboardUser:
        department = await session.scalar(
            select(models.Department.name)
            .join(models.User, models.User.department_id == models.Department.id)
            .where(models.User.id == user.id)
        )
        return DashboardUser(
            id=user.id, full_name=user.full_name, email=user.email, roles=sorted(user.roles), department=department
        )

    # ---- documents (granted documents only) ---------------------------------------------------

    async def _documents(self, session: AsyncSession, user: AuthenticatedUser) -> DocumentsSection:
        granted = document_access_condition(user.id, models.Document.id)
        by_status = (
            await session.execute(
                select(models.Document.status, func.count()).where(granted).group_by(models.Document.status)
            )
        ).all()
        by_source = (
            await session.execute(
                select(models.Document.source_type, func.count()).where(granted).group_by(models.Document.source_type)
            )
        ).all()
        chunks_total, chunks_embedded = (
            await session.execute(
                select(func.count(models.DocumentChunk.id), func.count(models.DocumentChunk.embedding))
                .join(models.Document, models.Document.id == models.DocumentChunk.document_id)
                .where(granted)
            )
        ).one()
        per_document = (
            select(models.Document.id)
            .join(models.DocumentChunk, models.DocumentChunk.document_id == models.Document.id)
            .where(granted)
            .group_by(models.Document.id)
            .having(func.count(models.DocumentChunk.embedding) == func.count(models.DocumentChunk.id))
            .subquery()
        )
        fully_indexed = await session.scalar(select(func.count()).select_from(per_document))
        recent = await self._document_refs(session, granted, limit=5)
        return DocumentsSection(
            total=sum(count for _, count in by_status),
            by_status=[LabelCount(label=label, count=count) for label, count in sorted(by_status)],
            by_source_type=[LabelCount(label=label, count=count) for label, count in sorted(by_source)],
            fully_indexed=fully_indexed or 0,
            chunks_total=chunks_total,
            chunks_embedded=chunks_embedded,
            recent=recent,
        )

    @staticmethod
    async def _document_refs(session: AsyncSession, condition: ColumnElement[bool], *, limit: int) -> list[DocumentRef]:
        rows = await session.scalars(
            select(models.Document).where(condition).order_by(desc(models.Document.created_at), models.Document.title).limit(limit)
        )
        return [
            DocumentRef(id=d.id, title=d.title, status=d.status, source_type=d.source_type, created_at=d.created_at)
            for d in rows
        ]

    # ---- projects ----------------------------------------------------------------------------

    async def _cards(
        self, session: AsyncSession, condition: ColumnElement[bool], today: date, roles: dict[UUID, str] | None = None
    ) -> list[ProjectCard]:
        totals = (
            select(
                models.ProjectMilestone.project_id.label("project_id"),
                func.count().label("total"),
                func.count().filter(models.ProjectMilestone.status == COMPLETED).label("done"),
            )
            .group_by(models.ProjectMilestone.project_id)
            .subquery()
        )
        rows = (
            await session.execute(
                select(models.Project, models.Department.name, models.User.full_name, totals.c.total, totals.c.done)
                .join(models.Department, models.Department.id == models.Project.department_id)
                .join(models.User, models.User.id == models.Project.lead_user_id, isouter=True)
                .join(totals, totals.c.project_id == models.Project.id, isouter=True)
                .where(condition)
                .order_by(models.Project.target_date.asc().nulls_last(), models.Project.code)
                .limit(MAX_PROJECTS)
            )
        ).all()
        return [
            ProjectCard(
                code=project.code,
                name=project.name,
                department=department,
                status=project.status,
                target_date=project.target_date,
                lead=lead,
                milestones=_summary(total or 0, done or 0),
                delayed=project.status != COMPLETED and project.target_date is not None and project.target_date < today,
                my_role=(roles or {}).get(project.id),
            )
            for project, department, lead, total, done in rows
        ]

    async def _milestones(
        self,
        session: AsyncSession,
        condition: ColumnElement[bool],
        today: date,
        *,
        extra: ColumnElement[bool],
        order: tuple[ColumnElement, ...],
        limit: int,
    ) -> list[MilestoneItem]:
        rows = (
            await session.execute(
                select(models.ProjectMilestone, models.Project.code, models.Project.name)
                .join(models.Project, models.Project.id == models.ProjectMilestone.project_id)
                .where(condition, extra)
                .order_by(*order)
                .limit(limit)
            )
        ).all()
        return [
            MilestoneItem(
                project_code=code,
                project_name=name,
                title=m.title,
                due_date=m.due_date,
                status=m.status,
                completed_on=m.completed_on,
                blocker_note=m.blocker_note,
                overdue=m.status != COMPLETED and m.due_date < today,
            )
            for m, code, name in rows
        ]

    async def _my_work(self, session: AsyncSession, user: AuthenticatedUser, today: date) -> MyWorkSection:
        member_roles = dict(
            (
                await session.execute(
                    select(models.ProjectMember.project_id, models.ProjectMember.role_title).where(
                        models.ProjectMember.user_id == user.id
                    )
                )
            ).all()
        )
        led = set(await session.scalars(select(models.Project.id).where(models.Project.lead_user_id == user.id)))
        roles = {**member_roles, **{project_id: "Project lead" for project_id in led}}
        condition = _involved(user.id)
        return MyWorkSection(
            projects=await self._cards(session, condition, today, roles),
            upcoming_milestones=await self._milestones(
                session,
                condition,
                today,
                extra=models.ProjectMilestone.status != COMPLETED,
                order=(models.ProjectMilestone.due_date, models.Project.code),
                limit=8,
            ),
        )

    async def _projects(
        self, session: AsyncSession, scope: tuple[str, str, ColumnElement[bool]], today: date
    ) -> ProjectsSection:
        kind, label, condition = scope
        counts = dict(
            (await session.execute(select(models.Project.status, func.count()).where(condition).group_by(models.Project.status))).all()
        )
        ordered = [s for s in STATUS_ORDER if s in counts] + sorted(s for s in counts if s not in STATUS_ORDER)
        total_ms, done_ms = (
            await session.execute(
                select(func.count(), func.count().filter(models.ProjectMilestone.status == COMPLETED))
                .select_from(models.ProjectMilestone)
                .join(models.Project, models.Project.id == models.ProjectMilestone.project_id)
                .where(condition)
            )
        ).one()
        cards = await self._cards(session, condition, today)
        pairs = union(
            select(models.ProjectMember.user_id.label("uid"), models.ProjectMember.project_id.label("pid")),
            select(models.Project.lead_user_id.label("uid"), models.Project.id.label("pid")).where(
                models.Project.lead_user_id.is_not(None)
            ),
        ).subquery()
        open_projects = func.count(pairs.c.pid)
        workload = (
            await session.execute(
                select(models.User.full_name, open_projects)
                .join(pairs, pairs.c.uid == models.User.id)
                .join(models.Project, models.Project.id == pairs.c.pid)
                .where(condition, models.Project.status != COMPLETED, models.User.is_active.is_(True))
                .group_by(models.User.id, models.User.full_name)
                .order_by(desc(open_projects), models.User.full_name)
                .limit(8)
            )
        ).all()
        return ProjectsSection(
            scope=kind,  # type: ignore[arg-type]
            scope_label=label,
            total=sum(counts.values()),
            active=counts.get(IN_PROGRESS, 0),
            by_status=[LabelCount(label=s, count=counts[s]) for s in ordered],
            milestones=_summary(total_ms, done_ms),
            projects=cards,
            upcoming_milestones=await self._milestones(
                session,
                condition,
                today,
                extra=models.ProjectMilestone.status != COMPLETED,
                order=(models.ProjectMilestone.due_date, models.Project.code),
                limit=8,
            ),
            blocked_milestones=await self._milestones(
                session,
                condition,
                today,
                extra=models.ProjectMilestone.status == "Blocked",
                order=(models.ProjectMilestone.due_date, models.Project.code),
                limit=8,
            ),
            delayed_projects=[card for card in cards if card.delayed],
            recent_updates=await self._milestones(
                session,
                condition,
                today,
                extra=and_(models.ProjectMilestone.status == COMPLETED, models.ProjectMilestone.completed_on.is_not(None)),
                order=(desc(models.ProjectMilestone.completed_on), models.Project.code),
                limit=5,
            ),
            workload=[WorkloadRow(name=name, active_projects=count) for name, count in workload],
        )

    # ---- finance (finance:read) ---------------------------------------------------------------

    async def _finance(self, session: AsyncSession) -> FinanceSection:
        expense = models.ProjectExpense
        approved = func.coalesce(func.sum(expense.amount).filter(expense.status == APPROVED), 0)
        pending = func.coalesce(func.sum(expense.amount).filter(expense.status == PENDING), 0)

        totals = {
            currency: (spend, waiting, waiting_count)
            for currency, spend, waiting, waiting_count in (
                await session.execute(
                    select(expense.currency, approved, pending, func.count().filter(expense.status == PENDING))
                    .group_by(expense.currency)
                )
            ).all()
        }
        budgets = {
            (pid, currency): amount
            for pid, currency, amount in (
                await session.execute(
                    select(models.ProjectBudget.project_id, models.ProjectBudget.currency, models.ProjectBudget.approved_amount)
                )
            ).all()
        }
        per_project = {
            (pid, currency): (spend, waiting)
            for pid, currency, spend, waiting in (
                await session.execute(
                    select(expense.project_id, expense.currency, approved, pending).group_by(expense.project_id, expense.currency)
                )
            ).all()
        }
        names = {
            pid: (code, name)
            for pid, code, name in (await session.execute(select(models.Project.id, models.Project.code, models.Project.name))).all()
        }
        month = func.to_char(expense.expense_date, "YYYY-MM")
        monthly = (
            await session.execute(
                select(expense.currency, month, func.sum(expense.amount))
                .where(expense.status == APPROVED)
                .group_by(expense.currency, month)
                .order_by(month)
            )
        ).all()
        categories = (
            await session.execute(
                select(expense.currency, expense.category, func.sum(expense.amount))
                .where(expense.status == APPROVED)
                .group_by(expense.currency, expense.category)
                .order_by(desc(func.sum(expense.amount)), expense.category)
            )
        ).all()

        currencies: list[FinanceCurrency] = []
        for currency in sorted({c for _, c in budgets} | set(totals)):
            spend, waiting, waiting_count = totals.get(currency, (0, 0, 0))
            projects = sorted({pid for pid, c in budgets if c == currency} | {pid for pid, c in per_project if c == currency})
            rows: list[ProjectSpend] = []
            budget_total = budgeted_actual = 0.0
            for pid in projects:
                actual, project_pending = per_project.get((pid, currency), (0, 0))
                budget = budgets.get((pid, currency))
                if budget is not None:
                    budget_total += _money(budget)
                    budgeted_actual += _money(actual)
                code, name = names[pid]
                rows.append(
                    ProjectSpend(
                        code=code,
                        name=name,
                        budget=None if budget is None else _money(budget),
                        actual=_money(actual),
                        pending=_money(project_pending),
                        utilization_percent=None if budget is None else _percent(_money(actual), _money(budget)),
                    )
                )
            rows.sort(key=lambda r: (-r.actual, r.code))
            has_budget = any(c == currency for _, c in budgets)
            currencies.append(
                FinanceCurrency(
                    currency=currency,
                    approved_budget=round(budget_total, 2) if has_budget else None,
                    actual_spend=_money(spend),
                    remaining_budget=round(budget_total - budgeted_actual, 2) if has_budget else None,
                    utilization_percent=_percent(budgeted_actual, budget_total) if has_budget else None,
                    pending_amount=_money(waiting),
                    pending_count=waiting_count,
                    monthly_spend=_fill_months([(m, _money(a)) for c, m, a in monthly if c == currency]),
                    by_category=[LabelAmount(label=label, amount=_money(a)) for c, label, a in categories if c == currency],
                    by_project=rows,
                )
            )

        recent = (
            await session.execute(
                select(expense, models.Project.code, models.Project.name)
                .join(models.Project, models.Project.id == expense.project_id)
                .order_by(desc(expense.expense_date), desc(expense.created_at))
                .limit(10)
            )
        ).all()
        return FinanceSection(
            currencies=currencies,
            recent_expenses=[
                ExpenseItem(
                    expense_date=e.expense_date,
                    category=e.category,
                    description=e.description,
                    project_code=code,
                    project_name=name,
                    amount=_money(e.amount),
                    currency=e.currency,
                    status=e.status,
                )
                for e, code, name in recent
            ],
        )

    # ---- workforce (hr:read) ---------------------------------------------------------------------

    async def _workforce(self, session: AsyncSession, user: AuthenticatedUser) -> WorkforceSection:
        by_department = (
            await session.execute(
                select(models.Department.code, models.Department.name, func.count(models.User.id))
                .join(
                    models.User,
                    and_(models.User.department_id == models.Department.id, models.User.is_active.is_(True)),
                    isouter=True,
                )
                .group_by(models.Department.code, models.Department.name)
                .order_by(models.Department.name)
            )
        ).all()
        active = await session.scalar(select(func.count()).select_from(models.User).where(models.User.is_active.is_(True)))
        inactive = await session.scalar(select(func.count()).select_from(models.User).where(models.User.is_active.is_(False)))
        by_role = (
            await session.execute(
                select(models.Role.name, func.count(distinct(models.User.id)))
                .join(models.UserRole, models.UserRole.role_id == models.Role.id)
                .join(models.User, models.User.id == models.UserRole.user_id)
                .where(models.User.is_active.is_(True))
                .group_by(models.Role.name)
                .order_by(desc(func.count(distinct(models.User.id))), models.Role.name)
            )
        ).all()
        compensation = await session.scalar(
            select(func.count())
            .select_from(models.EmployeeCompensation)
            .join(models.User, models.User.id == models.EmployeeCompensation.user_id)
            .where(models.User.is_active.is_(True))
        )
        hr_documents = await self._document_refs(
            session,
            and_(
                models.Document.department_id.in_(select(models.Department.id).where(models.Department.code == "HR")),
                document_access_condition(user.id, models.Document.id),
            ),
            limit=8,
        )
        return WorkforceSection(
            active_headcount=active or 0,
            inactive_accounts=inactive or 0,
            by_department=[DepartmentCount(code=c, name=n, count=k) for c, n, k in by_department],
            by_role=[LabelCount(label=label, count=count) for label, count in by_role],
            compensation_records_on_file=compensation or 0,
            hr_documents=hr_documents,
        )

    # ---- security (security:read) ------------------------------------------------------------------

    async def _security(self, session: AsyncSession) -> SecuritySection:
        users_per_role = dict(
            (
                await session.execute(
                    select(models.UserRole.role_id, func.count(distinct(models.User.id)))
                    .join(models.User, models.User.id == models.UserRole.user_id)
                    .where(models.User.is_active.is_(True))
                    .group_by(models.UserRole.role_id)
                )
            ).all()
        )
        permissions: dict[UUID, list[str]] = {}
        for role_id, resource, action in (
            await session.execute(
                select(models.RolePermission.role_id, models.Permission.resource, models.Permission.action)
                .join(models.Permission, models.Permission.id == models.RolePermission.permission_id)
                .order_by(models.Permission.resource, models.Permission.action)
            )
        ).all():
            permissions.setdefault(role_id, []).append(f"{resource}:{action}")
        roles = (await session.execute(select(models.Role.id, models.Role.name).order_by(models.Role.name))).all()
        granted = or_(
            models.Document.id.in_(select(models.DocumentRoleAccess.document_id)),
            models.Document.id.in_(select(models.DocumentUserAccess.document_id)),
        )
        return SecuritySection(
            roles=[
                RoleSummary(role=name, active_users=users_per_role.get(rid, 0), permissions=permissions.get(rid, []))
                for rid, name in roles
            ],
            permission_count=await session.scalar(select(func.count()).select_from(models.Permission)) or 0,
            grants=GrantSummary(
                role_grants=await session.scalar(select(func.count()).select_from(models.DocumentRoleAccess)) or 0,
                user_grants=await session.scalar(select(func.count()).select_from(models.DocumentUserAccess)) or 0,
                documents_total=await session.scalar(select(func.count()).select_from(models.Document)) or 0,
                documents_without_grants=await session.scalar(
                    select(func.count()).select_from(models.Document).where(~granted)
                )
                or 0,
            ),
        )


def _summary(total: int, done: int) -> MilestoneSummary:
    return MilestoneSummary(total=total, completed=done, percent_complete=_percent(done, total))


def _fill_months(points: list[tuple[str, float]]) -> list[MonthAmount]:
    """Months between the first and last with spending, so a quiet month shows as 0, not a gap."""
    if not points:
        return []
    known = dict(points)
    year, month = (int(part) for part in points[0][0].split("-"))
    last_year, last_month = (int(part) for part in points[-1][0].split("-"))
    filled: list[MonthAmount] = []
    while (year, month) <= (last_year, last_month):
        key = f"{year:04d}-{month:02d}"
        filled.append(MonthAmount(month=key, amount=known.get(key, 0.0)))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return filled


def _unavailable(user: AuthenticatedUser) -> list[UnavailableMetric]:
    """Metrics the application has no stored source for. They are not shown as zero."""
    items = [
        UnavailableMetric(
            key="task_list",
            label="Personal task list",
            reason="Tasks are not recorded; assignments are shown as projects and milestones.",
        )
    ]
    if user.has_role("SUPER_ADMIN"):
        items += [
            UnavailableMetric(
                key="system_health",
                label="Real-time system health",
                reason="The application does not record health or uptime metrics.",
            ),
            UnavailableMetric(
                key="activity_feed",
                label="Organization activity feed",
                reason="No activity log is stored; recently added documents are shown instead.",
            ),
        ]
    if user.has_permission("security", "read"):
        items.append(
            UnavailableMetric(
                key="security_events",
                label="Authentication failures, denied requests and security events",
                reason="These are written to server logs only; none are stored in the database.",
            )
        )
    if user.has_permission("hr", "read"):
        items.append(
            UnavailableMetric(
                key="workforce_history",
                label="Workforce changes over time",
                reason="Hire and exit dates are not recorded.",
            )
        )
    return items
