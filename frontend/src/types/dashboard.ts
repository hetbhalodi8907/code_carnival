/**
 * GET /api/v1/dashboard/overview — mirrors backend/app/schemas/dashboard.py.
 * A section is `null` when the server did not authorize the account to read it; the client never
 * decides what an account may see. Metrics with no stored source are listed in `unavailable`.
 */

export type DashboardVariant = "ceo" | "finance" | "hr" | "engineering" | "security" | "employee";

export interface DashboardUser {
  id: string;
  full_name: string;
  email: string;
  roles: string[];
  department: string | null;
}

export interface UnavailableMetric {
  key: string;
  label: string;
  reason: string;
}

export interface LabelCount {
  label: string;
  count: number;
}

export interface MilestoneSummary {
  total: number;
  completed: number;
  /** null when there are no milestones (not 0%). */
  percent_complete: number | null;
}

export interface ProjectCard {
  code: string;
  name: string;
  department: string;
  status: string;
  target_date: string | null;
  lead: string | null;
  milestones: MilestoneSummary;
  delayed: boolean;
  my_role: string | null;
}

export interface MilestoneItem {
  project_code: string;
  project_name: string;
  title: string;
  due_date: string;
  status: string;
  completed_on: string | null;
  blocker_note: string | null;
  overdue: boolean;
}

export interface WorkloadRow {
  name: string;
  active_projects: number;
}

export interface ProjectsSection {
  scope: "organization" | "department";
  scope_label: string;
  total: number;
  active: number;
  by_status: LabelCount[];
  milestones: MilestoneSummary;
  projects: ProjectCard[];
  upcoming_milestones: MilestoneItem[];
  blocked_milestones: MilestoneItem[];
  delayed_projects: ProjectCard[];
  recent_updates: MilestoneItem[];
  workload: WorkloadRow[];
}

export interface MonthAmount {
  month: string;
  amount: number;
}

export interface LabelAmount {
  label: string;
  amount: number;
}

export interface ProjectSpend {
  code: string;
  name: string;
  budget: number | null;
  actual: number;
  pending: number;
  utilization_percent: number | null;
}

export interface ExpenseItem {
  expense_date: string;
  category: string;
  description: string | null;
  project_code: string;
  project_name: string;
  amount: number;
  currency: string;
  status: string;
}

export interface FinanceCurrency {
  currency: string;
  approved_budget: number | null;
  actual_spend: number;
  remaining_budget: number | null;
  utilization_percent: number | null;
  pending_amount: number;
  pending_count: number;
  monthly_spend: MonthAmount[];
  by_category: LabelAmount[];
  by_project: ProjectSpend[];
}

export interface FinanceSection {
  currencies: FinanceCurrency[];
  recent_expenses: ExpenseItem[];
}

export interface DepartmentCount {
  code: string;
  name: string;
  count: number;
}

export interface DocumentRef {
  id: string;
  title: string;
  status: string;
  source_type: string;
  created_at: string;
}

export interface WorkforceSection {
  active_headcount: number;
  inactive_accounts: number;
  by_department: DepartmentCount[];
  by_role: LabelCount[];
  compensation_records_on_file: number;
  hr_documents: DocumentRef[];
}

export interface RoleSummary {
  role: string;
  active_users: number;
  permissions: string[];
}

export interface SecuritySection {
  roles: RoleSummary[];
  permission_count: number;
  grants: {
    role_grants: number;
    user_grants: number;
    documents_total: number;
    documents_without_grants: number;
  };
}

export interface DocumentsSection {
  total: number;
  by_status: LabelCount[];
  by_source_type: LabelCount[];
  fully_indexed: number;
  chunks_total: number;
  chunks_embedded: number;
  recent: DocumentRef[];
}

export interface MyWorkSection {
  projects: ProjectCard[];
  upcoming_milestones: MilestoneItem[];
}

export interface DashboardOverview {
  generated_at: string;
  dataset_note: string;
  variant: DashboardVariant;
  user: DashboardUser;
  documents: DocumentsSection;
  my_work: MyWorkSection;
  projects: ProjectsSection | null;
  finance: FinanceSection | null;
  workforce: WorkforceSection | null;
  security: SecuritySection | null;
  unavailable: UnavailableMetric[];
}
