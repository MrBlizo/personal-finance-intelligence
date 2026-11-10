"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Link as FLink, Tab, TabList } from "@fluentui/react-components";
import { RestoreFromFile } from "@/components/BackupPanel";
import Plot from "@/components/Plot";
import { Banner, Empty, Kpi, PageHead, Section, Spinner, useLoad } from "@/components/ui";
import { Insight, PlotFigure, Reminder, Summary, get, insightText, post } from "@/lib/api";
import { date, money, pct, signClass } from "@/lib/format";
import { useT } from "@/lib/i18n";

const PERIODS: Record<string, string> = {
  this_month: "This month", last_3_months: "3 months",
  last_12_months: "12 months", year_to_date: "Year to date",
};
const SEV_GLYPH: Record<string, string> = {
  warning: "", positive: "", info: "",
};

type Dash = { summary: Summary; charts: Record<string, PlotFigure> };

export default function Home() {
  const t = useT();
  const [period, setPeriod] = useState("last_12_months");
  const periods = useLoad(() =>
    get<Record<string, [string, string]>>("/api/analytics/periods"));
  const range = periods.data?.[period];
  const dash = useLoad(async () => range ? get<Dash>("/api/analytics/dashboard", {
    start: range[0], end: range[1],
    charts: ["monthly_cashflow", "category_breakdown", "net_worth",
      "budget_vs_actual"],
  }) : null, [range?.[0], range?.[1]]);
  const insights = useLoad(() => get<{ insights: Insight[] }>("/api/insights"));
  const reminders = useLoad(() => get<Reminder[]>("/api/reminders", { days: 14 }));
  const [seeding, setSeeding] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const s = dash.data?.summary;
  const cur = s?.currency ?? "CHF";
  const empty = s && s.transactions === 0 && s.net_worth === 0;

  return (
    <>
      <PageHead title={t("Home")} sub={t("Your finances at a glance")}>
        <TabList size="small" selectedValue={period}
          onTabSelect={(_, d) => setPeriod(String(d.value))}>
          {Object.entries(PERIODS).map(([k, label]) => (
            <Tab key={k} value={k}>{t(label)}</Tab>))}
        </TabList>
      </PageHead>
      {dash.error && <Banner kind="error">{dash.error}</Banner>}
      {s && s.missing_fx.length > 0 && (
        <Banner kind="warning" title={t("Missing exchange rates")}
          action={<Link href="/settings/"><Button size="small">{t("Open settings")}</Button></Link>}>
          {t("No rate to {cur} for {list}; those amounts are left out.",
            { cur, list: s.missing_fx.join(", ") })}
        </Banner>)}
      {s && s.unpriced_holdings.length > 0 && (
        <Banner kind="info"
          action={<Link href="/investments/"><Button size="small">{t("Update prices")}</Button></Link>}>
          {t("No price yet for {list}; they count as zero.",
            { list: s.unpriced_holdings.join(", ") })}
        </Banner>)}
      {empty && (
        <Banner kind="info" title={t("Welcome")}
          action={<Button appearance="primary" size="small" disabled={seeding}
            onClick={async () => {
              setSeeding(true);
              try { await post("/api/demo"); await dash.reload(); insights.reload(); }
              finally { setSeeding(false); }
            }}>{seeding ? t("Generating…") : t("Load demo data")}</Button>}>
          {t("Add an account and import a bank CSV, or explore with synthetic demo data (removable in Settings).")}
        </Banner>)}
      {empty && (
        <Banner kind="info" title={t("Moving from another PC?")}
          action={<RestoreFromFile appearance="primary" label={t("Restore from a backup")}
            onDone={() => { window.location.reload(); }} onError={(m) => setRestoreError(m)} />}>
          {t("Choose the move file (.pfibak) you created on the old PC under Settings → Backups.")}
        </Banner>)}
      {restoreError && <Banner kind="error" onClose={() => setRestoreError(null)}>{restoreError}</Banner>}
      {!s && dash.loading && <Spinner label={t("Loading…")} />}
      {s && (
        <>
          <div className="kpis">
            <Kpi label={t("Net worth")} value={money(s.net_worth, cur)}
              sub={`${t("Liquid")} ${money(s.liquid, undefined, 0)} · ${t("Invested")} ${money(s.investments, undefined, 0)}`} />
            <Kpi label={t("Income")} value={money(s.income, cur)}
              sub={t("Ø {v} / month", { v: money(s.avg_monthly_income, undefined, 0) })} />
            <Kpi label={t("Expenses")} value={money(s.expenses, cur)}
              sub={t("Ø {v} / month", { v: money(s.avg_monthly_expenses, undefined, 0) })} />
            <Kpi label={t("Net saved")} value={money(s.net, cur)} cls={signClass(s.net)}
              sub={t("{n} transactions", { n: s.transactions })} />
            <Kpi label={t("Savings rate")} value={pct(s.savings_rate)}
              cls={signClass(s.savings_rate)} sub={t("(income − expenses) / income")} />
          </div>
          <div className="grid g2">
            <Section title={t("Income vs. expenses")}>
              <Plot figure={dash.data?.charts.monthly_cashflow} /></Section>
            <Section title={t("Where the money goes")}>
              <Plot figure={dash.data?.charts.category_breakdown} /></Section>
            <Section title={t("Net worth")}>
              <Plot figure={dash.data?.charts.net_worth} /></Section>
            <Section title={t("Budgets this month")}>
              <Plot figure={dash.data?.charts.budget_vs_actual} /></Section>
          </div>
          <div className="grid g2">
            <Section title={t("Coming up")} sub={t("Bills and income in the next 14 days")}
              actions={<Link href="/recurring/"><FLink as="span">{t("Bills & recurring")}</FLink></Link>}>
              {reminders.data?.length === 0 && <Empty>{t("Nothing due in the next 14 days.")}</Empty>}
              {reminders.data?.slice(0, 6).map((r) => (
                <div className="list-row" key={r.key}>
                  <span className="glyph" aria-hidden>{r.auto_post ? "" : ""}</span>
                  <div className="grow">
                    <span className="cell-main">{r.name}</span>
                    <span className="cell-sub">
                      {date(r.date)} · {r.days_left === 0 ? t("today")
                        : t("in {n} days", { n: r.days_left })}
                      {r.auto_post ? ` · ${t("posted automatically")}` : ""}
                    </span>
                  </div>
                  <span className={`num ${signClass(r.amount)}`}>{money(r.amount, r.currency)}</span>
                </div>))}
            </Section>
            <Section title={t("Insights")}
              actions={<Link href="/insights/"><FLink as="span">{t("All insights")}</FLink></Link>}>
              {insights.data?.insights.length === 0 && <Empty>{t("No notable patterns yet.")}</Empty>}
              {insights.data?.insights.slice(0, 4).map((i, n) => {
                const x = insightText(i, t);
                return (
                  <div className="insight" key={n}>
                    <span className="glyph" aria-hidden>{SEV_GLYPH[i.severity]}</span>
                    <div><div>{x.title}</div><div className="caption">{x.detail}</div></div>
                  </div>);
              })}
            </Section>
          </div>
        </>)}
    </>
  );
}
