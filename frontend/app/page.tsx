"use client";
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { Button, Link as FLink, Switch, Tab, TabList, Tooltip } from "@fluentui/react-components";
import {
  ArrowDown20Regular, ArrowUp20Regular, Settings20Regular,
} from "@fluentui/react-icons";
import Plot from "@/components/Plot";
import { Banner, Empty, Kpi, Modal, PageHead, Progress, Section, Spinner, useLoad } from "@/components/ui";
import {
  Account, EnvelopeMonth, Goal, HomeCard, HomeCardId, Insight, PlotFigure, Reminder,
  Settings, Summary, get, insightText, put,
} from "@/lib/api";
import { date, locale, money, pct, signClass } from "@/lib/format";
import { useI18n, useT } from "@/lib/i18n";
import { I } from "@/components/icons";

const PERIODS: Record<string, string> = {
  this_month: "This month", last_3_months: "3 months",
  last_12_months: "12 months", year_to_date: "Year to date",
};
const SEV_GLYPH: Record<string, string> = {
  warning: I.warning, positive: I.checkCircle, info: I.info,
};

/** "Good morning" etc. for the hour of the day. */
function greeting(h: number): string {
  if (h < 5) return "Good evening";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

type Dash = { summary: Summary; charts: Record<string, PlotFigure> };
const CARD_LABELS: Record<HomeCardId, string> = {
  review: "To review", cash_flow: "Income vs. expenses", spending: "Where the money goes",
  budgets: "Budgets this month", net_worth: "Net worth", upcoming: "Coming up",
  insights: "Insights", accounts: "Accounts", goals: "Goals",
};

function Customize({ layout, onClose, onSave }: {
  layout: HomeCard[]; onClose: () => void; onSave: (l: HomeCard[]) => void;
}) {
  const t = useT();
  const [cards, setCards] = useState(layout);
  const move = (i: number, d: number) => {
    const next = [...cards];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    setCards(next);
  };
  return (
    <Modal title={t("Customise home")} onClose={onClose} actions={<>
      <Button appearance="primary" onClick={() => { onSave(cards); onClose(); }}>{t("Save")}</Button>
      <Button onClick={() => setCards(cards.map((c) => ({ ...c, hidden: false })))}>{t("Show all")}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      <div className="caption">{t("Choose which cards the home page shows, and in which order.")}</div>
      <div>{cards.map((c, i) => (
        <div key={c.id} className="layout-row">
          <Switch checked={!c.hidden} aria-label={t(CARD_LABELS[c.id])}
            onChange={(_, d) => setCards(cards.map((x) => x.id === c.id ? { ...x, hidden: !d.checked } : x))} />
          <span className="grow">{t(CARD_LABELS[c.id])}</span>
          <Button appearance="subtle" size="small" icon={<ArrowUp20Regular />} disabled={i === 0}
            aria-label={t("Move up")} onClick={() => move(i, -1)} />
          <Button appearance="subtle" size="small" icon={<ArrowDown20Regular />}
            disabled={i === cards.length - 1} aria-label={t("Move down")} onClick={() => move(i, 1)} />
        </div>))}</div>
    </Modal>);
}

export default function Home() {
  const t = useT();
  const { lang } = useI18n();
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
  const settings = useLoad(() => get<Settings>("/api/settings"));
  const [layout, setLayout] = useState<HomeCard[] | null>(null);
  useEffect(() => { if (settings.data) setLayout(settings.data.home_layout); }, [settings.data]);
  const [customize, setCustomize] = useState(false);
  const envelope = settings.data?.budget_mode === "envelope";
  const shown = new Set((layout ?? []).filter((c) => !c.hidden).map((c) => c.id));
  const waiting = useLoad(() => shown.has("review")
    ? get<{ count: number }>("/api/review/count") : Promise.resolve(null), [shown.has("review")]);
  const env = useLoad(() => envelope && shown.has("budgets")
    ? get<EnvelopeMonth>("/api/envelopes") : Promise.resolve(null), [envelope, shown.has("budgets")]);
  const accounts = useLoad(() => shown.has("accounts")
    ? get<Account[]>("/api/accounts") : Promise.resolve(null), [shown.has("accounts")]);
  const goals = useLoad(() => shown.has("goals")
    ? get<Goal[]>("/api/goals") : Promise.resolve(null), [shown.has("goals")]);
  const s = dash.data?.summary;
  const cur = s?.currency ?? "USD";
  const empty = s && s.transactions === 0 && s.net_worth === 0;

  const renderCard = (id: HomeCardId): ReactNode => {
    switch (id) {
      case "review":
        return waiting.data?.count ? (
          <Section title={t("To review")}
            actions={<Link href="/transactions/?review=1"><Button appearance="primary" size="small">
              {t("Review now")}</Button></Link>}>
            <div className="hero" style={{ marginBottom: 0 }}>
              <div><div className="hero-value">{waiting.data.count}</div>
                <div className="caption">{t("imported or automatic transactions wait for your check")}</div></div>
            </div>
          </Section>) : null;
      case "cash_flow":
        return <Section title={t("Income vs. expenses")}><Plot figure={dash.data?.charts.monthly_cashflow} /></Section>;
      case "spending":
        return <Section title={t("Where the money goes")}><Plot figure={dash.data?.charts.category_breakdown} /></Section>;
      case "net_worth":
        return <Section title={t("Net worth")}><Plot figure={dash.data?.charts.net_worth} /></Section>;
      case "budgets":
        if (envelope && env.data) {
          const e = env.data;
          const rows = e.groups.flatMap((g) => g.items)
            .filter((r) => r.status === "overspent" || r.status === "underfunded").slice(0, 5);
          return (
            <Section title={t("Budget this month")}
              actions={<Link href="/budgets/"><FLink as="span">{t("Budgets")}</FLink></Link>}>
              <div className={`hero ${e.ready_to_assign < 0 ? "bad" : e.ready_to_assign > 0 ? "good" : ""}`}>
                <div><div className="hero-label">{t("Ready to Assign")}</div>
                  <div className="hero-value">{money(e.ready_to_assign, e.currency)}</div></div>
              </div>
              {rows.length === 0 ? <Empty>{t("Every category is funded and nothing is overspent.")}</Empty>
                : rows.map((r) => (
                  <div key={r.category_id ?? 0} className="list-row">
                    <span className="grow">{t(r.name)}</span>
                    <span className={`pill ${r.status}`}>{r.status === "overspent"
                      ? money(r.available) : t("{a} short", { a: money(r.shortfall) })}</span>
                  </div>))}
            </Section>);
        }
        return <Section title={t("Budgets this month")}><Plot figure={dash.data?.charts.budget_vs_actual} /></Section>;
      case "upcoming":
        return (
          <Section title={t("Coming up")} sub={t("Bills and income in the next 14 days")}
            actions={<Link href="/recurring/"><FLink as="span">{t("Bills & recurring")}</FLink></Link>}>
            {reminders.data?.length === 0 && <Empty>{t("Nothing due in the next 14 days.")}</Empty>}
            {reminders.data?.slice(0, 6).map((r) => (
              <div className="list-row" key={r.key}>
                <span className="glyph" aria-hidden>{r.auto_post ? I.autorenew : I.calendarMonth}</span>
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
          </Section>);
      case "insights":
        return (
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
          </Section>);
      case "accounts":
        return (
          <Section title={t("Accounts")}
            actions={<Link href="/accounts/"><FLink as="span">{t("All accounts")}</FLink></Link>}>
            {accounts.data?.filter((a) => !a.is_archived).slice(0, 8).map((a) => (
              <div key={a.id} className="list-row">
                <span className="grow"><span className="cell-main">{a.name}</span>
                  <span className="cell-sub">{a.institution ?? t(a.type)}</span></span>
                <span className={`num ${signClass(a.balance)}`}>{money(a.balance, a.currency)}</span>
              </div>))}
          </Section>);
      case "goals":
        return (
          <Section title={t("Goals")}
            actions={<Link href="/goals/"><FLink as="span">{t("All goals")}</FLink></Link>}>
            {goals.data?.length === 0 && <Empty>{t("No savings goals yet.")}</Empty>}
            {goals.data?.slice(0, 4).map((g) => (
              <div key={g.id} className="bar-row">
                <div className="row"><span className="grow">{g.name}</span>
                  <span className="caption">{money(g.saved_amount, g.currency)} / {money(g.target_amount)}</span></div>
                <Progress value={g.progress} status={g.status === "achieved" ? "achieved" : undefined} />
              </div>))}
          </Section>);
    }
  };

  return (
    <>
      <PageHead title={t(greeting(new Date().getHours()))}
        sub={new Date().toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long" })}>
        <TabList size="small" selectedValue={period}
          onTabSelect={(_, d) => setPeriod(String(d.value))}>
          {Object.entries(PERIODS).map(([k, label]) => (
            <Tab key={k} value={k}>{t(label)}</Tab>))}
        </TabList>
        <Tooltip content={t("Customise home")} relationship="label">
          <Button appearance="subtle" icon={<Settings20Regular />} onClick={() => setCustomize(true)} />
        </Tooltip>
      </PageHead>
      {customize && layout && <Customize layout={layout} onClose={() => setCustomize(false)}
        onSave={(l) => { setLayout(l); put("/api/settings", { home_layout: l }).catch(() => {}); }} />}
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
          action={<div className="row">
            <Link href="/accounts/"><Button appearance="primary" size="small">{t("Add an account")}</Button></Link>
            <Link href="/settings/"><Button size="small">{t("Set up sync")}</Button></Link></div>}>
          {t("Add an account and import a bank statement. Already use PFI on another device? Set up sync with the same cloud drive and passphrase.")}
        </Banner>)}
      {!s && dash.loading && <Spinner label={t("Loading…")} />}
      {s && (
        <>
          <div className="home-top">
            <div className="home-hero">
              <div className="home-hero-label">{t("Net worth")}</div>
              <div className="home-hero-value">{money(s.net_worth, cur)}</div>
              <div className="home-hero-sub">
                {t("Liquid")} {money(s.liquid, undefined, 0)} · {t("Invested")} {money(s.investments, undefined, 0)}
              </div>
            </div>
            <div className="home-kpis">
              <Kpi tone="lime" label={t("Income")} value={money(s.income, cur)}
                sub={t("Avg. {v} / month", { v: money(s.avg_monthly_income, undefined, 0) })} />
              <Kpi tone="pink" label={t("Expenses")} value={money(s.expenses, cur)}
                sub={t("Avg. {v} / month", { v: money(s.avg_monthly_expenses, undefined, 0) })} />
              <Kpi tone="violet" label={t("Net saved")} value={money(s.net, cur)}
                sub={t("{n} transactions", { n: s.transactions })} />
              <Kpi tone="cyan" label={t("Savings rate")} value={pct(s.savings_rate)}
                sub={t("(income − expenses) / income")} />
            </div>
          </div>
          <div className="home-cards">
            {(layout ?? []).filter((c) => !c.hidden).map((c) => {
              const card = renderCard(c.id);
              return card ? <div key={c.id}>{card}</div> : null;
            })}
          </div>
        </>)}
    </>
  );
}
