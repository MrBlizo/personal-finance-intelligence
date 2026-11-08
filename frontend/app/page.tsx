"use client";
import Link from "next/link";
import { useState } from "react";
import Plot from "@/components/Plot";
import { Banner, Empty, Kpi, PageHead, Spinner, useLoad } from "@/components/ui";
import { Insight, PlotFigure, Summary, get, post } from "@/lib/api";
import { money, pct, signClass } from "@/lib/format";

const PERIODS: Record<string, string> = {
  this_month: "This month", last_3_months: "3 months",
  last_12_months: "12 months", year_to_date: "Year to date",
};
const SEV: Record<string, string> = {
  warning: "var(--warn)", positive: "var(--pos)", info: "var(--accent)",
};

type Dash = { summary: Summary; charts: Record<string, PlotFigure> };

export default function Dashboard() {
  const [period, setPeriod] = useState("last_12_months");
  const periods = useLoad(() =>
    get<Record<string, [string, string]>>("/api/analytics/periods"));
  const range = periods.data?.[period];
  const dash = useLoad(async () => range ? get<Dash>("/api/analytics/dashboard", {
    start: range[0], end: range[1],
    charts: ["monthly_cashflow", "category_breakdown", "net_worth",
      "budget_vs_actual"],
  }) : null, [range?.[0], range?.[1]]);
  const insights = useLoad(() =>
    get<{ insights: Insight[] }>("/api/insights"));
  const [seeding, setSeeding] = useState(false);
  const s = dash.data?.summary;
  const cur = s?.currency ?? "CHF";
  const empty = s && s.transactions === 0 && s.net_worth === 0;

  return (
    <>
      <PageHead title="Dashboard" sub="Your finances at a glance">
        <div className="chips">
          {Object.entries(PERIODS).map(([k, label]) => (
            <button key={k} className={k === period ? "on" : ""}
              onClick={() => setPeriod(k)}>{label}</button>))}
        </div>
      </PageHead>
      {dash.error && <Banner kind="error">{dash.error}</Banner>}
      {s && s.missing_fx.length > 0 && (
        <Banner kind="warning">
          No exchange rate to {cur} for {s.missing_fx.join(", ")}: those
          amounts are left out. <Link href="/settings/">Add rates</Link>.
        </Banner>)}
      {s && s.unpriced_holdings.length > 0 && (
        <Banner kind="info">
          No price entered for {s.unpriced_holdings.join(", ")}; they count as
          zero. <Link href="/investments/">Update prices</Link>.
        </Banner>)}
      {empty && (
        <Banner kind="info">
          <b>Welcome!</b> Start by <Link href="/accounts/">adding an
          account</Link> and <Link href="/import/">importing a bank CSV</Link>,
          or explore with a synthetic demo dataset (removable in Settings).{" "}
          <button className="primary" disabled={seeding} onClick={async () => {
            setSeeding(true);
            try { await post("/api/demo"); await dash.reload(); insights.reload(); }
            finally { setSeeding(false); }
          }}>{seeding ? "Generating…" : "Load demo data"}</button>
        </Banner>)}
      {!s && dash.loading && <Spinner label="Loading…" />}
      {s && (
        <div className="stack">
          <div className="grid kpis">
            <Kpi label="Net worth" value={money(s.net_worth, cur)}
              sub={`Liquid ${money(s.liquid, undefined, 0)} · Invested ${money(s.investments, undefined, 0)}`} />
            <Kpi label="Income" value={money(s.income, cur)}
              sub={`Ø ${money(s.avg_monthly_income, undefined, 0)} / month`} />
            <Kpi label="Expenses" value={money(s.expenses, cur)}
              sub={`Ø ${money(s.avg_monthly_expenses, undefined, 0)} / month`} />
            <Kpi label="Net saved" value={money(s.net, cur)} cls={signClass(s.net)}
              sub={`${s.transactions} transactions`} />
            <Kpi label="Savings rate" value={pct(s.savings_rate)}
              cls={signClass(s.savings_rate)} sub="(income − expenses) / income" />
          </div>
          <div className="grid g2">
            <div className="card"><h3>Income vs. expenses</h3>
              <Plot figure={dash.data?.charts.monthly_cashflow} /></div>
            <div className="card"><h3>Where the money goes</h3>
              <Plot figure={dash.data?.charts.category_breakdown} /></div>
            <div className="card"><h3>Net worth</h3>
              <Plot figure={dash.data?.charts.net_worth} /></div>
            <div className="card"><h3>Budgets this month</h3>
              <Plot figure={dash.data?.charts.budget_vs_actual} /></div>
          </div>
          <div className="card">
            <div className="page-head" style={{ marginBottom: 4 }}>
              <h3>Insights</h3><Link href="/insights/">All insights →</Link>
            </div>
            {insights.data?.insights.length === 0 &&
              <Empty>No notable patterns yet.</Empty>}
            {insights.data?.insights.slice(0, 5).map((i, n) => (
              <div className="insight" key={n}>
                <span className="dot" style={{ background: SEV[i.severity] }} />
                <div><b>{i.title}</b><div className="muted small">{i.detail}</div></div>
              </div>))}
          </div>
        </div>)}
    </>
  );
}
