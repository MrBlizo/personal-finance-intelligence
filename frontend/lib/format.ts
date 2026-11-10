// Formatting helpers (Swiss conventions: 1'234.50).

const nf = new Map<number, Intl.NumberFormat>();
function fmt(decimals: number) {
  if (!nf.has(decimals)) {
    nf.set(decimals, new Intl.NumberFormat("de-CH", {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    }));
  }
  return nf.get(decimals)!;
}

// In right-to-left layouts, numbers such as 53'093 must be kept as one
// left-to-right run, otherwise the bidi algorithm reorders the groups.
// Unicode isolates (LRI ... PDI) do that and are invisible.
const isolate = (s: string) =>
  typeof document !== "undefined" && document.documentElement.dir === "rtl"
    ? `\u2066${s}\u2069` : s;

export function money(v: number | null | undefined, currency?: string,
  decimals = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = fmt(decimals).format(v);
  return isolate(currency ? `${currency} ${s}` : s);
}

export function num(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return isolate(fmt(decimals).format(v));
}

export function pct(v: number | null | undefined, decimals = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return isolate(`${(v * 100).toFixed(decimals)} %`);
}

export function date(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? v + "T00:00:00" : v);
  return isolate(d.toLocaleDateString("de-CH", {
    day: "2-digit", month: "2-digit", year: "numeric",
  }));
}

export function iso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const today = () => iso(new Date());

export function signClass(v: number | null | undefined): string {
  if (!v) return "";
  return v > 0 ? "pos" : "neg";
}

export const ACCOUNT_TYPES: Record<string, string> = {
  checking: "Checking", savings: "Savings", cash: "Cash",
  credit_card: "Credit card", investment: "Investment", loan: "Loan",
};
export const ASSET_CLASSES: Record<string, string> = {
  stock: "Stock", etf: "ETF", bond: "Bond", fund: "Fund", crypto: "Crypto",
  real_estate: "Real estate", commodity: "Commodity", cash: "Cash",
  other: "Other",
};
export const FREQUENCIES: Record<string, string> = {
  weekly: "Weekly", biweekly: "Every 2 weeks", monthly: "Monthly",
  quarterly: "Quarterly", yearly: "Yearly",
};
export const CURRENCIES = ["CHF", "EUR", "MAD", "USD", "GBP", "JPY", "CAD",
  "SEK", "NOK", "DKK", "PLN", "CZK", "AUD", "CNY", "TRY", "AED", "SAR"];

/** File size for people: "820 KB", "1.4 MB", "1.2 GB". */
export function bytes(n: number): string {
  if (n < 1048576) return `${num(Math.max(n, 1024) / 1024, 0)} KB`;
  if (n < 1073741824) return `${num(n / 1048576, 1)} MB`;
  return `${num(n / 1073741824, 1)} GB`;
}
