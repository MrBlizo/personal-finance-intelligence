"use client";
import { useState } from "react";
import Plot from "@/components/Plot";
import { accountOptions, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Spinner, clean, useLoad,
} from "@/components/ui";
import { Forecast, Recurring, del, get, post, put } from "@/lib/api";
import { FREQUENCIES, date, money, pct, signClass, today } from "@/lib/format";

export default function ForecastPage() {
  const refs = useRefs();
  const [horizon, setHorizon] = useState(90);
  const [threshold, setThreshold] = useState(0);
  const fc = useLoad(() => get<Forecast>("/api/forecast", { horizon_days: horizon, threshold }),
    [horizon, threshold]);
  const rec = useLoad(() => get<Recurring[]>("/api/recurring"));
  const [edit, setEdit] = useState<Recurring | "new" | null>(null);
  const [remove, setRemove] = useState<Recurring | null>(null);
  const f = fc.data;
  const cur = f?.base_currency ?? "CHF";
  const accounts = refs.data?.accounts ?? [];
  const cats = refs.data?.categories ?? [];
  const reload = () => { rec.reload(); fc.reload(); };

  return (
    <>
      <PageHead title="Cash-flow forecast" sub="Model prediction for checking, savings, cash and card accounts">
        <div className="chips">{[30, 90, 180, 365].map((d) => (
          <button key={d} className={d === horizon ? "on" : ""} onClick={() => setHorizon(d)}>{d} days</button>))}</div>
        <label className="field">Alert below ({cur})
          <input type="number" value={threshold} style={{ width: 110 }}
            onChange={(e) => setThreshold(Number(e.target.value))} /></label>
      </PageHead>
      {fc.error && <Banner kind="error">{fc.error}</Banner>}
      {f?.notes.map((n) => <Banner key={n} kind="warning">{n}</Banner>)}
      {fc.loading && !f && <Spinner label="Simulating…" />}
      {f && (
        <div className="stack">
          <div className="grid kpis">
            <Kpi label="Balance today" value={money(f.start_balance, cur)} />
            <Kpi label={`Median in ${horizon} days`} value={money(f.p50[f.p50.length - 1], cur)}
              sub={`90% range ${money(f.p5[f.p5.length - 1], undefined, 0)} – ${money(f.p95[f.p95.length - 1], undefined, 0)}`} />
            <Kpi label={`Chance of dropping below ${money(threshold, undefined, 0)}`}
              value={pct(f.prob_below_threshold, 0)}
              cls={f.prob_below_threshold > 0.2 ? "neg" : f.prob_below_threshold > 0.05 ? "" : "pos"} />
            <Kpi label="Scheduled net (recurring)" value={money(f.scheduled_total, cur)} cls={signClass(f.scheduled_total)}
              sub={`Everyday spending Ø ${money(f.discretionary_daily_mean, undefined)} / day`} />
          </div>
          <div className="card">
            <Plot figure={f.figure} height={380} />
            <p className="small muted">{f.method} {f.simulations} simulations, learned from the last
              {" "}{f.lookback_days_used} days. Bands show the range of simulated outcomes, not a guarantee;
              past behaviour may not repeat.</p>
          </div>
          <div className="grid g2">
            <div className="card table-wrap">
              <div className="page-head" style={{ marginBottom: 8 }}>
                <h3 style={{ margin: 0 }}>Recurring items</h3>
                <button className="primary" onClick={() => setEdit("new")}>+ Add</button>
              </div>
              {rec.data?.length === 0 && <Empty>Add salary, rent, insurance… to improve the forecast.
                See Insights for detected subscriptions.</Empty>}
              {!!rec.data?.length && (
                <table><thead><tr><th>Name</th><th>Every</th><th>Next</th><th className="num">Amount</th><th /></tr></thead>
                  <tbody>{rec.data.map((r) => (
                    <tr key={r.id} style={{ opacity: r.is_active ? 1 : 0.5 }}>
                      <td>{r.name}<div className="small muted">{accounts.find((a) => a.id === r.account_id)?.name}</div></td>
                      <td>{FREQUENCIES[r.frequency]}</td><td>{date(r.next_date)}</td>
                      <td className={`num ${signClass(r.amount)}`}>{money(r.amount)}</td>
                      <td className="num"><button className="link" onClick={() => setEdit(r)}>Edit</button>
                        <button className="link danger" onClick={() => setRemove(r)}>Delete</button></td>
                    </tr>))}</tbody></table>)}
            </div>
            <div className="card table-wrap">
              <h3>Upcoming scheduled items</h3>
              {f.upcoming.length === 0 ? <Empty>Nothing scheduled in this horizon.</Empty> : (
                <table><tbody>{f.upcoming.map((u, i) => (
                  <tr key={i}><td>{date(u.date)}</td><td>{u.name}</td>
                    <td className={`num ${signClass(u.amount_base)}`}>{money(u.amount_base, cur)}</td></tr>))}
                </tbody></table>)}
            </div>
          </div>
        </div>)}
      {edit && (() => {
        const r = edit === "new" ? null : edit;
        return (
          <FormModal title={r ? `Edit ${r.name}` : "Add recurring item"} onClose={() => setEdit(null)}
            initial={r ? { ...r } as never : { name: "", account_id: accountOptions(accounts)[0]?.value ?? "",
              category_id: "", amount: "", frequency: "monthly", start_date: today(), end_date: "", is_active: true }}
            fields={[
              { name: "name", label: "Name", required: true, full: true },
              { name: "account_id", label: "Account", type: "select", required: true, options: accountOptions(accounts) },
              { name: "category_id", label: "Category", type: "select", options: categoryOptions(cats),
                help: "Needed to recognise past payments of this item." },
              { name: "amount", label: "Amount (+ income, − expense)", type: "number", step: "0.01", required: true },
              { name: "frequency", label: "Frequency", type: "select", required: true,
                options: Object.entries(FREQUENCIES).map(([value, label]) => ({ value, label })) },
              { name: "start_date", label: "First date", type: "date", required: true },
              { name: "end_date", label: "End date (optional)", type: "date" },
              { name: "is_active", label: "Active", type: "checkbox" },
            ]}
            onSubmit={async (v) => {
              const b = clean(v, ["account_id", "category_id"]);
              const body = { name: b.name, account_id: b.account_id, category_id: b.category_id,
                amount: String(b.amount), frequency: b.frequency, start_date: b.start_date,
                end_date: b.end_date, is_active: b.is_active };
              if (r) await put(`/api/recurring/${r.id}`, body); else await post("/api/recurring", body);
              reload();
            }} />);
      })()}
      {remove && <Confirm onClose={() => setRemove(null)} text={`Delete the recurring item “${remove.name}”?`}
        onYes={async () => { await del(`/api/recurring/${remove.id}`); reload(); }} />}
    </>
  );
}
