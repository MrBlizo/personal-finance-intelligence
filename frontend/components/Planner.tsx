"use client";
// What-if planner and financial-independence calculator (Forecast page).
// Both are projections from the user's own history; the backend explains
// its method and the UI says so next to every result.
import { useEffect, useState } from "react";
import { Button, Field, Input, Select, SpinButton } from "@fluentui/react-components";
import Plot from "./Plot";
import { I } from "./icons";
import { Banner, Kpi, Section, Spinner, useLoad } from "./ui";
import { PlotFigure, get, post } from "@/lib/api";
import { money, num, pct, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Change =
  | { kind: "monthly"; amount: number; label?: string; start?: string }
  | { kind: "once"; amount: number; label?: string; start?: string }
  | { kind: "recurring_pct"; recurring_id: number; pct: number; label?: string };
interface Band { p5: number[]; p50: number[]; p95: number[] }
interface WhatIf {
  currency: string; dates: string[]; changes: string[];
  baseline: Band; scenario: Band;
  end: { baseline: number; scenario: number };
  lowest: { baseline: number; scenario: number };
  threshold: number; verdict: "affordable" | "tight" | "not_affordable";
  notes: string[]; method: string;
}
interface Choice { id: number; name: string; amount: number }
interface Fi {
  currency: string; annual_income: number; annual_spending: number;
  annual_saving: number; savings_rate: number | null; invested: number;
  target: number; years: number | null; year_reached: number | null;
  path: { year: number; value: number }[]; method: string;
}

const VERDICT = {
  affordable: { tone: "lime", icon: I.checkCircle, text: "Affordable: even the unlucky simulations stay above your alert level." },
  tight: { tone: "cyan", icon: I.autoGraph, text: "Tight: the typical path is fine, but unlucky months could dip below your alert level." },
  not_affordable: { tone: "pink", icon: I.warning, text: "Not affordable yet: the typical path drops below your alert level." },
} as const;

const PRESETS: { label: string; change: Change }[] = [
  { label: "Buy a car", change: { kind: "once", amount: -15000, label: "Buy a car" } },
  { label: "A raise", change: { kind: "monthly", amount: 300, label: "A raise" } },
  { label: "Higher rent", change: { kind: "monthly", amount: -200, label: "Higher rent" } },
  { label: "Holiday", change: { kind: "once", amount: -2500, label: "Holiday" } },
];

function bandFigure(w: WhatIf, t: (k: string) => string): PlotFigure {
  const x = w.dates;
  const line = (y: number[], name: string, color: string, dash = "solid") =>
    ({ x, y, name, type: "scatter", mode: "lines", line: { color, width: 2.5, dash } });
  return {
    data: [
      { x, y: w.scenario.p95, type: "scatter", mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x, y: w.scenario.p5, type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty",
        fillcolor: "rgba(204,121,167,0.22)", name: t("Scenario 90% range") },
      line(w.baseline.p50, t("Without the changes"), "#0072b2", "dash"),
      line(w.scenario.p50, t("With the changes"), "#cc79a7"),
      ...(w.threshold ? [{ x: [x[0], x[x.length - 1]], y: [w.threshold, w.threshold], type: "scatter",
        mode: "lines", name: t("Alert level"), line: { color: "#d55e00", width: 1, dash: "dot" } }] : []),
    ],
    layout: { margin: { l: 60, r: 16, t: 8, b: 40 }, legend: { orientation: "h", y: -0.18 },
      hovermode: "x unified", yaxis: { title: { text: w.currency } } },
  } as PlotFigure;
}

export function WhatIfPlanner({ threshold }: { threshold: number }) {
  const t = useT();
  const choices = useLoad(() => get<Choice[]>("/api/forecast/what-if/choices"), []);
  const [changes, setChanges] = useState<Change[]>([]);
  const [horizon, setHorizon] = useState(365);
  const [result, setResult] = useState<WhatIf | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (i: number, c: Change) => setChanges((cs) => cs.map((x, j) => (j === i ? c : x)));
  const add = (c: Change) => setChanges((cs) => [...cs, c]);
  const run = async () => {
    if (!changes.length) { setError(t("Add at least one change, for example a one-off purchase.")); return; }
    setBusy(true); setError(null);
    try {
      setResult(await post<WhatIf>("/api/forecast/what-if", { changes, horizon_days: horizon, threshold }));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  useEffect(() => { setResult(null); }, [changes, horizon]);
  const v = result && VERDICT[result.verdict];

  return (
    <Section title={<span className="title-icon"><span className="icon" aria-hidden>{I.autoGraph}</span>{t("What if…?")}</span>}
      sub={t("Try a purchase, a raise or a price change and see your balance with and without it.")}>
      <div className="chip-row">
        {PRESETS.map((p) => (
          <Button key={p.label} size="small" shape="circular" icon={<span className="icon" aria-hidden>{I.add}</span>}
            onClick={() => add({ ...p.change, label: t(p.label) })}>{t(p.label)}</Button>))}
        <Button size="small" shape="circular" appearance="subtle"
          onClick={() => add({ kind: "monthly", amount: -100 })}>{t("Every month…")}</Button>
        <Button size="small" shape="circular" appearance="subtle"
          onClick={() => add({ kind: "once", amount: -1000, start: today() })}>{t("One-off…")}</Button>
        {!!choices.data?.length && (
          <Button size="small" shape="circular" appearance="subtle"
            onClick={() => add({ kind: "recurring_pct", recurring_id: choices.data![0].id, pct: 10 })}>
            {t("Change a bill…")}</Button>)}
      </div>
      {changes.map((c, i) => (
        <div key={i} className="whatif-row">
          <Input aria-label={t("Name")} value={c.label ?? ""} placeholder={t(
            c.kind === "monthly" ? "Every month" : c.kind === "once" ? "One-off" : "Bill change")}
            onChange={(_, d) => set(i, { ...c, label: d.value })} />
          {c.kind === "recurring_pct" ? (<>
            <Select aria-label={t("Bill or income")} value={String(c.recurring_id)}
              onChange={(_, d) => set(i, { ...c, recurring_id: Number(d.value) })}>
              {choices.data?.map((r) => <option key={r.id} value={r.id}>{r.name} ({money(r.amount)})</option>)}
            </Select>
            <Field label={t("Change %")} orientation="horizontal">
              <SpinButton value={c.pct} step={5} min={-100} max={500} style={{ width: 96 }}
                onChange={(_, d) => set(i, { ...c, pct: Number(d.value ?? d.displayValue ?? 0) })} />
            </Field>
          </>) : (<>
            <Field label={t(c.kind === "monthly" ? "Per month" : "Amount")} orientation="horizontal"
              hint={t("Negative = money out")}>
              <SpinButton value={c.amount} step={c.kind === "monthly" ? 50 : 500} style={{ width: 130 }}
                onChange={(_, d) => set(i, { ...c, amount: Number(d.value ?? d.displayValue ?? 0) })} />
            </Field>
            <Field label={t(c.kind === "monthly" ? "From" : "On")} orientation="horizontal">
              <Input type="date" value={c.start ?? today()}
                onChange={(_, d) => set(i, { ...c, start: d.value })} />
            </Field>
          </>)}
          <Button appearance="subtle" aria-label={t("Remove")} icon={<span className="icon" aria-hidden>{I.close}</span>}
            onClick={() => setChanges((cs) => cs.filter((_, j) => j !== i))} />
        </div>))}
      <div className="row-actions">
        <Select aria-label={t("Horizon")} value={String(horizon)} onChange={(_, d) => setHorizon(Number(d.value))}>
          {[90, 180, 365, 730].map((d) => <option key={d} value={d}>{t("{n} days", { n: d })}</option>)}
        </Select>
        <Button appearance="primary" disabled={busy || !changes.length} onClick={run}>
          {busy ? t("Simulating…") : t("See the effect")}</Button>
      </div>
      {error && <Banner kind="error">{error}</Banner>}
      {result && v && (<>
        {result.notes.map((n) => <Banner key={n} kind="warning">{t(n)}</Banner>)}
        <div className={`verdict tone-${v.tone}`}>
          <span className="icon" aria-hidden>{v.icon}</span><span>{t(v.text)}</span>
        </div>
        <div className="kpis">
          <Kpi label={t("Typical balance at the end")} value={money(result.end.scenario, result.currency)}
            sub={t("{v} without the changes", { v: money(result.end.baseline, result.currency, 0) })} tone="violet" />
          <Kpi label={t("Difference")} value={money(result.end.scenario - result.end.baseline, result.currency)}
            cls={result.end.scenario >= result.end.baseline ? "pos" : "neg"} />
          <Kpi label={t("Lowest point (typical)")} value={money(result.lowest.scenario, result.currency)}
            sub={t("{v} without the changes", { v: money(result.lowest.baseline, result.currency, 0) })}
            cls={result.lowest.scenario < result.threshold ? "neg" : ""} />
        </div>
        <Plot figure={bandFigure(result, t)} height={340} />
        <p className="caption">{t(result.method)}</p>
      </>)}
    </Section>
  );
}

export function IndependenceCalc() {
  const t = useT();
  const [ret, setRet] = useState(5);
  const [wd, setWd] = useState(4);
  const [extra, setExtra] = useState(0);
  const fi = useLoad(() => get<Fi>("/api/planning/independence",
    { return_pct: ret, withdrawal_pct: wd, extra_monthly: extra }), [ret, wd, extra]);
  const f = fi.data;
  const spin = (label: string, value: number, setV: (n: number) => void, step: number, min: number, max: number, width = 140) => (
    <Field label={label}>
      <SpinButton value={value} step={step} min={min} max={max} style={{ width }}
        onChange={(_, d) => setV(Number(d.value ?? d.displayValue ?? value))} />
    </Field>);
  const figure: PlotFigure | null = f ? {
    data: [
      { x: f.path.map((p) => p.year), y: f.path.map((p) => p.value), type: "scatter", mode: "lines+markers",
        name: t("Invested"), line: { color: "#009e73", width: 3, shape: "spline" }, marker: { size: 5 } },
      { x: [f.path[0]?.year, f.path[f.path.length - 1]?.year], y: [f.target, f.target], type: "scatter",
        mode: "lines", name: t("Independence target"), line: { color: "#e69f00", width: 2, dash: "dash" } },
    ],
    layout: { margin: { l: 70, r: 16, t: 8, b: 40 }, legend: { orientation: "h", y: -0.18 },
      yaxis: { title: { text: f.currency } }, hovermode: "x unified" },
  } as PlotFigure : null;

  return (
    <Section title={<span className="title-icon"><span className="icon" aria-hidden>{I.beachAccess}</span>{t("Financial independence")}</span>}
      sub={t("When could your investments pay for your spending? Based on your last 12 months.")}>
      <div className="row-actions wrap">
        {spin(t("Yearly return after inflation %"), ret, setRet, 0.5, -5, 20)}
        {spin(t("Safe withdrawal rate %"), wd, setWd, 0.5, 0.5, 15)}
        {spin(t("Extra saving per month"), extra, setExtra, 100, 0, 1e9, 160)}
      </div>
      {fi.error && <Banner kind="error">{fi.error}</Banner>}
      {fi.loading && !f && <Spinner />}
      {f && (<>
        <div className="kpis">
          <Kpi tone="lime" label={t("Independent in")}
            value={f.years === null ? t("Not on this path") : f.years === 0 ? t("Already there")
              : t("{n} years", { n: f.years })}
            sub={f.year_reached ? t("around {y}", { y: f.year_reached }) : t("Save more or spend less to get there")} />
          <Kpi label={t("Target")} value={money(f.target, f.currency, 0)}
            sub={t("{s} a year ÷ {w}%", { s: money(f.annual_spending, f.currency, 0), w: num(wd, 1) })} />
          <Kpi label={t("Invested today")} value={money(f.invested, f.currency, 0)}
            sub={f.target > 0 ? t("{p} of the target", { p: pct(Math.min(1, f.invested / f.target), 0) }) : undefined} />
          <Kpi label={t("Savings rate")} value={f.savings_rate === null ? "—" : pct(f.savings_rate, 0)}
            sub={t("{v} saved a year", { v: money(f.annual_saving, f.currency, 0) })} />
        </div>
        {f.path.length > 1 && <Plot figure={figure} height={300} />}
        <p className="caption">{t(f.method)}</p>
      </>)}
    </Section>
  );
}
