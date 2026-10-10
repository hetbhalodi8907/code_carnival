import { Banknote, Clock, PiggyBank, TrendingUp } from "lucide-react";

import { BarList, EmptyNote, Gauge, MetricCard, Panel, SectionTitle, StatGrid, StatusBadge, TD, TH, TableWrap } from "@/components/dashboard/primitives";
import { formatDate, formatMoney, formatMonth } from "@/lib/dashboardFormat";
import type { ExpenseItem, FinanceCurrency, FinanceSection } from "@/types/dashboard";

const CHART_HEIGHT = 112;

function MonthlyChart({ currency, data }: { currency: string; data: FinanceCurrency["monthly_spend"] }) {
  if (data.length === 0) return <EmptyNote>No approved spending is recorded yet.</EmptyNote>;
  const max = Math.max(...data.map((m) => m.amount), 1);
  return (
    <figure className="m-0 rounded-lg border border-border bg-surface-2 px-3 pb-3 pt-4">
      <div className="overflow-x-auto">
        <ul className="m-0 flex min-w-full list-none items-end justify-around gap-1.5 p-0" aria-label={`Approved monthly spending in ${currency}`}>
          {data.map((m) => (
            <li key={m.month} className="flex min-w-[40px] flex-1 flex-col items-center gap-1.5">
              <span className="text-[11px] font-medium tabular-nums text-muted-foreground">{formatMoney(m.amount, currency, true)}</span>
              {/* The track makes every month the same width and height; the fill is the month's share of the largest month. */}
              <div className="relative flex w-8 items-end overflow-hidden rounded-md bg-muted" style={{ height: CHART_HEIGHT }} aria-hidden="true">
                <div className="w-full rounded-md bg-primary" style={{ height: Math.max(3, Math.round((m.amount / max) * CHART_HEIGHT)) }} />
              </div>
              <span className="text-xs font-medium">{formatMonth(m.month)}</span>
            </li>
          ))}
        </ul>
      </div>
      <figcaption className="sr-only">Approved expenses per month in {currency}.</figcaption>
    </figure>
  );
}

function CurrencyBlock({ block, single }: { block: FinanceCurrency; single: boolean }) {
  const c = block.currency;
  return (
    <div className="flex flex-col gap-5" data-testid={`finance-${c}`}>
      {!single ? <h3 className="text-sm font-semibold">Amounts in {c} <span className="font-normal text-muted-foreground">(never combined with other currencies)</span></h3> : null}
      <StatGrid>
        <MetricCard label="Actual spend (approved)" value={formatMoney(block.actual_spend, c)} icon={Banknote} hint="Approved expenses only" />
        <MetricCard
          label="Approved budget"
          value={block.approved_budget === null ? "Not available" : formatMoney(block.approved_budget, c)}
          icon={PiggyBank}
          hint={block.approved_budget === null ? `No budget is recorded in ${c}` : "Sum of project budgets"}
        />
        <MetricCard
          label="Remaining budget"
          value={block.remaining_budget === null ? "Not available" : formatMoney(block.remaining_budget, c)}
          icon={TrendingUp}
          tone={block.remaining_budget !== null && block.remaining_budget < 0 ? "danger" : "default"}
          hint={block.remaining_budget !== null && block.remaining_budget < 0 ? "Spending exceeds the approved budget" : undefined}
        />
        <MetricCard
          label="Awaiting approval"
          value={formatMoney(block.pending_amount, c)}
          icon={Clock}
          tone={block.pending_count > 0 ? "warning" : "default"}
          hint={`${block.pending_count} pending ${block.pending_count === 1 ? "expense" : "expenses"}`}
        />
      </StatGrid>
      <Gauge percent={block.utilization_percent} label="Budget utilization" />
      <div className="grid items-start gap-6 *:min-w-0 lg:grid-cols-2">
        <div>
          <SectionTitle>Monthly spending trend</SectionTitle>
          <MonthlyChart currency={c} data={block.monthly_spend} />
        </div>
        <div>
          <SectionTitle>Spending by category</SectionTitle>
          <BarList rows={block.by_category.map((x) => ({ label: x.label, value: x.amount }))} format={(n) => formatMoney(n, c)} emptyText="No approved spending is recorded yet." />
        </div>
      </div>
      <div>
        <SectionTitle>Budget versus actual by project</SectionTitle>
        <TableWrap label={`Spending by project in ${c}`}>
          <table className="w-full min-w-[540px] border-collapse">
            <thead>
              <tr>
                <th scope="col" className={TH}>Project</th>
                <th scope="col" className={`${TH} text-right`}>Budget</th>
                <th scope="col" className={`${TH} text-right`}>Actual</th>
                <th scope="col" className={`${TH} text-right`}>Pending</th>
                <th scope="col" className={`${TH} text-right`}>Utilization</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {block.by_project.map((p) => (
                <tr key={p.code}>
                  <td className={TD}>
                    <span className="font-medium">{p.name}</span> <span className="text-xs text-muted-foreground">{p.code}</span>
                  </td>
                  <td className={`${TD} text-right tabular-nums`}>{p.budget === null ? "Not available" : formatMoney(p.budget, c)}</td>
                  <td className={`${TD} text-right tabular-nums`}>{formatMoney(p.actual, c)}</td>
                  <td className={`${TD} text-right tabular-nums`}>{formatMoney(p.pending, c)}</td>
                  <td className={`${TD} text-right tabular-nums ${p.utilization_percent !== null && p.utilization_percent > 100 ? "font-semibold text-destructive-strong" : ""}`}>
                    {p.utilization_percent === null ? "Not available" : `${p.utilization_percent}%${p.utilization_percent > 100 ? " (over)" : ""}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </div>
    </div>
  );
}

function RecentExpenses({ items }: { items: ExpenseItem[] }) {
  if (items.length === 0) return <EmptyNote>No expenses are recorded.</EmptyNote>;
  return (
    <TableWrap label="Recent expenses">
      <table className="w-full min-w-[620px] border-collapse">
        <thead>
          <tr>
            <th scope="col" className={TH}>Date</th>
            <th scope="col" className={TH}>Category</th>
            <th scope="col" className={TH}>Project</th>
            <th scope="col" className={`${TH} text-right`}>Amount</th>
            <th scope="col" className={`${TH} pl-6`}>Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((e, index) => (
            <tr key={`${e.project_code}-${e.expense_date}-${index}`}>
              <td className={`${TD} whitespace-nowrap`}>{formatDate(e.expense_date)}</td>
              <td className={TD}>
                {e.category}
                {e.description ? <span className="block text-xs text-muted-foreground">{e.description}</span> : null}
              </td>
              <td className={TD}>{e.project_code}</td>
              <td className={`${TD} text-right tabular-nums`}>{formatMoney(e.amount, e.currency)}</td>
              <td className={`${TD} pl-6`}>
                <StatusBadge status={e.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export function FinancePanel({ data }: { data: FinanceSection }) {
  return (
    <Panel id="finance" title="Finance" description="Budgets and expenses recorded in the demo dataset. Actual spend counts approved expenses only.">
      {data.currencies.length === 0 ? (
        <EmptyNote>No budgets or expenses are recorded.</EmptyNote>
      ) : (
        <div className="flex flex-col gap-8">
          {data.currencies.map((block) => (
            <CurrencyBlock key={block.currency} block={block} single={data.currencies.length === 1} />
          ))}
        </div>
      )}
      <div className="mt-8" />
      <SectionTitle>Recent expenses</SectionTitle>
      <RecentExpenses items={data.recent_expenses} />
    </Panel>
  );
}
