import type { LucideIcon } from "lucide-react";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

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
    <Card id={id} aria-labelledby={`${id}-title`} className={cn("scroll-mt-4", className)}>
      <CardHeader className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <CardTitle id={`${id}-title`}>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
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
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  tone?: "default" | "warning" | "danger";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-card p-4 shadow-xs" data-testid="metric-card">
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
      <div className="text-2xl font-semibold tracking-tight">{value}</div>
      {hint ? <div className="text-xs text-subtle">{hint}</div> : null}
    </div>
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
        <Info className="size-4 text-subtle" aria-hidden="true" />
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
    <div className="-mx-1 overflow-x-auto px-1" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

export const TH = "whitespace-nowrap px-2 py-2 text-left text-[11.5px] font-semibold uppercase tracking-[0.04em] text-subtle";
export const TD = "px-2 py-2.5 align-top text-[13px]";

export function DashboardSkeleton() {
  const block = "animate-pulse rounded-xl bg-muted";
  return (
    <div role="status" aria-live="polite" aria-label="Loading dashboard" data-testid="dashboard-skeleton" className="flex flex-col gap-4">
      <span className="sr-only">Loading your dashboard…</span>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={cn(block, "h-[104px]")} />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className={cn(block, "h-64")} />
        <div className={cn(block, "h-64")} />
      </div>
      <div className={cn(block, "h-48")} />
    </div>
  );
}
