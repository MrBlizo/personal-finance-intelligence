"use client";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button } from "@fluentui/react-components";
import Plot from "@/components/Plot";
import { Banner, Empty, PageHead, Section, Spinner, useLoad } from "@/components/ui";
import { Insight, PlotFigure, get, insightText, post } from "@/lib/api";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";

const SEV_GLYPH: Record<string, string> = {
  warning: "", positive: "", info: "",
};
const CHARTS: [string, string][] = [
  ["category_trend", "Spending by category per month"],
  ["savings_rate", "Savings rate per month"],
  ["weekday_heatmap", "Spending by weekday"],
  ["top_merchants", "Top payees (12 months)"],
];

export default function Insights() {
  const t = useT();
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
    try {
      await post("/api/recurring", { name: d.payee, account_id: d.account_id, category_id: d.category_id,
        amount: String(-d.last_amount), frequency: d.cadence, start_date: d.last_date, is_active: true,
        remind_days: 3 });
      setAdded(new Set(added).add(d.payee));
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <>
      <PageHead title={t("Insights")} sub={ins.data ? t("Patterns found from {a} to {b}",
        { a: date(ins.data.start), b: date(ins.data.end) }) : ""} />
      {(ins.error || error) && <Banner kind="error">{ins.error ?? error}</Banner>}
      <Section>
        {ins.loading && !ins.data && <Spinner />}
        {ins.data?.insights.length === 0 && <Empty>{t("No notable patterns found. More history gives better insights.")}</Empty>}
        {ins.data?.insights.map((i, n) => {
          const x = insightText(i, t);
          return (
            <div className="insight" key={n} style={{ alignItems: "center" }}>
              <span className="glyph" aria-hidden>{SEV_GLYPH[i.severity]}</span>
              <div className="grow"><div>{x.title}</div><div className="caption">{x.detail}</div></div>
              {i.type === "subscription" && (
                added.has(String(i.data.payee))
                  ? <Badge appearance="tint" color="success">{t("Added")}</Badge>
                  : <Button size="small" onClick={() => addRecurring(i)}>{t("Add as recurring")}</Button>)}
              {i.type === "unusual_transaction" &&
                <Link href="/transactions/"><Button size="small">{t("Review")}</Button></Link>}
              {i.type === "data_quality" && i.data.currencies !== undefined &&
                <Link href="/settings/"><Button size="small">{t("Fix")}</Button></Link>}
              {i.type === "data_quality" && i.data.count !== undefined &&
                <Link href="/transactions/?uncategorized=1"><Button size="small">{t("Categorise")}</Button></Link>}
            </div>);
        })}
        <p className="caption" style={{ marginTop: 8 }}>
          {t("Insights are statistical observations (robust z-scores, regular payment intervals, month-over-month changes), not explanations.")}</p>
      </Section>
      <div className="grid g2" style={{ marginTop: 16 }}>
        {CHARTS.map(([n, title]) => (
          <Section key={n} title={t(title)}><Plot figure={charts.data?.[n]} /></Section>))}
      </div>
    </>
  );
}
