import { EmptyNote, StatusBadge } from "@/components/dashboard/primitives";
import { formatDate, formatPercent } from "@/lib/dashboardFormat";
import type { ProjectCard } from "@/types/dashboard";

function Progress({ project }: { project: ProjectCard }) {
  const { total, completed, percent_complete } = project.milestones;
  if (percent_complete === null) return <span className="text-xs text-subtle">No milestones recorded</span>;
  return (
    <div className="min-w-[120px]">
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${project.name} milestone progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent_complete)}>
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent_complete}%` }} />
      </div>
      <span className="mt-0.5 block text-xs text-muted-foreground">
        {completed} of {total} milestones · {formatPercent(percent_complete)}
      </span>
    </div>
  );
}

/** Projects with status, target date, lead and recorded milestone progress. */
export function ProjectList({ projects, empty, showRole = false }: { projects: ProjectCard[]; empty: string; showRole?: boolean }) {
  if (projects.length === 0) return <EmptyNote>{empty}</EmptyNote>;
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {projects.map((p) => (
        <li key={p.code} className="flex flex-col gap-2 rounded-lg border border-border bg-surface-2 p-3.5" data-testid="project-card">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[14px] font-semibold">{p.name}</p>
              <p className="text-xs text-subtle">
                {p.code} · {p.department}
              </p>
            </div>
            <StatusBadge status={p.status} />
          </div>
          <Progress project={p} />
          <p className="text-xs text-muted-foreground">
            Target {formatDate(p.target_date)}
            {p.delayed ? <span className="font-semibold text-destructive-strong"> · Past target date</span> : null}
            {p.lead ? ` · Lead ${p.lead}` : ""}
            {showRole && p.my_role ? <span className="font-medium text-foreground"> · Your role: {p.my_role}</span> : null}
          </p>
        </li>
      ))}
    </ul>
  );
}
