/** Presentation helpers for the dashboard. They format backend values; they never compute metrics. */

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" -> "5 Oct 2026". Date-only values are read as written, so no time zone can shift them. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not set";
  const match = DATE_ONLY.exec(value);
  if (match) return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not set";
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown time";
  return parsed.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** "2026-04" -> "Apr 26". */
export function formatMonth(value: string): string {
  const [year, month] = value.split("-");
  return `${MONTHS[Number(month) - 1] ?? value} ${year.slice(2)}`;
}

/**
 * Money in the row's own currency. Rupee amounts use lakh/crore, as Nexora's documents do;
 * other currencies use the standard grouping. `compact` shortens large amounts for chart labels.
 */
export function formatMoney(amount: number, currency: string, compact = false): string {
  if (currency === "INR") {
    const abs = Math.abs(amount);
    if (compact || abs >= 1e7) {
      if (abs >= 1e7) return `₹${(amount / 1e7).toFixed(2)} Cr`;
      if (abs >= 1e5) return `₹${(amount / 1e5).toFixed(2)} L`;
    }
    return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  }
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : 2,
    }).format(amount);
  } catch {
    return `${amount.toLocaleString("en-US")} ${currency}`;
  }
}

/** A percentage, or "Not available" when the server had no valid figure (never a silent 0%). */
export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not available" : `${value.toFixed(1).replace(/\.0$/, "")}%`;
}

/** Badge colour for a status. The status text is always shown too, so colour is never the only signal. */
export function statusTone(status: string): "default" | "muted" | "success" | "warning" | "destructive" {
  switch (status) {
    case "Completed":
    case "Approved":
    case "ready":
      return "success";
    case "In progress":
      return "default";
    case "Pending":
      return "warning";
    case "Blocked":
    case "Rejected":
      return "destructive";
    default:
      return "muted";
  }
}
