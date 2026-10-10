import { CircleAlert, Database, FileText, FolderKanban, MessagesSquare, PiggyBank, RefreshCw, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router";

import { DashboardSkeleton, EmptyNote, MetricCard, StatGrid, UnavailableList } from "@/components/dashboard/primitives";
import { FinancePanel } from "@/components/dashboard/FinancePanel";
import { DocumentsPanel, MyWorkPanel, SecurityPanel, WorkforcePanel } from "@/components/dashboard/OtherPanels";
import { ProjectsPanel } from "@/components/dashboard/ProjectsPanel";
import { useDashboard } from "@/components/dashboard/useDashboard";
import { StateBlock } from "@/components/feedback/StateBlock";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/context/useAuth";
import { formatDateTime, formatMoney, formatPercent } from "@/lib/dashboardFormat";
import { roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import type { DashboardOverview, DashboardVariant } from "@/types/dashboard";

type SectionKey = "finance" | "projects" | "workforce" | "security" | "documents" | "my-work";

/** Which authorized sections lead for each kind of account. A section the server did not send is skipped. */
const SECTION_ORDER: Record<DashboardVariant, SectionKey[]> = {
  ceo: ["projects", "finance", "workforce", "documents", "security", "my-work"],
  finance: ["finance", "my-work", "documents"],
  hr: ["workforce", "my-work", "documents"],
  engineering: ["projects", "my-work", "documents"],
  security: ["security", "documents", "my-work"],
  employee: ["my-work", "documents"],
};

function renderSection(key: SectionKey, data: DashboardOverview) {
  switch (key) {
    case "finance":
      return data.finance ? <FinancePanel key={key} data={data.finance} /> : null;
    case "projects":
      return data.projects ? <ProjectsPanel key={key} data={data.projects} /> : null;
    case "workforce":
      return data.workforce ? <WorkforcePanel key={key} data={data.workforce} /> : null;
    case "security":
      return data.security ? <SecurityPanel key={key} data={data.security} /> : null;
    case "documents":
      return <DocumentsPanel key={key} data={data.documents} />;
    case "my-work":
      return <MyWorkPanel key={key} data={data.my_work} name={data.user.full_name.split(" ")[0]} />;
  }
}

function Highlights({ data }: { data: DashboardOverview }) {
  const { projects, finance, workforce, security, documents, my_work: myWork } = data;
  const firstCurrency = finance?.currencies[0];
  return (
    <section aria-label="Key figures">
      <StatGrid>
      {projects ? (
        <MetricCard label="Projects" value={projects.total} icon={FolderKanban} hint={`${projects.active} in progress · ${projects.scope_label}`} />
      ) : (
        <MetricCard label="My projects" value={myWork.projects.length} icon={FolderKanban} hint={myWork.projects.length ? "Projects you lead or belong to" : "None recorded for you"} />
      )}
      {workforce ? <MetricCard label="Active employees" value={workforce.active_headcount} icon={Users} hint={`${workforce.by_department.length} departments`} /> : null}
      {firstCurrency ? (
        <MetricCard
          label="Budget utilization"
          value={formatPercent(firstCurrency.utilization_percent)}
          icon={PiggyBank}
          tone={firstCurrency.utilization_percent !== null && firstCurrency.utilization_percent > 100 ? "danger" : "default"}
          hint={`${formatMoney(firstCurrency.actual_spend, firstCurrency.currency)} approved spend`}
        />
      ) : null}
      {security ? <MetricCard label="Roles and permissions" value={`${security.roles.length} / ${security.permission_count}`} icon={ShieldCheck} hint="Defined in the access-control model" /> : null}
      <MetricCard label="Readable documents" value={documents.total} icon={FileText} hint={`${documents.fully_indexed} fully indexed`} />
      </StatGrid>
    </section>
  );
}

function Shortcuts({ data, permissions }: { data: DashboardOverview; permissions: readonly string[] }) {
  // Accounts that cannot ingest directly still get the upload pages, where they submit files for CEO approval.
  const canUpload = permissions.includes("documents:write") || permissions.includes("documents:submit");
  const canApprove = permissions.includes("documents:approve");
  const link = cn(buttonVariants({ variant: "secondary", size: "sm" }));
  return (
    <nav aria-label="Shortcuts" className="flex flex-wrap gap-2">
      <Link to="/app/chat" className={cn(buttonVariants({ size: "sm" }))}>
        <MessagesSquare aria-hidden="true" />
        Ask the assistant
      </Link>
      {canUpload ? (
        <>
          <Link to="/app/upload" className={link}>Upload a PDF</Link>
          <Link to="/app/upload-image" className={link}>Upload an image</Link>
        </>
      ) : null}
      {canApprove ? <Link to="/app/approvals" className={link}>Approval queue</Link> : null}
      {data.projects ? <a href="#projects" className={link}>Project details</a> : null}
      {data.finance ? <a href="#finance" className={link}>Finance details</a> : null}
    </nav>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const { data, error, loading, refresh } = useDashboard();
  if (!user) return null;
  const sections = data ? SECTION_ORDER[data.variant].map((key) => renderSection(key, data)).filter(Boolean) : [];

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="mx-auto flex w-full max-w-[1240px] min-w-0 flex-col gap-5 p-4 sm:p-5 lg:p-6">
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight">Welcome, {user.full_name.split(" ")[0]}</h2>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[13.5px] text-muted-foreground">
              <span>{user.roles.map(roleLabel).join(", ") || "No role assigned"}</span>
              {data?.user.department ? <span>· {data.user.department}</span> : null}
              <Badge variant="muted" title={data?.dataset_note}>
                <Database aria-hidden="true" />
                Demo dataset
              </Badge>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {data ? <span className="hidden text-xs text-muted-foreground sm:inline">Updated {formatDateTime(data.generated_at)}</span> : null}
            <Button variant="secondary" size="sm" onClick={refresh} disabled={loading} aria-label="Refresh dashboard">
              {loading ? <Spinner /> : <RefreshCw aria-hidden="true" />}
              Refresh
            </Button>
          </div>
        </header>

        {loading && !data ? <DashboardSkeleton /> : null}

        {error && !data ? (
          <StateBlock
            icon={CircleAlert}
            tone="error"
            title={error.title}
            role="alert"
            actions={
              error.retryable ? (
                <Button size="sm" onClick={refresh}>
                  <RefreshCw aria-hidden="true" />
                  Try again
                </Button>
              ) : undefined
            }
          >
            {error.message}
          </StateBlock>
        ) : null}

        {error && data ? (
          <Alert variant="error" role="alert">
            Couldn&apos;t refresh the dashboard: {error.message} The figures below are from the last successful load.
          </Alert>
        ) : null}

        {data ? (
          <>
            <Shortcuts data={data} permissions={user.permissions} />
            <Highlights data={data} />
            {sections.length > 0 ? sections : <EmptyNote>No dashboard sections are available to your account.</EmptyNote>}
            <UnavailableList items={data.unavailable} />
          </>
        ) : null}
      </div>
    </div>
  );
}
