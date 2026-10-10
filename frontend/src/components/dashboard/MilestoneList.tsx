import { formatDate } from "@/lib/dashboardFormat";
import { EmptyNote, StatusBadge } from "@/components/dashboard/primitives";
import type { MilestoneItem } from "@/types/dashboard";

/** Milestones with their due date; overdue and blocked states are spelled out in words. */
export function MilestoneList({ items, empty, showCompleted = false }: { items: MilestoneItem[]; empty: string; showCompleted?: boolean }) {
  if (items.length === 0) return <EmptyNote>{empty}</EmptyNote>;
  return (
    <ul className="m-0 list-none divide-y divide-border p-0">
      {items.map((m) => (
        <li key={`${m.project_code}-${m.title}`} className="py-2.5 first:pt-0 last:pb-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium leading-snug">{m.title}</p>
              <p className="text-xs text-muted-foreground">
                {m.project_code} · {m.project_name}
              </p>
            </div>
            <StatusBadge status={m.status} />
          </div>
          {m.blocker_note ? <p className="mt-1 text-xs leading-snug text-destructive-strong">Blocker: {m.blocker_note}</p> : null}
          <p className="mt-1 text-xs text-muted-foreground">
            {showCompleted && m.completed_on ? `Completed ${formatDate(m.completed_on)}` : `Due ${formatDate(m.due_date)}`}
            {m.overdue ? <span className="font-semibold text-destructive-strong"> · Overdue</span> : null}
          </p>
        </li>
      ))}
    </ul>
  );
}
