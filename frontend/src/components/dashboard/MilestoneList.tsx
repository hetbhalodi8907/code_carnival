import { formatDate } from "@/lib/dashboardFormat";
import { EmptyNote, StatusBadge } from "@/components/dashboard/primitives";
import type { MilestoneItem } from "@/types/dashboard";

/** Milestones with their due date; overdue and blocked states are spelled out in words. */
export function MilestoneList({ items, empty, showCompleted = false }: { items: MilestoneItem[]; empty: string; showCompleted?: boolean }) {
  if (items.length === 0) return <EmptyNote>{empty}</EmptyNote>;
  return (
    <ul className="divide-y divide-border">
      {items.map((m) => (
        <li key={`${m.project_code}-${m.title}`} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 py-2.5 first:pt-0 last:pb-0">
          <div className="min-w-0">
            <p className="text-[13.5px] font-medium">{m.title}</p>
            <p className="text-xs text-subtle">
              {m.project_code} · {m.project_name}
            </p>
            {m.blocker_note ? <p className="mt-1 text-xs text-destructive-strong">Blocker: {m.blocker_note}</p> : null}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1 text-right">
            <StatusBadge status={m.status} />
            <span className="text-xs text-muted-foreground">
              {showCompleted && m.completed_on ? `Completed ${formatDate(m.completed_on)}` : `Due ${formatDate(m.due_date)}`}
              {m.overdue ? <span className="font-semibold text-destructive-strong"> · Overdue</span> : null}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
