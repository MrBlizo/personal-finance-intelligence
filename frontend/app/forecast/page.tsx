"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Field, Link as FLink, SpinButton, Tab, TabList } from "@fluentui/react-components";
import Plot from "@/components/Plot";
import { Banner, Empty, Kpi, PageHead, Section, Spinner, useLoad } from "@/components/ui";
import { Forecast, get } from "@/lib/api";
import { date, money, pct, signClass } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function ForecastPage() {
  const t = useT();
  const [horizon, setHorizon] = useState(90);
  const [threshold, setThreshold] = useState(0);
  const fc = useLoad(() => get<Forecast>("/api/forecast", { horizon_days: horizon, threshold }),
    [horizon, threshold]);
  const f = fc.data;
  const cur = f?.base_currency ?? "CHF";

  return (
    <>
      <PageHead title={t("Cash-flow forecast")}
        sub={t("Model prediction for checking, savings, cash and card accounts")}>
        <TabList size="small" selectedValue={horizon}
          onTabSelect={(_, d) => setHorizon(Number(d.value))}>
          {[30, 90, 180, 365].map((d) => <Tab key={d} value={d}>{t("{n} days", { n: d })}</Tab>)}
        </TabList>
        <Field label={t("Alert below ({cur})", { cur })} orientation="horizontal">
          <SpinButton value={threshold} step={100} style={{ width: 120 }}
            onChange={(_, d) => setThreshold(Number(d.value ?? d.displayValue ?? 0))} />
        </Field>
      </PageHead>
      {fc.error && <Banner kind="error">{fc.error}</Banner>}
      {f?.notes.map((n) => <Banner key={n} kind="warning">{t(n)}</Banner>)}
      {fc.loading && !f && <Spinner label={t("Simulating…")} />}
      {f && (
        <>
          <div className="kpis">
            <Kpi label={t("Balance today")} value={money(f.start_balance, cur)} />
            <Kpi label={t("Median in {n} days", { n: horizon })} value={money(f.p50[f.p50.length - 1], cur)}
              sub={t("90% range {a} – {b}", { a: money(f.p5[f.p5.length - 1], undefined, 0),
                b: money(f.p95[f.p95.length - 1], undefined, 0) })} />
            <Kpi label={t("Chance of dropping below {v}", { v: money(threshold, undefined, 0) })}
              value={pct(f.prob_below_threshold, 0)}
              cls={f.prob_below_threshold > 0.2 ? "neg" : f.prob_below_threshold > 0.05 ? "" : "pos"} />
            <Kpi label={t("Scheduled net (recurring)")} value={money(f.scheduled_total, cur)}
              cls={signClass(f.scheduled_total)}
              sub={t("Everyday spending Ø {v} / day", { v: money(f.discretionary_daily_mean) })} />
          </div>
          <Section>
            <Plot figure={f.figure} height={400} />
            <p className="caption">
              {t("{n} simulations, learned from the last {d} days. Bands show the range of simulated outcomes, not a guarantee; past behaviour may not repeat.",
                { n: f.simulations, d: f.lookback_days_used })}</p>
          </Section>
          <Section title={t("Upcoming scheduled items")}
            actions={<Link href="/recurring/"><FLink as="span">{t("Manage bills & recurring")}</FLink></Link>}>
            {f.upcoming.length === 0 ? (
              <Empty action={<Link href="/recurring/"><Button>{t("Add recurring items")}</Button></Link>}>
                {t("Nothing scheduled in this horizon. Add salary, rent and insurance to improve the forecast.")}</Empty>) : (
              <div className="table-wrap" style={{ maxHeight: 360 }}>
                <table><thead><tr><th>{t("Date")}</th><th>{t("Name")}</th>
                  <th className="num">{t("Amount")}</th></tr></thead>
                  <tbody>{f.upcoming.map((u, i) => (
                    <tr key={i}><td>{date(u.date)}</td><td>{u.name}</td>
                      <td className={`num ${signClass(u.amount_base)}`}>{money(u.amount_base, cur)}</td></tr>))}
                  </tbody></table>
              </div>)}
          </Section>
        </>)}
    </>
  );
}
