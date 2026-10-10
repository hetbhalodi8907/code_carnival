import type { LucideIcon } from "lucide-react";
import { Info } from "lucide-react";
import { Children, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { statusTone } from "@/lib/dashboardFormat";
import { cn } from "@/lib/utils";
import type { UnavailableMetric } from "@/types/dashboard";

/** A titled section of the dashboard. The id doubles as an in-page anchor for shortcuts. */
export function Panel({
  id,
  title,
  description,
  action,
  children,
  className,
}: {
  id: string;
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card id={id} aria-labelledby={`${id}-title`} className={cn("min-w-0 scroll-mt-4", className)}>
      <CardHeader className="flex flex-wrap items-start justify-between gap-2 px-4 py-3.5 sm:px-5 sm:py-4">
        <div className="min-w-0">
          <CardTitle id={`${id}-title`} className="text-base">
            {title}
          </CardTitle>
          {description ? <CardDescription className="mt-1 max-w-[72ch] leading-relaxed">{description}</CardDescription> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent className="min-w-0 p-4 sm:p-5">{children}</CardContent>
    </Card>
  );
}

/** One headline number. `hint` explains it; `tone` is only a visual accent, never the only signal. */
export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  compact = false,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  tone?: "default" | "warning" | "danger";
  /** A smaller value for text rather than a number (e.g. "4 pdf · 1 image"). */
  compact?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-border bg-card p-4 shadow-xs" data-testid="metric-card">
      <div className="flex items-center gap-2 text-[12.5px] font-medium text-muted-foreground">
        <span
          className={cn(
            "inline-flex size-7 items-center justify-center rounded-lg",
            tone === "default" && "bg-primary-soft text-primary",
            tone === "warning" && "bg-warning-soft text-warning-strong",
            tone === "danger" && "bg-destructive-soft text-destructive-strong",
          )}
        >
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <span className="truncate">{label}</span>
      </div>
      <div className={cn("break-words font-semibold tracking-tight", compact ? "text-lg leading-8" : "text-2xl")}>{value}</div>
      {hint ? <div className="text-xs leading-snug text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

/** Columns per card count (literal strings so Tailwind can see them): a row is always filled or evenly split. */
const STAT_COLUMNS: Record<number, string> = {
  1: "",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-2 xl:grid-cols-4",
  5: "sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5",
  6: "sm:grid-cols-3",
};

/**
 * A responsive row of metric cards. The column count follows the number of cards, so three cards share one row
 * and four form a 2x2 or 4x1 grid, instead of leaving an empty slot. Children may shrink (min-w-0) rather than
 * stretching the page.
 */
export function StatGrid({ children, className }: { children: ReactNode; className?: string }) {
  const count = Children.toArray(children).length;
  return (
    <div className={cn("grid grid-cols-1 gap-3 *:min-w-0", STAT_COLUMNS[count] ?? "sm:grid-cols-2 lg:grid-cols-3", className)}>
      {children}
    </div>
  );
}

/** The label above a group of content inside a panel: one level below the panel title. */
export function SectionTitle({ children, icon: Icon }: { children: ReactNode; icon?: LucideIcon }) {
  return (
    <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">
      {Icon ? <Icon className="size-4 shrink-0" aria-hidden="true" /> : null}
      {children}
    </h3>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={statusTone(status)}>{status}</Badge>;
}

/** Horizontal bars with the value always printed beside them (the bar is a visual aid only). */
export function BarList({
  rows,
  format = (n) => String(n),
  emptyText = "Nothing recorded.",
}: {
  rows: { label: string; value: number; note?: string }[];
  format?: (value: number) => string;
  emptyText?: string;
}) {
  if (rows.length === 0) return <EmptyNote>{emptyText}</EmptyNote>;
  const max = Math.max(...rows.map((row) => row.value), 0);
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.label}>
          <div className="flex items-baseline justify-between gap-3 text-[13px]">
            <span className="min-w-0 truncate font-medium">{row.label}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{row.note ? `${row.note} · ` : ""}{format(row.value)}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
            <div className="h-full rounded-full bg-primary" style={{ width: `${max > 0 ? Math.max(2, (row.value / max) * 100) : 0}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** A budget-style gauge. Over 100% is shown as it is (and flagged in text), not clamped away. */
export function Gauge({ percent, label }: { percent: number | null; label: string }) {
  if (percent === null) return <p className="text-sm text-muted-foreground">{label}: not available (no valid budget).</p>;
  const over = percent > 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="font-medium">{label}</span>
        <span className={cn("tabular-nums font-semibold", over && "text-destructive-strong")}>
          {percent.toFixed(1).replace(/\.0$/, "")}%{over ? " (over budget)" : ""}
        </span>
      </div>
      <div
        className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, Math.round(percent))}
      >
        <div className={cn("h-full rounded-full", over ? "bg-destructive" : percent >= 85 ? "bg-warning" : "bg-primary")} style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-border-strong bg-surface-2 px-4 py-5 text-center text-[13.5px] text-muted-foreground">{children}</p>;
}

/** Metrics the application cannot compute because nothing is stored for them (distinct from a zero). */
export function UnavailableList({ items }: { items: UnavailableMetric[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="unavailable-title" className="rounded-xl border border-dashed border-border-strong bg-surface-2 p-4">
      <h2 id="unavailable-title" className="flex items-center gap-2 text-[13.5px] font-semibold">
        <Info className="size-4 text-muted-foreground" aria-hidden="true" />
        Not available in this deployment
      </h2>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.key} className="text-[13px] leading-snug">
            <span className="font-medium">{item.label}.</span> <span className="text-muted-foreground">{item.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TableWrap({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div
      className={cn(
        "max-w-full overflow-x-auto overscroll-x-contain rounded-lg border border-border",
        // The first column stays visible while the rest scrolls sideways on narrow screens.
        "[&_td:first-child]:sticky [&_td:first-child]:left-0 [&_td:first-child]:z-[1] [&_td:first-child]:bg-card",
        "[&_th:first-child]:sticky [&_th:first-child]:left-0 [&_th:first-child]:z-[1] [&_th:first-child]:bg-surface-2",
        "[&_tbody_tr:hover>*]:bg-muted/40",
      )}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      {children}
    </div>
  );
}

export const TH = "whitespace-nowrap bg-surface-2 px-3 py-2.5 text-left text-[11.5px] font-semibold uppercase tracking-[0.05em] text-muted-foreground";
export const TD = "bg-card px-3 py-2.5 align-top text-[13px] transition-colors";

export function DashboardSkeleton() {
  const block = "animate-pulse rounded-xl bg-muted";
  return (
    <div role="status" aria-live="polite" aria-label="Loading dashboard" data-testid="dashboard-skeleton" className="flex flex-col gap-4">
      <span className="sr-only">Loading your dashboard…</span>
      <StatGrid>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={cn(block, "h-[104px]")} />
        ))}
      </StatGrid>
      <div className="grid gap-4 *:min-w-0 lg:grid-cols-2">
        <div className={cn(block, "h-64")} />
        <div className={cn(block, "h-64")} />
      </div>
      <div className={cn(block, "h-48")} />
    </div>
  );
}
