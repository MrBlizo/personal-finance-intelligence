"use client";
import Link from "next/link";
import { useState } from "react";
import Plot from "@/components/Plot";
import { Banner, Empty, PageHead, Spinner, useLoad } from "@/components/ui";
import { Insight, PlotFigure, get, post } from "@/lib/api";
import { date } from "@/lib/format";

const SEV: Record<string, string> = {
  warning: "var(--warn)", positive: "var(--pos)", info: "var(--accent)",
};
const CHARTS: [string, string][] = [
  ["category_trend", "Spending by category per month"],
  ["savings_rate", "Savings rate per month"],
  ["weekday_heatmap", "Spending by weekday"],
  ["top_merchants", "Top payees (12 months)"],
];

export default function Insights() {
  const ins = useLoad(() => get<{ insights: Insight[]; start: string; end: string }>("/api/insights"));
  const charts = useLoad(async () => {
    const figs = await Promise.all(CHARTS.map(([n]) => get<PlotFigure>(`/api/analytics/charts/${n}`)));
    return Object.fromEntries(CHARTS.map(([n], i) => [n, figs[i]]));
  });
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const addRecurring = async (i: Insight) => {
    const d = i.data as { payee: string; cadence: string; last_amount: number;
      category_id: number | null; account_id: number; last_date: string };
    const freq = d.cadence === "weekly" ? "weekly" : d.cadence;
    try {
      await post("/api/recurring", { name: d.payee, account_id: d.account_id, category_id: d.category_id,
        amount: String(-d.last_amount), frequency: freq, start_date: d.last_date, is_active: true });
      setAdded(new Set(added).add(d.payee));
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <>
      <PageHead title="Insights" sub={ins.data ? `Patterns found from ${date(ins.data.start)} to ${date(ins.data.end)}` : ""} />
      {(ins.error || error) && <Banner kind="error">{ins.error ?? error}</Banner>}
      <div className="stack">
        <div className="card">
          {ins.loading && !ins.data && <Spinner />}
          {ins.data?.insights.length === 0 && <Empty>No notable patterns found. More history gives better insights.</Empty>}
          {ins.data?.insights.map((i, n) => (
            <div className="insight" key={n}>
              <span className="dot" style={{ background: SEV[i.severity] }} />
              <div style={{ flex: 1 }}><b>{i.title}</b><div className="muted small">{i.detail}</div></div>
              {i.type === "subscription" && (
                added.has(String(i.data.payee)) ? <span className="badge ok">Added</span>
                  : <button onClick={() => addRecurring(i)}>Add as recurring</button>)}
              {i.type === "unusual_transaction" && <Link href="/transactions/">Review</Link>}
              {i.type === "data_quality" && i.data.currencies !== undefined && <Link href="/settings/">Fix</Link>}
              {i.type === "data_quality" && i.data.count !== undefined && <Link href="/transactions/?uncategorized=1">Categorize</Link>}
            </div>))}
          <p className="small muted">Insights are statistical observations (robust z-scores, regular payment
            intervals, month-over-month changes), not explanations.</p>
        </div>
        <div className="grid g2">
          {CHARTS.map(([n, title]) => (
            <div className="card" key={n}><h3>{title}</h3><Plot figure={charts.data?.[n]} /></div>))}
        </div>
      </div>
    </>
  );
}
