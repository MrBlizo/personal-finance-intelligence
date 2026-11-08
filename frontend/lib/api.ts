// Typed client for the PFI backend. In production the UI is served by the
// backend itself (same origin); with `next dev` on port 3000 it calls the
// API on 127.0.0.1:8765.

export type Id = number;

export interface Settings {
  base_currency: string;
  currencies_in_use: string[];
  schema_version: number;
  fx_auto_update: boolean;
  fx_last_update: string | null;
}
export interface Backup { name: string; kind: string; size: number; created: string }
export interface Account {
  id: Id; name: string; type: string; currency: string;
  institution: string | null; opening_balance: number; opening_date: string;
  is_archived: boolean; is_demo: boolean; notes: string | null;
  balance: number; balance_base: number | null; holdings_base: number;
}
export interface Category {
  id: Id; name: string; kind: "income" | "expense";
  parent_id: Id | null; color: string | null; full_name: string;
}
export interface Txn {
  id: Id; account_id: Id; account_name: string; currency: string;
  txn_date: string; amount: number; amount_base: number | null;
  kind: "income" | "expense" | "transfer"; description: string;
  merchant: string | null; category_id: Id | null;
  category_name: string | null; transfer_group: string | null;
  import_batch_id: Id | null; trade_id: Id | null; notes: string | null;
}
export interface FxRate {
  id: Id; rate_date: string; from_currency: string; to_currency: string;
  rate: number; source: string;
}
export interface Rule {
  id: Id; pattern: string; match_field: string; is_regex: boolean;
  category_id: Id; priority: number;
}
export interface Recurring {
  id: Id; name: string; account_id: Id; category_id: Id | null;
  amount: number; frequency: string; start_date: string;
  end_date: string | null; is_active: boolean; next_date: string | null;
}
export interface BudgetItem {
  id: Id; category_id: Id; category: string; budget: number; spent: number;
  remaining: number; pct: number | null; projected: number;
  status: "ok" | "at_risk" | "over";
}
export interface BudgetStatus {
  month: string; currency: string; days_elapsed: number;
  days_in_month: number; total_budget: number; total_spent: number;
  items: BudgetItem[]; missing_fx: string[];
}
export interface Goal {
  id: Id; name: string; currency: string; target_amount: number;
  target_date: string | null; account_id: Id | null; saved_amount: number;
  manual_saved_amount: number; priority: number; notes: string | null;
  progress: number; remaining: number; months_left: number | null;
  required_monthly: number | null; recent_monthly_saving: number | null;
  projected_completion: string | null; status: string; note: string | null;
}
export interface Holding {
  id: Id; account_id: Id; symbol: string; name: string; asset_class: string;
  currency: string; quantity: number; avg_cost: number; cost_basis: number;
  last_price: number | null; price_date: string | null;
  market_value: number | null; unrealized_pl: number | null;
  unrealized_pl_pct: number | null; realized_pl: number; dividends: number;
  market_value_base: number | null; cost_basis_base: number | null;
}
export interface Trade {
  id: Id; holding_id: Id; trade_date: string; trade_type: string;
  quantity: number; price: number; fees: number; cash_amount: number | null;
  notes: string | null;
}
export interface Summary {
  currency: string; start: string; end: string; income: number;
  expenses: number; net: number; savings_rate: number | null;
  avg_monthly_income: number; avg_monthly_expenses: number;
  transactions: number; net_worth: number; liquid: number;
  investments: number; liabilities: number; missing_fx: string[];
  unpriced_holdings: string[];
}
export interface Insight {
  type: string; severity: "info" | "warning" | "positive";
  title: string; detail: string; data: Record<string, unknown>;
}
export interface Forecast {
  base_currency: string; origin: string; horizon_days: number;
  simulations: number; lookback_days_used: number; start_balance: number;
  dates: string[]; p5: number[]; p50: number[]; p95: number[];
  expected_end: number; threshold: number; prob_below_threshold: number;
  discretionary_daily_mean: number; scheduled_total: number;
  upcoming: { date: string; name: string; amount_base: number }[];
  notes: string[]; method: string; figure: PlotFigure;
}
export interface ImportPreview {
  filename: string; sha256: string; already_imported: boolean;
  delimiter: string; encoding: string; columns: string[];
  rows: Record<string, string | null>[];
  guess: Record<string, string | boolean | null>;
  preset: { id: Id; name: string; mapping: Record<string, unknown> } | null;
}
export interface ImportResult {
  batch_id: Id; rows_total: number; rows_imported: number;
  rows_duplicate: number; rows_failed: number; errors: string[];
  categorized: number; preset?: string | null;
}
export interface ImportBatch {
  id: Id; account_id: Id; filename: string; rows_total: number;
  rows_imported: number; rows_duplicate: number; rows_failed: number;
  imported_at: string;
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type PlotFigure = { data: any[]; layout: Record<string, any> };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function base(): string {
  if (typeof window === "undefined") return "";
  return window.location.port === "3000" ? "http://127.0.0.1:8765" : "";
}

function detail(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map((e) => {
        const loc = Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "";
        return `${loc ? loc + ": " : ""}${e.msg}`;
      }).join("; ");
    }
  }
  return `Request failed (HTTP ${status}).`;
}

export async function api<T>(path: string, init: RequestInit & {
  json?: unknown; query?: Record<string, unknown>;
} = {}): Promise<T> {
  const { json, query, ...rest } = init;
  let url = base() + path;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)));
      else qs.append(k, String(v));
    }
    const s = qs.toString();
    if (s) url += "?" + s;
  }
  const headers: Record<string, string> = {};
  if (json !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "include", ...rest, headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the PFI backend. If you are " +
      "developing, start it with `python run.py`; otherwise restart PFI.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, res.status));
  return body as T;
}

export const get = <T>(path: string, query?: Record<string, unknown>) =>
  api<T>(path, { query });
export const post = <T>(path: string, json?: unknown,
  query?: Record<string, unknown>) =>
  api<T>(path, { method: "POST", json, query });
export const put = <T>(path: string, json: unknown) =>
  api<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json: unknown) =>
  api<T>(path, { method: "PATCH", json });
export const del = <T = void>(path: string,
  query?: Record<string, unknown>) =>
  api<T>(path, { method: "DELETE", query });
