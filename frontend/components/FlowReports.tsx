"use client";
// 0.6 reports: where money comes from and goes, balances over time, the age
// of money and spending per payee, for a chosen period.
import Link from "next/link";
import { useState } from "react";
import { Button } from "@fluentui/react-components";
import Plot from "./Plot";
import { Banner, Empty, Section, Spinner, useLoad } from "./ui";
import { PayeeTotal, PlotFigure, get } from "@/lib/api";
import { date, iso, money } from "@/lib/format";
import { useT } from "@/lib/i18n";

const PRESETS = [3, 6, 12] as const;

function useRange() {
  const [months, setMonths] = useState<number>(6);
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
  return { months, setMonths, start: iso(start), end: iso(end) };
}

function RangePicker({ months, setMonths }: { months: number; setMonths: (n: number) => void }) {
  const t = useT();
  return (
    <div className="row">
      {PRESETS.map((n) => (
        <Button key={n} size="small" appearance={months === n ? "primary" : "secondary"}
          onClick={() => setMonths(n)}>{t("{n} months", { n })}</Button>))}
    </div>);
}

export function FlowReport() {
  const t = useT();
  const r = useRange();
  const fig = useLoad(() => get<PlotFigure>("/api/analytics/charts/money_flow",
    { start: r.start, end: r.end }), [r.start]);
  return (
    <Section title={t("Money flow")}
      sub={t("Income on the left, spending and savings on the right, {a} to {b}.",
        { a: date(r.start), b: date(r.end) })}
      actions={<RangePicker months={r.months} setMonths={r.setMonths} />}>
      {fig.error && <Banner kind="error">{fig.error}</Banner>}
      {fig.loading && !fig.data && <Spinner />}
      {fig.data && <Plot figure={fig.data} height={460} />}
    </Section>);
}

export function BalanceReport() {
  const t = useT();
  const r = useRange();
  const bal = useLoad(() => get<PlotFigure>("/api/analytics/charts/balance_history",
    { start: r.start, end: r.end }), [r.start]);
  const age = useLoad(() => get<{ age: number | null; points: { date: string; age: number | null }[] }>(
    "/api/analytics/age-of-money", { months: Math.max(r.months, 2) }), [r.months]);
  const ageFig = useLoad(() => get<PlotFigure>("/api/analytics/charts/age_of_money",
    { start: r.start, end: r.end }), [r.start]);
  return (<>
    <Section title={t("Balances over time")} sub={t("Month-end balance of each everyday account, in the base currency.")}
      actions={<RangePicker months={r.months} setMonths={r.setMonths} />}>
      {bal.error && <Banner kind="error">{bal.error}</Banner>}
      {bal.data ? <Plot figure={bal.data} height={320} /> : <Spinner />}
    </Section>
    <Section title={t("Age of money")}
      sub={t("How many days your money waits between arriving and being spent (average of the last 10 payments). Higher means more breathing room.")}>
      {age.data && (
        <div className="hero" style={{ marginBottom: 12 }}>
          <div>
            <div className="hero-label">{t("Today")}</div>
            <div className="hero-value">{age.data.age === null ? "—" : t("{n} days", { n: age.data.age })}</div>
            <div className="caption">{age.data.age === null
              ? t("Needs at least 10 payments from everyday accounts.")
              : age.data.age >= 30 ? t("You are spending money that arrived more than a month ago.")
                : t("Aim for 30 days or more: then this month is paid with last month's income.")}</div>
          </div>
        </div>)}
      {ageFig.data && <Plot figure={ageFig.data} height={260} />}
    </Section>
  </>);
}

export function PayeeReport() {
  const t = useT();
  const r = useRange();
  const data = useLoad(() => get<{ currency: string; payees: PayeeTotal[] }>(
    "/api/analytics/payees", { start: r.start, end: r.end }), [r.start]);
  const [all, setAll] = useState(false);
  const rows = data.data ? (all ? data.data.payees : data.data.payees.slice(0, 25)) : [];
  return (
    <Section title={t("Spending by payee")}
      sub={t("{a} to {b}, in {c}.", { a: date(r.start), b: date(r.end), c: data.data?.currency ?? "" })}
      actions={<RangePicker months={r.months} setMonths={r.setMonths} />}>
      {data.error && <Banner kind="error">{data.error}</Banner>}
      {data.loading && !data.data && <Spinner />}
      {data.data && data.data.payees.length === 0 && <Empty>{t("No spending in this period.")}</Empty>}
      {rows.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Payee")}</th><th className="num">{t("Payments")}</th>
            <th className="num">{t("Average")}</th><th className="num">{t("Total")}</th>
            <th>{t("Last")}</th></tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.payee}>
              <td><Link href={`/transactions/?q=${encodeURIComponent(`payee:"${p.payee}"`)}`}>{p.payee}</Link></td>
              <td className="num">{p.count}</td>
              <td className="num muted">{money(p.average)}</td>
              <td className="num">{money(p.total)}</td>
              <td>{date(p.last_date)}</td></tr>))}</tbody>
        </table></div>)}
      {data.data && data.data.payees.length > 25 && !all && (
        <Button appearance="subtle" onClick={() => setAll(true)}>
          {t("Show all {n} payees", { n: data.data.payees.length })}</Button>)}
    </Section>);
}
