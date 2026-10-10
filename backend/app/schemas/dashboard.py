"""Response models for GET /api/v1/dashboard/overview.

Every optional section is ``None`` when the signed-in account does not hold the permission that
gates it (it is never merely hidden): the server does not send data the account may not read.
Amounts are plain numbers in the currency recorded on the row; different currencies are never
added together. A metric the application has no source for is listed in ``unavailable`` instead
of being shown as zero.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


DashboardVariant = Literal["ceo", "finance", "hr", "engineering", "security", "employee"]


class DashboardUser(_Out):
    id: UUID
    full_name: str
    email: str
    roles: list[str]
    department: str | None


class UnavailableMetric(_Out):
    key: str
    label: str
    reason: str


class LabelCount(_Out):
    label: str
    count: int


class MilestoneSummary(_Out):
    total: int
    completed: int
    percent_complete: float | None
    """None when there are no milestones (not 0%)."""


class ProjectCard(_Out):
    code: str
    name: str
    department: str
    status: str
    target_date: date | None
    lead: str | None
    milestones: MilestoneSummary
    delayed: bool
    """Not completed and the target date has passed."""
    my_role: str | None = None
    """Only on "my work": "Project lead" or the recorded role on the project."""


class MilestoneItem(_Out):
    project_code: str
    project_name: str
    title: str
    due_date: date
    status: str
    completed_on: date | None
    blocker_note: str | None
    overdue: bool
    """Not completed and the due date has passed."""


class WorkloadRow(_Out):
    name: str
    active_projects: int


class ProjectsSection(_Out):
    scope: Literal["organization", "department"]
    scope_label: str
    total: int
    active: int
    """Projects whose status is "In progress"."""
    by_status: list[LabelCount]
    milestones: MilestoneSummary
    projects: list[ProjectCard]
    upcoming_milestones: list[MilestoneItem]
    blocked_milestones: list[MilestoneItem]
    delayed_projects: list[ProjectCard]
    recent_updates: list[MilestoneItem]
    """Most recently completed milestones."""
    workload: list[WorkloadRow]


class MonthAmount(_Out):
    month: str
    """YYYY-MM"""
    amount: float


class LabelAmount(_Out):
    label: str
    amount: float


class ProjectSpend(_Out):
    code: str
    name: str
    budget: float | None
    actual: float
    pending: float
    utilization_percent: float | None


class ExpenseItem(_Out):
    expense_date: date
    category: str
    description: str | None
    project_code: str
    project_name: str
    amount: float
    currency: str
    status: str


class FinanceCurrency(_Out):
    currency: str
    approved_budget: float | None
    actual_spend: float
    """Approved expenses only."""
    remaining_budget: float | None
    utilization_percent: float | None
    """Approved spend on budgeted projects divided by their approved budget; None without a budget."""
    pending_amount: float
    pending_count: int
    monthly_spend: list[MonthAmount]
    by_category: list[LabelAmount]
    by_project: list[ProjectSpend]


class FinanceSection(_Out):
    currencies: list[FinanceCurrency]
    recent_expenses: list[ExpenseItem]


class DepartmentCount(_Out):
    code: str
    name: str
    count: int


class DocumentRef(_Out):
    id: UUID
    title: str
    status: str
    source_type: str
    created_at: datetime


class WorkforceSection(_Out):
    active_headcount: int
    inactive_accounts: int
    by_department: list[DepartmentCount]
    by_role: list[LabelCount]
    compensation_records_on_file: int
    """A count only: amounts are never part of the dashboard."""
    hr_documents: list[DocumentRef]
    """HR-department documents this account is authorized to read."""


class RoleSummary(_Out):
    role: str
    active_users: int
    permissions: list[str]


class GrantSummary(_Out):
    role_grants: int
    user_grants: int
    documents_total: int
    documents_without_grants: int


class SecuritySection(_Out):
    roles: list[RoleSummary]
    permission_count: int
    grants: GrantSummary


class DocumentsSection(_Out):
    """Counts cover only documents this account is authorized to read."""

    total: int
    by_status: list[LabelCount]
    by_source_type: list[LabelCount]
    fully_indexed: int
    chunks_total: int
    chunks_embedded: int
    recent: list[DocumentRef]


class MyWorkSection(_Out):
    projects: list[ProjectCard]
    upcoming_milestones: list[MilestoneItem]


class DashboardOverview(_Out):
    generated_at: datetime
    dataset_note: str
    variant: DashboardVariant
    user: DashboardUser
    documents: DocumentsSection
    my_work: MyWorkSection
    projects: ProjectsSection | None
    finance: FinanceSection | None
    workforce: WorkforceSection | None
    security: SecuritySection | None
    unavailable: list[UnavailableMetric]
