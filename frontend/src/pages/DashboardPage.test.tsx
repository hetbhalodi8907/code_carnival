import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatDate, formatMoney, formatPercent } from "@/lib/dashboardFormat";
import { getAccessToken } from "@/services/session";
import { mockFetch, renderApp, signIn } from "@/test/utils";
import type { CurrentUser } from "@/types/api";
import type { DashboardOverview, DashboardVariant, MilestoneItem, ProjectCard } from "@/types/dashboard";

const BASE_PERMISSIONS = ["documents:read", "employee:self_read"];

function account(name: string, role: string, extra: string[] = []): CurrentUser {
  return {
    id: `id-${role}`,
    email: `${name.split(" ")[0].toLowerCase()}@nexora.example`,
    full_name: name,
    roles: [role],
    permissions: [...BASE_PERMISSIONS, ...extra],
  };
}

const ACCOUNTS: Record<DashboardVariant, CurrentUser> = {
  ceo: account("Ishaan Malhotra", "SUPER_ADMIN", ["documents:write", "finance:read", "hr:read", "engineering:read", "security:read"]),
  finance: account("Vikram Nair", "FINANCE_MANAGER", ["finance:read", "finance:write"]),
  hr: account("Meera Iyer", "HR_MANAGER", ["hr:read", "hr:write"]),
  engineering: account("Ananya Rao", "ENGINEERING_MANAGER", ["engineering:read", "engineering:write"]),
  security: account("Devika Krishnan", "SECURITY_MANAGER", ["security:read", "security:write"]),
  employee: account("Kabir Sethi", "EMPLOYEE"),
};

const milestone = (over: Partial<MilestoneItem> = {}): MilestoneItem => ({
  project_code: "PRJ-ENG-01",
  project_name: "Platform Reliability Programme",
  title: "Failover drill sign-off",
  due_date: "2026-10-20",
  status: "Blocked",
  completed_on: null,
  blocker_note: "Waiting for the vendor datacentre maintenance window.",
  overdue: false,
  ...over,
});

const project = (over: Partial<ProjectCard> = {}): ProjectCard => ({
  code: "PRJ-ENG-01",
  name: "Platform Reliability Programme",
  department: "Engineering",
  status: "In progress",
  target_date: "2026-12-15",
  lead: "Ananya Rao",
  milestones: { total: 4, completed: 2, percent_complete: 50 },
  delayed: false,
  my_role: null,
  ...over,
});

const INR = {
  currency: "INR",
  approved_budget: 12_000_000,
  actual_spend: 9_000_000,
  remaining_budget: 3_000_000,
  utilization_percent: 75,
  pending_amount: 500_000,
  pending_count: 2,
  monthly_spend: [
    { month: "2026-04", amount: 1_000_000 },
    { month: "2026-05", amount: 0 },
    { month: "2026-06", amount: 8_000_000 },
  ],
  by_category: [
    { label: "Contractors", amount: 6_000_000 },
    { label: "Software Licences", amount: 3_000_000 },
  ],
  by_project: [
    { code: "PRJ-FIN-02", name: "Vendor Payment Automation", budget: 2_000_000, actual: 3_000_000, pending: 0, utilization_percent: 150 },
    { code: "PRJ-ENG-01", name: "Platform Reliability Programme", budget: 10_000_000, actual: 6_000_000, pending: 500_000, utilization_percent: 60 },
  ],
};

function overview(variant: DashboardVariant, over: Partial<DashboardOverview> = {}): DashboardOverview {
  const user = ACCOUNTS[variant];
  return {
    generated_at: "2026-10-10T08:30:00Z",
    dataset_note: "Demo dataset: fictional Nexora records created for demonstration.",
    variant,
    user: { id: user.id, full_name: user.full_name, email: user.email, roles: user.roles, department: "Engineering" },
    documents: {
      total: 3,
      by_status: [{ label: "ready", count: 3 }],
      by_source_type: [{ label: "pdf", count: 3 }],
      fully_indexed: 3,
      chunks_total: 12,
      chunks_embedded: 12,
      recent: [{ id: "d1", title: "Engineering_Handbook.pdf", status: "ready", source_type: "pdf", created_at: "2026-10-09T10:00:00Z" }],
    },
    my_work: { projects: [], upcoming_milestones: [] },
    projects: null,
    finance: null,
    workforce: null,
    security: null,
    unavailable: [{ key: "task_list", label: "Personal task list", reason: "Tasks are not recorded." }],
    ...over,
  };
}

const PROJECTS = {
  scope: "organization" as const,
  scope_label: "All departments",
  total: 8,
  active: 5,
  by_status: [
    { label: "Planning", count: 2 },
    { label: "In progress", count: 5 },
    { label: "Completed", count: 1 },
  ],
  milestones: { total: 24, completed: 9, percent_complete: 37.5 },
  projects: [project(), project({ code: "PRJ-FIN-02", name: "Vendor Payment Automation", department: "Finance", delayed: true })],
  upcoming_milestones: [milestone({ title: "Service catalogue import", status: "In progress", blocker_note: null, overdue: true, due_date: "2026-10-05" })],
  blocked_milestones: [milestone()],
  delayed_projects: [project({ code: "PRJ-FIN-02", name: "Vendor Payment Automation", delayed: true })],
  recent_updates: [milestone({ title: "Portal alpha", status: "Completed", blocker_note: null, completed_on: "2026-08-12" })],
  workload: [{ name: "Nisha Pillai", active_projects: 2 }],
};

const FINANCE = {
  currencies: [INR],
  recent_expenses: [
    { expense_date: "2026-10-08", category: "Contractors", description: "Rollout support (Q3)", project_code: "PRJ-SEC-01", project_name: "Zero-Trust Access Rollout", amount: 900_000, currency: "INR", status: "Pending" },
    { expense_date: "2026-10-07", category: "Training", description: null, project_code: "PRJ-ENG-02", project_name: "Internal Developer Portal", amount: 260_000, currency: "INR", status: "Rejected" },
  ],
};

const WORKFORCE = {
  active_headcount: 19,
  inactive_accounts: 1,
  by_department: [
    { code: "ENG", name: "Engineering", count: 5 },
    { code: "HR", name: "Human Resources", count: 3 },
  ],
  by_role: [
    { label: "EMPLOYEE", count: 14 },
    { label: "HR_MANAGER", count: 1 },
  ],
  compensation_records_on_file: 2,
  hr_documents: [{ id: "d2", title: "HR_Policy.pdf", status: "ready", source_type: "pdf", created_at: "2026-10-09T10:00:00Z" }],
};

const SECURITY = {
  roles: [
    { role: "SUPER_ADMIN", active_users: 1, permissions: ["documents:read", "documents:write"] },
    { role: "EMPLOYEE", active_users: 14, permissions: ["documents:read"] },
  ],
  permission_count: 11,
  grants: { role_grants: 35, user_grants: 2, documents_total: 11, documents_without_grants: 0 },
};

async function openDashboard(variant: DashboardVariant, body: DashboardOverview) {
  signIn();
  const fetchMock = mockFetch({
    "GET /api/v1/auth/me": { body: ACCOUNTS[variant] },
    "GET /api/v1/dashboard/overview": { body },
  });
  renderApp("/app/dashboard");
  await screen.findByRole("navigation", { name: "Shortcuts" }); // present only once the data has loaded
  return fetchMock;
}

const panel = (name: RegExp | string) => screen.getByRole("region", { name });
const hasPanel = (name: RegExp | string) => screen.queryByRole("region", { name }) !== null;

describe("dashboard formatting", () => {
  it("formats values without ever turning a missing figure into zero", () => {
    expect(formatPercent(null)).toBe("Not available");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(37.5)).toBe("37.5%");
    expect(formatMoney(12_000_000, "INR")).toBe("₹1.20 Cr");
    expect(formatMoney(9_000_000, "INR")).toBe("₹90,00,000");
    expect(formatMoney(1_000, "USD")).toBe("$1,000.00");
    expect(formatDate("2026-10-05")).toBe("5 Oct 2026");
    expect(formatDate(null)).toBe("Not set");
  });
});

describe("dashboard routing and navigation", () => {
  it("is the application home and appears in the sidebar", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: ACCOUNTS.finance }, "GET /api/v1/dashboard/overview": { body: overview("finance", { finance: FINANCE }) } });
    renderApp("/app");

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    await screen.findByRole("navigation", { name: "Shortcuts" });
    expect(screen.getByTestId("location")).toHaveTextContent("/app/dashboard");
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    const labels = within(nav).getAllByRole("link").map((link) => link.textContent ?? "");
    for (const name of ["Dashboard", "Assistant", "Upload", "Upload images", "Profile"]) {
      expect(labels.some((label) => label.startsWith(name))).toBe(true);
    }
  });

  it("keeps the Assistant and the upload pages reachable, and locked uploads stay locked", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: ACCOUNTS.employee }, "GET /api/v1/dashboard/overview": { body: overview("employee") } });
    const user = userEvent.setup();
    renderApp("/app/dashboard");

    const shortcuts = await screen.findByRole("navigation", { name: "Shortcuts" });
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: /Upload images/ })).toHaveTextContent("locked");
    expect(within(shortcuts).queryByRole("link", { name: /Upload/ })).not.toBeInTheDocument();
    await user.click(within(shortcuts).getByRole("link", { name: /Ask the assistant/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Assistant" })).toBeInTheDocument();
  });

  it("offers upload shortcuts only to accounts the server allowed to upload", async () => {
    await openDashboard("ceo", overview("ceo", { projects: PROJECTS, finance: FINANCE, workforce: WORKFORCE, security: SECURITY }));
    const shortcuts = screen.getByRole("navigation", { name: "Shortcuts" });
    expect(within(shortcuts).getByRole("link", { name: "Upload a PDF" })).toHaveAttribute("href", "/app/upload");
    expect(within(shortcuts).getByRole("link", { name: "Upload an image" })).toHaveAttribute("href", "/app/upload-image");
    expect(within(shortcuts).getByRole("link", { name: "Project details" })).toHaveAttribute("href", "#projects");
  });
});

describe("role-aware content", () => {
  it("CEO: organization projects, finance, workforce, access control and the honest unavailable list", async () => {
    await openDashboard(
      "ceo",
      overview("ceo", {
        projects: PROJECTS,
        finance: FINANCE,
        workforce: WORKFORCE,
        security: SECURITY,
        unavailable: [
          { key: "system_health", label: "Real-time system health", reason: "The application does not record health or uptime metrics." },
          { key: "activity_feed", label: "Organization activity feed", reason: "No activity log is stored." },
        ],
      }),
    );
    for (const name of [/^Projects/, /^Finance/, /^Workforce/, /^Access control/, /^Documents you can read/]) expect(panel(name)).toBeInTheDocument();
    expect(screen.getByText("Demo dataset")).toBeInTheDocument();
    const projects = panel(/^Projects/);
    expect(within(projects).getByText("8 projects, 5 in progress", { exact: false })).toBeInTheDocument();
    expect(within(projects).getByText("Blocker: Waiting for the vendor datacentre maintenance window.")).toBeInTheDocument();
    const notAvailable = screen.getByRole("region", { name: "Not available in this deployment" });
    expect(notAvailable).toHaveTextContent("Real-time system health");
    expect(notAvailable).toHaveTextContent("does not record health");
  });

  it("Finance Manager: budget, actual, remaining, utilization, trend, categories, projects and expenses", async () => {
    await openDashboard("finance", overview("finance", { finance: FINANCE }));
    const finance = panel(/^Finance/);
    expect(within(finance).getByText("₹90,00,000")).toBeInTheDocument(); // actual spend
    expect(within(finance).getByText("₹1.20 Cr")).toBeInTheDocument(); // approved budget
    expect(within(finance).getAllByText("₹30,00,000").length).toBeGreaterThanOrEqual(1); // remaining budget
    expect(within(finance).getByRole("progressbar", { name: "Budget utilization" })).toHaveAttribute("aria-valuenow", "75");
    expect(within(finance).getByText("Apr 26")).toBeInTheDocument();
    expect(within(finance).getByText("Contractors", { selector: "span" })).toBeInTheDocument();
    const byProject = within(finance).getByRole("region", { name: "Spending by project in INR" });
    expect(within(byProject).getByText("150% (over)")).toBeInTheDocument(); // overspend is shown, not clamped
    const expenses = within(finance).getByRole("region", { name: "Recent expenses" });
    expect(within(expenses).getByText("Pending")).toBeInTheDocument();
    expect(within(expenses).getByText("Rejected")).toBeInTheDocument();
    expect(within(expenses).getByText("8 Oct 2026")).toBeInTheDocument();
    // Sections this account was not sent are not rendered.
    expect(hasPanel(/^Workforce/)).toBe(false);
    expect(hasPanel(/^Access control/)).toBe(false);
    expect(screen.queryByText(/salary|compensation/i)).not.toBeInTheDocument();
  });

  it("keeps different currencies separate and shows a missing budget as unavailable, not zero", async () => {
    const usd = { ...INR, currency: "USD", approved_budget: null, remaining_budget: null, utilization_percent: null, actual_spend: 1_000 };
    await openDashboard("finance", overview("finance", { finance: { ...FINANCE, currencies: [INR, usd] } }));
    expect(screen.getByTestId("finance-INR")).toBeInTheDocument();
    const usdBlock = screen.getByTestId("finance-USD");
    expect(within(usdBlock).getByText("$1,000.00")).toBeInTheDocument();
    expect(within(usdBlock).getAllByText("Not available").length).toBeGreaterThanOrEqual(2);
    expect(within(usdBlock).getByText(/Budget utilization: not available/)).toBeInTheDocument();
  });

  it("HR Manager: headcount and distributions, a compensation COUNT only, and the unavailable history", async () => {
    await openDashboard(
      "hr",
      overview("hr", {
        workforce: WORKFORCE,
        unavailable: [{ key: "workforce_history", label: "Workforce changes over time", reason: "Hire and exit dates are not recorded." }],
      }),
    );
    const workforce = panel(/^Workforce/);
    expect(within(workforce).getByText("19")).toBeInTheDocument();
    expect(within(workforce).getByText("Human Resources")).toBeInTheDocument();
    expect(within(workforce).getByText("HR Manager")).toBeInTheDocument();
    expect(within(workforce).getByText("HR_Policy.pdf")).toBeInTheDocument();
    expect(within(workforce).getByText(/Count only/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Not available in this deployment" })).toHaveTextContent("Hire and exit dates are not recorded");
    expect(hasPanel(/^Finance/)).toBe(false);
    expect(workforce.textContent).not.toMatch(/₹|annual_ctc/);
  });

  it("Engineering Manager: only the projects the server sent, with blockers, overdue milestones and workload", async () => {
    await openDashboard("engineering", overview("engineering", { projects: { ...PROJECTS, scope: "department", scope_label: "Engineering and projects you belong to", total: 2, active: 2, projects: [project()] } }));
    const projects = panel(/^Projects/);
    expect(within(projects).getByText("Service catalogue import")).toBeInTheDocument();
    expect(within(projects).getByText(/Overdue/)).toBeInTheDocument();
    expect(within(projects).getByText("Nisha Pillai")).toBeInTheDocument();
    expect(within(projects).queryByText("Zero-Trust Access Rollout")).not.toBeInTheDocument();
    expect(hasPanel(/^Finance/)).toBe(false);
  });

  it("Security Manager: roles, permissions and grants; the missing security-event source is stated", async () => {
    await openDashboard(
      "security",
      overview("security", {
        security: SECURITY,
        unavailable: [{ key: "security_events", label: "Authentication failures, denied requests and security events", reason: "These are written to server logs only; none are stored in the database." }],
      }),
    );
    const access = panel(/^Access control/);
    const roles = within(access).getByRole("region", { name: "Roles and permissions" });
    expect(within(roles).getByRole("rowheader", { name: "CEO / Super Admin" })).toBeInTheDocument();
    expect(within(access).getByText("35")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Not available in this deployment" })).toHaveTextContent("none are stored in the database");
    expect(roles.textContent).not.toMatch(/password|token|hash|secret|\$argon2/i);
  });

  it("Employee: only their own projects with their role, no organization panels", async () => {
    await openDashboard(
      "employee",
      overview("employee", {
        my_work: {
          projects: [project({ code: "PRJ-ENG-02", name: "Internal Developer Portal", my_role: "Project lead" }), project({ my_role: "Backend engineer" })],
          upcoming_milestones: [milestone({ title: "Beta to all engineers", status: "Not started", blocker_note: null })],
        },
      }),
    );
    const mine = panel(/^My work/);
    expect(within(mine).getByText(/Your role: Project lead/)).toBeInTheDocument();
    expect(within(mine).getByText(/Your role: Backend engineer/)).toBeInTheDocument();
    expect(within(mine).getByText("Beta to all engineers")).toBeInTheDocument();
    for (const name of [/^Projects/, /^Finance/, /^Workforce/, /^Access control/]) expect(hasPanel(name)).toBe(false);
    expect(screen.getByRole("region", { name: "Not available in this deployment" })).toHaveTextContent("Personal task list");
  });

  it("Employee with no assignment: an empty state, never invented projects", async () => {
    await openDashboard("employee", overview("employee"));
    expect(within(panel(/^My work/)).getByText("You are not recorded on any project.")).toBeInTheDocument();
    expect(screen.getByText("0", { selector: "div" })).toBeInTheDocument(); // a genuine zero is shown as 0
  });
});

describe("dashboard states", () => {
  it("shows a loading skeleton, then the content", async () => {
    signIn();
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    mockFetch({
      "GET /api/v1/auth/me": { body: ACCOUNTS.employee },
      "GET /api/v1/dashboard/overview": async () => {
        await gate;
        return { body: overview("employee") };
      },
    });
    renderApp("/app/dashboard");

    expect(await screen.findByTestId("dashboard-skeleton")).toBeInTheDocument();
    release?.();
    expect(await screen.findByRole("region", { name: /^My work/ })).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();
  });

  it("shows a calm error with a retry that recovers", async () => {
    signIn();
    let attempt = 0;
    mockFetch({
      "GET /api/v1/auth/me": { body: ACCOUNTS.employee },
      "GET /api/v1/dashboard/overview": () =>
        ++attempt === 1
          ? { status: 503, body: { error: { code: "HTTP_ERROR", message: "postgresql://secret-host failed", request_id: "r" } } }
          : { body: overview("employee") },
    });
    const user = userEvent.setup();
    renderApp("/app/dashboard");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Service temporarily unavailable");
    expect(document.body.textContent).not.toContain("secret-host");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: /^My work/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("refresh keeps the last data on screen and reports a failed refresh", async () => {
    signIn();
    let attempt = 0;
    mockFetch({
      "GET /api/v1/auth/me": { body: ACCOUNTS.employee },
      "GET /api/v1/dashboard/overview": () =>
        ++attempt === 1 ? { body: overview("employee") } : { status: 500, body: { error: { code: "HTTP_ERROR", message: "boom", request_id: "r" } } },
    });
    const user = userEvent.setup();
    renderApp("/app/dashboard");

    await screen.findByRole("region", { name: /^My work/ });
    await user.click(screen.getByRole("button", { name: "Refresh dashboard" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Couldn't refresh the dashboard"));
    expect(screen.getByRole("region", { name: /^My work/ })).toBeInTheDocument();
  });

  it("an expired session on the dashboard ends the session instead of showing data", async () => {
    signIn();
    mockFetch({
      "GET /api/v1/auth/me": { body: ACCOUNTS.employee },
      "GET /api/v1/dashboard/overview": { status: 401, body: { error: { code: "HTTP_ERROR", message: "x", request_id: "r" } } },
    });
    renderApp("/app/dashboard");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });

  it("asks the server for the dashboard with the bearer token and no role or scope parameters", async () => {
    const fetchMock = await openDashboard("finance", overview("finance", { finance: FINANCE }));
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/dashboard/overview"));
    expect(String(call?.[0])).toMatch(/\/api\/v1\/dashboard\/overview$/);
    expect((call?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer test-access-token");
  });
});
