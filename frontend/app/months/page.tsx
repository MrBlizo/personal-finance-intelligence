"use client";
// Month by month: what came in, what was spent, what was paid and saved.
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button, Tooltip } from "@fluentui/react-components";
import { ChevronLeft20Regular, ChevronRight20Regular } from "@fluentui/react-icons";
import { CategoryIcon } from "@/components/CategoryIcon";
import { Empty, Kpi, PageHead, Section, Spinner, useLoad } from "@/components/ui";
import { get } from "@/lib/api";
import { date, locale, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Totals {
  income: number; spent: number; bills: number; debt_payments: number;
  paid: number; saved: number; net: number;
}
interface MonthRow extends Totals { month: string; transactions: number }
interface MonthDetail {
  month: string; currency: string; days: number; totals: Totals; previous: Totals;
  categories: { category: string; amount: number; share: number; previous: number }[];
  bills: { name: string; date: string; amount: number; account: string }[];
  debt_payments: { account: string; amount: number }[];
  biggest: { id: number; date: string; description: string; category: string; amount: number }[];
  daily: { this: number[]; previous: number[] };
}

const label = (m: string, style: "long" | "short" = "long") =>
  new Intl.DateTimeFormat(locale(), { month: style, year: style === "long" ? "numeric" : "2-digit" })
    .format(new Date(`${m}-15T12:00:00`));

function shift(m: string, by: number) {
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(y, mo - 1 + by, 15);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Cumulative spending this month (solid) against last month (dashed). */
function Pace({ now, before, days, currency }: {
  now: number[]; before: number[]; days: number; currency: string;
}) {
  const t = useT();
  const W = 520, H = 180, P = 8;
  const top = Math.max(1, ...now, ...before);
  const x = (i: number, n: number) => P + (i / Math.max(1, n - 1)) * (W - 2 * P);
  const path = (v: number[], n: number) => v.map((y, i) =>
    `${i ? "L" : "M"}${x(i, n).toFixed(1)} ${(H - P - (y / top) * (H - 2 * P)).toFixed(1)}`).join(" ");
  const end = x(Math.max(0, now.length - 1), days);
  return (
    <figure className="pace" aria-label={t("Spending pace: {a} this month, {b} last month",
      { a: money(now[now.length - 1] ?? 0, currency, 0), b: money(before[before.length - 1] ?? 0, currency, 0) })}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        <path d={path(before, before.length)} className="pace-prev" />
        {now.length > 0 && <path d={`${path(now, days)} L${end} ${H - P} L${P} ${H - P} Z`} className="pace-fill" />}
        <path d={path(now, days)} className="pace-now" />
      </svg>
      <figcaption className="caption">
        <span className="legend now" /> {t("This month")}
        <span className="legend prev" /> {t("Last month")}
      </figcaption>
    </figure>
  );
}

export default function Months() {
  const t = useT();
  const timeline = useLoad(() => get<{ currency: string; months: MonthRow[] }>("/api/analytics/months?count=24"));
  const rows = useMemo(() => timeline.data?.months ?? [], [timeline.data]);
  const [month, setMonth] = useState<string | null>(null);
  useEffect(() => {
    if (!month && rows.length) setMonth(rows[rows.length - 1].month);
  }, [rows, month]);
  const detail = useLoad(async () => month ? get<MonthDetail>(`/api/analytics/months/${month}`) : null, [month]);
  const d = detail.data;
  const cur = timeline.data?.currency ?? "";
  const top = Math.max(1, ...rows.map((r) => Math.max(r.income, r.spent)));
  const first = rows[0]?.month, last = rows[rows.length - 1]?.month;

  const change = (a: number, b: number) => (b > 0 ? (a - b) / b : null);
  const spentChange = d ? change(d.totals.spent, d.previous.spent) : null;

  return (
    <>
      <PageHead title={t("Month by month")} sub={month ? label(month) : undefined}>
        <Tooltip content={t("Previous month")} relationship="label">
          <Button appearance="subtle" icon={<ChevronLeft20Regular />} disabled={!month || month === first}
            onClick={() => month && setMonth(shift(month, -1))} /></Tooltip>
        <Tooltip content={t("Next month")} relationship="label">
          <Button appearance="subtle" icon={<ChevronRight20Regular />} disabled={!month || month === last}
            onClick={() => month && setMonth(shift(month, 1))} /></Tooltip>
      </PageHead>
      {timeline.loading && <Spinner label={t("Loading…")} />}
      {!timeline.loading && rows.length === 0 && (
        <Empty action={<Link href="/import/"><Button appearance="primary">{t("Import a statement")}</Button></Link>}>
          {t("No transactions yet. Each month will appear here with what you spent and paid.")}
        </Empty>)}
      {rows.length > 0 && (
        <div className="month-strip" role="tablist" aria-label={t("Months")}>
          {rows.map((r) => (
            <button key={r.month} type="button" role="tab" aria-selected={r.month === month}
              className="month-pill" onClick={() => setMonth(r.month)}
              title={`${label(r.month)}: ${t("spent")} ${money(r.spent, cur, 0)}`}>
              <span className="month-bars" aria-hidden>
                <span className="bar in" style={{ height: `${(r.income / top) * 100}%` }} />
                <span className="bar out" style={{ height: `${(r.spent / top) * 100}%` }} />
              </span>
              <span className="month-name">{label(r.month, "short")}</span>
            </button>))}
        </div>)}
      {month && detail.loading && !d && <Spinner label={t("Loading…")} />}
      {d && (
        <>
          <div className="month-top">
            <div className="month-hero">
              <div className="home-hero-label">{t("Spent in {m}", { m: label(d.month) })}</div>
              <div className="month-hero-value">{money(d.totals.spent, cur)}</div>
              <div className="home-hero-sub">
                {spentChange === null ? t("No spending the month before to compare with.")
                  : spentChange <= 0
                    ? t("{p} less than {m}", { p: pct(-spentChange, 0), m: label(shift(d.month, -1)) })
                    : t("{p} more than {m}", { p: pct(spentChange, 0), m: label(shift(d.month, -1)) })}
              </div>
            </div>
            <div className="month-grid">
              <Kpi tone="lime" label={t("Earned")} value={money(d.totals.income, cur)}
                sub={t("Left over {v}", { v: money(d.totals.net, cur, 0) })} />
              <Kpi tone="violet" label={t("Paid")} value={money(d.totals.paid, cur)}
                sub={t("Bills {a} · Cards & loans {b}", { a: money(d.totals.bills, cur, 0), b: money(d.totals.debt_payments, cur, 0) })} />
              <Kpi tone="cyan" label={t("Saved")} value={money(d.totals.saved, cur)}
                sub={t("Moved to savings and investments")} />
              <Kpi label={t("Savings rate")} value={d.totals.income > 0 ? pct(d.totals.net / d.totals.income) : "—"}
                sub={t("(income − expenses) / income")} />
            </div>
          </div>
          <div className="month-cols">
            <Section title={t("Where it went")} sub={t("Spending by category, compared with the month before")}>
              {d.categories.length === 0 ? <Empty>{t("Nothing spent this month.")}</Empty> : (
                <ul className="cat-bars">
                  {d.categories.map((c) => {
                    const diff = c.amount - c.previous;
                    return (
                      <li key={c.category}>
                        <CategoryIcon name={c.category} size={36} />
                        <div className="cat-bar-main">
                          <div className="cat-bar-head">
                            <span>{t(c.category)}</span>
                            <span className="num">{money(c.amount, cur)}</span>
                          </div>
                          <div className="cat-bar-track" aria-hidden>
                            <span style={{ width: `${Math.max(2, c.share * 100)}%` }} />
                          </div>
                          <div className="caption">
                            {pct(c.share, 0)} · {c.previous === 0 ? t("new this month")
                              : diff >= 0 ? t("{v} more than last month", { v: money(diff, cur, 0) })
                                : t("{v} less than last month", { v: money(-diff, cur, 0) })}
                          </div>
                        </div>
                      </li>);
                  })}
                </ul>)}
            </Section>
            <div className="month-side">
              <Section title={t("Paid this month")} sub={t("Bills, and payments to cards and loans")}>
                {d.bills.length + d.debt_payments.length === 0 ? <Empty>{t("No bills or debt payments this month.")}</Empty> : (
                  <ul className="list">
                    {d.bills.map((b, i) => (
                      <li key={`b${i}`} className="list-row">
                        <div><div>{b.name}</div><div className="caption">{date(b.date)} · {b.account}</div></div>
                        <span className="num">{money(b.amount, cur)}</span>
                      </li>))}
                    {d.debt_payments.map((p) => (
                      <li key={`d${p.account}`} className="list-row">
                        <div><div>{p.account}</div><div className="caption">{t("Card or loan payment")}</div></div>
                        <span className="num">{money(p.amount, cur)}</span>
                      </li>))}
                  </ul>)}
              </Section>
              <Section title={t("Spending pace")} sub={t("Running total, day by day")}>
                <Pace now={d.daily.this} before={d.daily.previous} days={d.days} currency={cur} />
              </Section>
              <Section title={t("Biggest expenses")}>
                {d.biggest.length === 0 ? <Empty>{t("Nothing spent this month.")}</Empty> : (
                  <ul className="list">
                    {d.biggest.map((b) => (
                      <li key={b.id} className="list-row">
                        <div><div>{b.description}</div><div className="caption">{date(b.date)} · {t(b.category)}</div></div>
                        <span className="num">{money(b.amount, cur)}</span>
                      </li>))}
                  </ul>)}
              </Section>
            </div>
          </div>
        </>)}
    </>
  );
}
