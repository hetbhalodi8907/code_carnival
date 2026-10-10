import { FileText, Layers, ShieldCheck } from "lucide-react";

import { BarList, EmptyNote, MetricCard, Panel, SectionTitle, StatGrid, StatusBadge, TD, TH, TableWrap } from "@/components/dashboard/primitives";
import { MilestoneList } from "@/components/dashboard/MilestoneList";
import { ProjectList } from "@/components/dashboard/ProjectList";
import { formatDateTime } from "@/lib/dashboardFormat";
import { roleLabel } from "@/lib/roles";
import { formatPermission } from "@/lib/format";
import type { DocumentRef, DocumentsSection, MyWorkSection, SecuritySection, WorkforceSection } from "@/types/dashboard";

function DocumentRows({ items, empty }: { items: DocumentRef[]; empty: string }) {
  if (items.length === 0) return <EmptyNote>{empty}</EmptyNote>;
  return (
    <ul className="divide-y divide-border">
      {items.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0">
          <div className="flex min-w-0 items-center gap-2.5">
            <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-medium">{d.title}</p>
              <p className="text-xs text-muted-foreground">
                {d.source_type.toUpperCase()} · added {formatDateTime(d.created_at)}
              </p>
            </div>
          </div>
          <StatusBadge status={d.status} />
        </li>
      ))}
    </ul>
  );
}

export function DocumentsPanel({ data }: { data: DocumentsSection }) {
  const indexed = data.chunks_total > 0 ? `${data.chunks_embedded} of ${data.chunks_total} passages` : "no passages";
  return (
    <Panel id="documents" title="Documents you can read" description="Counts cover only the documents your account is granted access to.">
      <StatGrid>
        <MetricCard label="Readable documents" value={data.total} icon={FileText} />
        <MetricCard label="Fully indexed" value={`${data.fully_indexed} of ${data.total}`} icon={ShieldCheck} hint={`Embeddings: ${indexed}`} />
        <MetricCard
          label="By source"
          compact
          value={data.by_source_type.length === 0 ? "None" : data.by_source_type.map((s) => `${s.count} ${s.label}`).join(" · ")}
          icon={Layers}
          hint={data.by_status.map((s) => `${s.count} ${s.label}`).join(" · ") || "No status recorded"}
        />
      </StatGrid>
      <div className="mt-6" />
      <SectionTitle>Recently added</SectionTitle>
      <DocumentRows items={data.recent} empty="No documents are available to your account." />
    </Panel>
  );
}

export function WorkforcePanel({ data }: { data: WorkforceSection }) {
  return (
    <Panel id="workforce" title="Workforce" description="Active employee accounts. Compensation amounts are never shown here.">
      <StatGrid>
        <MetricCard label="Active headcount" value={data.active_headcount} icon={ShieldCheck} hint={`${data.inactive_accounts} deactivated ${data.inactive_accounts === 1 ? "account" : "accounts"}`} />
        <MetricCard label="Compensation records" value={data.compensation_records_on_file} icon={FileText} hint="Count only; amounts stay in the access-controlled records" />
      </StatGrid>
      <div className="mt-6 grid gap-6 *:min-w-0 lg:grid-cols-2">
        <div>
          <SectionTitle>Headcount by department</SectionTitle>
          <BarList rows={data.by_department.map((d) => ({ label: d.name, value: d.count }))} emptyText="No departments recorded." />
        </div>
        <div>
          <SectionTitle>Employees by role</SectionTitle>
          <BarList rows={data.by_role.map((r) => ({ label: roleLabel(r.label), value: r.count }))} emptyText="No role assignments recorded." />
        </div>
      </div>
      <div className="mt-6" />
      <SectionTitle>HR policies and workforce resources you can read</SectionTitle>
      <DocumentRows items={data.hr_documents} empty="No HR documents are available to your account." />
    </Panel>
  );
}

export function SecurityPanel({ data }: { data: SecuritySection }) {
  const g = data.grants;
  return (
    <Panel id="security" title="Access control" description="Roles, permissions and document grants. No document text, credentials or tokens are shown.">
      <StatGrid>
        <MetricCard label="Roles" value={data.roles.length} icon={ShieldCheck} />
        <MetricCard label="Permissions defined" value={data.permission_count} icon={ShieldCheck} />
        <MetricCard label="Role grants" value={g.role_grants} icon={FileText} hint="Document access given to roles" />
        <MetricCard label="Direct user grants" value={g.user_grants} icon={FileText} hint={`${g.documents_without_grants} of ${g.documents_total} documents have no grant`} tone={g.documents_without_grants > 0 ? "warning" : "default"} />
      </StatGrid>
      <div className="mt-6" />
      <SectionTitle>Roles and their permissions</SectionTitle>
      <TableWrap label="Roles and permissions">
        <table className="w-full min-w-[560px] border-collapse">
          <thead>
            <tr>
              <th scope="col" className={TH}>Role</th>
              <th scope="col" className={`${TH} text-right`}>Active users</th>
              <th scope="col" className={TH}>Permissions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.roles.map((r) => (
              <tr key={r.role}>
                <th scope="row" className={`${TD} whitespace-nowrap text-left font-medium`}>{roleLabel(r.role)}</th>
                <td className={`${TD} text-right tabular-nums`}>{r.active_users}</td>
                <td className={`${TD} text-muted-foreground`}>{r.permissions.map(formatPermission).join(", ") || "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </Panel>
  );
}

export function MyWorkPanel({ data, name }: { data: MyWorkSection; name: string }) {
  return (
    <Panel id="my-work" title="My work" description={`Projects ${name} leads or is recorded as a member of.`}>
      <ProjectList projects={data.projects} empty="You are not recorded on any project." showRole />
      {data.projects.length > 0 ? (
        <>
          <div className="mt-6" />
          <SectionTitle>Your upcoming milestones</SectionTitle>
          <MilestoneList items={data.upcoming_milestones} empty="No open milestones on your projects." />
        </>
      ) : null}
    </Panel>
  );
}
