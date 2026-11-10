"use client";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import { Button, Select } from "@fluentui/react-components";
import Plot from "@/components/Plot";
import { catLabel } from "@/components/refs";
import { Banner, Empty, Kpi, PageHead, Progress, Section, Spinner, useLoad } from "@/components/ui";
import { CalendarData, PlotFigure, get } from "@/lib/api";
import { date, money, pct } from "@/lib/format";
import { useI18n, useT } from "@/lib/i18n";

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** One cell per day, weeks as columns (Monday first), like a year heatmap. */
function Heatmap({ data, lang }: { data: CalendarData; lang: string }) {
  const t = useT();
  const byDay = useMemo(() => new Map(data.days.map((d) => [d.date, d])), [data]);
  const spends = data.days.map((d) => d.spend).filter((v) => v > 0).sort((a, b) => a - b);
  // Quartiles instead of the maximum, so one large purchase does not wash
  // out every other day.
  const q = [0.25, 0.5, 0.75].map((p) => spends[Math.floor(p * (spends.length - 1))] ?? 0);
  const level = (v: number) => (v <= 0 ? 0 : v <= q[0] ? 1 : v <= q[1] ? 2 : v <= q[2] ? 3 : 4);
  const first = new Date(data.year, 0, 1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7));
  const weeks: Date[][] = [];
  for (let d = new Date(start); d.getFullYear() <= data.year; ) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) { week.push(new Date(d)); d.setDate(d.getDate() + 1); }
    weeks.push(week);
    if (d.getFullYear() > data.year) break;
  }
  const todayIso = iso(new Date());
  const fmtMonth = (m: number) => new Date(data.year, m, 1).toLocaleDateString(lang, { month: "short" });
  const fmtDay = (i: number) => new Date(2024, 0, 1 + i).toLocaleDateString(lang, { weekday: "short" });
  return (
    <div className="heat-wrap">
      <div className="heat" style={{ gridTemplateColumns: `auto repeat(${weeks.length}, 1fr)` }}>
        <span />
        {weeks.map((w, i) => {
          const m = w.find((d) => d.getDate() === 1 && d.getFullYear() === data.year);
          return <span key={i} className="heat-month">{m ? fmtMonth(m.getMonth()) : ""}</span>;
        })}
        {[0, 1, 2, 3, 4, 5, 6].map((row) => (
          <Fragment key={row}>
            <span className="heat-day">{row % 2 === 0 ? fmtDay(row) : ""}</span>
            {weeks.map((w, i) => {
              const d = w[row];
              const key = iso(d);
              if (d.getFullYear() !== data.year) return <span key={`${row}-${i}`} />;
              const info = byDay.get(key);
              const future = key > todayIso;
              const title = `${date(key)}: ${info?.spend ? money(info.spend, data.currency) : t("no spending")}`
                + (info?.income ? ` · ${t("income {v}", { v: money(info.income, data.currency) })}` : "");
              return future ? <span key={`${row}-${i}`} className="heat-cell heat-future" /> : (
                <Link key={`${row}-${i}`} href={`/transactions/?start=${key}&end=${key}`}
                  className={`heat-cell heat-${level(info?.spend ?? 0)}`} title={title} aria-label={title} />);
            })}
          </Fragment>))}
      </div>
      <div className="heat-legend caption">
        {t("Less")}{[0, 1, 2, 3, 4].map((l) => <span key={l} className={`heat-cell heat-${l}`} />)}{t("More")}
      </div>
    </div>
  );
}

export default function CalendarPage() {
  const t = useT();
  const { lang } = useI18n();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const cal = useLoad(() => get<CalendarData>("/api/analytics/calendar", { year }), [year]);
  const d = cal.data;
  const r = d?.review;
  const years = d ? Array.from({ length: thisYear - Math.min(d.first_year, year) + 1 },
    (_, i) => thisYear - i) : [year];
  const monthName = (m: number | null) => m === null ? "—"
    : new Date(year, m - 1, 1).toLocaleDateString(lang, { month: "long" });
  const weekday = (w: number | null) => w === null ? "—"
    : new Date(2024, 0, 1 + w).toLocaleDateString(lang, { weekday: "long" });
  const figure = useMemo<PlotFigure | null>(() => r ? {
    data: [
      { type: "bar", name: t("Spending"), marker: { color: "#D55E00" },
        x: r.months.map((m) => monthName(m.month)), y: r.months.map((m) => m.spend) },
      { type: "bar", name: t("Income"), marker: { color: "#009E73" },
        x: r.months.map((m) => monthName(m.month)), y: r.months.map((m) => m.income) },
    ],
    layout: { barmode: "group", margin: { l: 56, r: 16, t: 8, b: 40 },
      legend: { orientation: "h", y: -0.2 }, yaxis: { title: { text: d!.currency } } },
  } : null, [r, d, t, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const change = (v: number | null, inverse = false) => v === null ? undefined
    : <span className={(v > 0) !== inverse ? "neg" : "pos"}>
      {t("{v} vs {y}", { v: `${v > 0 ? "+" : ""}${pct(v, 0)}`, y: year - 1 })}</span>;
  const empty = r && r.spend === 0 && r.income === 0;

  return (
    <>
      <PageHead title={t("Spending calendar")} sub={t("Every day of the year at a glance, and your year in review")}>
        <Select value={String(year)} onChange={(_, v) => setYear(Number(v.value))} aria-label={t("Year")}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </Select>
      </PageHead>
      {cal.error && <Banner kind="error">{cal.error}</Banner>}
      {d && d.missing_fx.length > 0 && (
        <Banner kind="warning">{t("{list} cannot be converted to {cur}. Add an exchange rate.",
          { list: d.missing_fx.join(", "), cur: d.currency })}</Banner>)}
      {cal.loading && !d && <Spinner />}
      {d && r && (
        <>
          <Section title={t("Daily spending {y}", { y: year })}
            sub={t("Darker days cost more. Click a day to see its transactions.")}>
            <Heatmap data={d} lang={lang} />
          </Section>
          {empty ? <div className="card"><Empty>{t("No income or spending in {y}.", { y: year })}</Empty></div> : (
            <>
              <div className="group-title">{t("Year in review")}</div>
              <div className="kpis">
                <Kpi label={t("Spending")} value={money(r.spend, d.currency, 0)}
                  sub={change(r.previous.spend_change)} />
                <Kpi label={t("Income")} value={money(r.income, d.currency, 0)}
                  sub={change(r.previous.income_change, true)} />
                <Kpi label={t("Saved")} value={money(r.net, d.currency, 0)} cls={r.net >= 0 ? "pos" : "neg"}
                  sub={r.savings_rate === null ? undefined : t("{v} of income", { v: pct(r.savings_rate, 0) })} />
                <Kpi label={t("Per day")} value={money(r.daily_average, d.currency)}
                  sub={t("over {n} days", { n: r.days })} />
                <Kpi label={t("No-spend days")} value={String(r.no_spend_days)}
                  sub={r.days ? t("{v} of the days", { v: pct(r.no_spend_days / r.days, 0) }) : undefined} />
              </div>
              <div className="grid g2">
                <Section title={t("Where the money went")}>
                  {r.top_categories.map((c) => (
                    <div key={c.category} className="bar-row">
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <span>{catLabel(c.category, t) || t(c.category)}</span>
                        <span className="caption">{money(c.spend, d.currency, 0)} · {pct(c.share, 0)}</span>
                      </div>
                      <Progress value={c.share} />
                    </div>))}
                </Section>
                <Section title={t("Highlights")}>
                  <table className="facts"><tbody>
                    <tr><td>{t("Biggest expense")}</td><td>{r.biggest
                      ? <>{money(r.biggest.spend, d.currency)} <span className="caption">
                        {r.biggest.description} · {date(r.biggest.date)}</span></> : "—"}</td></tr>
                    <tr><td>{t("Most expensive month")}</td><td>{monthName(r.highest_month)}</td></tr>
                    <tr><td>{t("Cheapest month")}</td><td>{monthName(r.lowest_month)}</td></tr>
                    <tr><td>{t("Day you spend most")}</td><td>{weekday(r.busiest_weekday)}</td></tr>
                    <tr><td>{t("Days with spending")}</td><td>{r.spend_days}</td></tr>
                  </tbody></table>
                  <div style={{ marginTop: 12 }}>
                    <Link href="/reports/"><Button size="small">{t("Open reports")}</Button></Link>
                  </div>
                </Section>
              </div>
              <Section title={t("Month by month")}>
                {figure && <Plot figure={figure} height={280} />}
              </Section>
            </>)}
        </>)}
    </>
  );
}
