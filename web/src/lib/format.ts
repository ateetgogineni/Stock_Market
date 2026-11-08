const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function formatInr(v: number | null | undefined): string {
  return v == null ? "—" : inr.format(v);
}

export function formatCrore(v: number | null | undefined): string {
  return v == null ? "—" : `₹${num.format(v / 1e7)} crore`;
}

export function formatPct(v: number | null | undefined, dp = 2): string {
  return v == null ? "—" : `${(v * 100).toFixed(dp)}%`;
}

export function formatSigned(v: number | null | undefined, dp = 2): string {
  return v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) + " IST";
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00+05:30` : iso);
  return d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });
}

export const DATA_STATUS_LABEL: Record<string, string> = {
  live: "Live",
  delayed: "Delayed quote",
  end_of_day: "End of day",
  stale: "Stale",
  unavailable: "Unavailable",
};

export const RATING_LABEL: Record<string, string> = {
  BUY: "BUY",
  HOLD: "HOLD",
  SELL: "SELL",
  INSUFFICIENT_DATA: "INSUFFICIENT DATA",
};
