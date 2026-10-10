import { AlertTriangle, CalendarClock, CheckCircle2, Users } from "lucide-react";

import { MilestoneList } from "@/components/dashboard/MilestoneList";
import { ProjectList } from "@/components/dashboard/ProjectList";
import { BarList, EmptyNote, Panel, SectionTitle } from "@/components/dashboard/primitives";
import { formatPercent } from "@/lib/dashboardFormat";
import type { ProjectsSection } from "@/types/dashboard";

export function ProjectsPanel({ data }: { data: ProjectsSection }) {
  return (
    <Panel
      id="projects"
      title="Projects"
      description={`${data.scope_label} · ${data.total} ${data.total === 1 ? "project" : "projects"}, ${data.active} in progress`}
    >
      <div className="grid gap-6 *:min-w-0 lg:grid-cols-3">
        <div>
          <SectionTitle icon={CheckCircle2}>Projects by status</SectionTitle>
          <BarList rows={data.by_status.map((s) => ({ label: s.label, value: s.count }))} emptyText="No projects recorded." />
          <p className="mt-4 text-[13px] text-muted-foreground">
            Milestone completion:{" "}
            <span className="font-semibold text-foreground">
              {data.milestones.total > 0
                ? `${data.milestones.completed} of ${data.milestones.total} (${formatPercent(data.milestones.percent_complete)})`
                : "no milestones recorded"}
            </span>
          </p>
        </div>
        <div>
          <SectionTitle icon={CalendarClock}>Upcoming milestones</SectionTitle>
          <MilestoneList items={data.upcoming_milestones} empty="No open milestones." />
        </div>
        <div>
          <SectionTitle icon={AlertTriangle}>Blockers and delays</SectionTitle>
          {data.blocked_milestones.length === 0 && data.delayed_projects.length === 0 ? (
            <EmptyNote>No blocked milestones or projects past their target date are recorded.</EmptyNote>
          ) : (
            <>
              <MilestoneList items={data.blocked_milestones} empty="" />
              {data.delayed_projects.length > 0 ? (
                <ul className="mt-3 flex flex-col gap-1.5 text-[13px]">
                  {data.delayed_projects.map((p) => (
                    <li key={p.code}>
                      <span className="font-medium">{p.name}</span> <span className="text-destructive-strong">is past its target date</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
        </div>
      </div>

      <div className="mt-8 grid gap-6 *:min-w-0 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionTitle icon={Users}>All projects in scope</SectionTitle>
          <ProjectList projects={data.projects} empty="No projects are available to your account." />
        </div>
        <div className="flex flex-col gap-6">
          <div>
            <SectionTitle icon={Users}>Open projects per person</SectionTitle>
            <BarList
              rows={data.workload.map((w) => ({ label: w.name, value: w.active_projects }))}
              emptyText="No assignments are recorded."
              format={(n) => `${n} ${n === 1 ? "project" : "projects"}`}
            />
          </div>
          <div>
            <SectionTitle icon={CheckCircle2}>Recent updates</SectionTitle>
            <MilestoneList items={data.recent_updates} empty="No milestones have been completed yet." showCompleted />
          </div>
        </div>
      </div>
    </Panel>
  );
}
