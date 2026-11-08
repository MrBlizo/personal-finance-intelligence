"use client";
import { useState } from "react";
import { Button, Input, Tab, TabList } from "@fluentui/react-components";
import {
  ArrowDownload20Regular, DocumentPdf20Regular, Table20Regular,
} from "@fluentui/react-icons";
import Plot from "@/components/Plot";
import { catLabel } from "@/components/refs";
import { Banner, Empty, Kpi, PageHead, Section, Spinner, StatusBadge, useLoad } from "@/components/ui";
import { MonthlyReport, NetWorthPoint, PlotFigure, downloadUrl, get } from "@/lib/api";
import { date, money, pct, signClass } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const BLUE = "#0072B2", SKY = "#56B4E9", GREEN = "#009E73";

export default function Reports() {
  const { t, lang } = useI18n();
  const now = new Date();
  const prevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const [month, setMonth] = useState(
    `${prevMonth.getFullYear()}-${String(prevMonth.getMonth() + 1).padStart(2, "0")}`);
  const [tab, setTab] = useState("monthly");
  const [months, setMonths] = useState(24);
  const rep = useLoad(() => get<MonthlyReport>("/api/reports/monthly", { month }), [month]);
  const nw = useLoad(() => get<{ currency: string; points: NetWorthPoint[] }>(
    "/api/reports/net-worth", { months }), [months]);
  const r = rep.data;
  const cur = r?.currency ?? "CHF";

  const nwFig: PlotFigure | null = nw.data ? {
    data: [
      { type: "scatter", mode: "lines", name: "Liquid", stackgroup: "nw",
        x: nw.data.points.map((p) => p.date), y: nw.data.points.map((p) => p.liquid),
        line: { color: SKY, width: 0 } },
      { type: "scatter", mode: "lines", name: "Investments", stackgroup: "nw",
        x: nw.data.points.map((p) => p.date), y: nw.data.points.map((p) => p.investments),
        line: { color: GREEN, width: 0 } },
      { type: "scatter", mode: "lines+markers", name: "Net worth",
        x: nw.data.points.map((p) => p.date), y: nw.data.points.map((p) => p.total),
        line: { color: BLUE, width: 2.5 }, marker: { size: 5 } },
    ],
    layout: { margin: { l: 64, r: 12, t: 8, b: 40 }, hovermode: "x unified",
      legend: { orientation: "h", y: 1.08 }, yaxis: { title: { text: `Value / ${nw.data.currency}` } } },
  } : null;

  return (
    <>
      <PageHead title={t("Reports")} sub={t("Monthly report, exports and net-worth history")}>
        <Button icon={<Table20Regular />} as="a" href={downloadUrl("/api/export/workbook.xlsx")}>
          {t("Excel workbook")}</Button>
        <Button icon={<ArrowDownload20Regular />} as="a" href={downloadUrl("/api/export/transactions.csv")}>
          {t("All transactions (CSV)")}</Button>
      </PageHead>
      <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(String(d.value))} style={{ marginBottom: 12 }}>
        <Tab value="monthly">{t("Monthly report")}</Tab>
        <Tab value="networth">{t("Net worth over time")}</Tab>
      </TabList>

      {tab === "monthly" && (
        <>
          <div className="filters">
            <Input type="month" value={month} onChange={(_, d) => d.value && setMonth(d.value)}
              aria-label={t("Month")} />
            <Button appearance="primary" icon={<DocumentPdf20Regular />} as="a"
              href={downloadUrl("/api/reports/monthly.pdf", { month, lang: lang === "fr" ? "fr" : "en" })}>
              {t("Download PDF")}</Button>
          </div>
          {rep.error && <Banner kind="error">{rep.error}</Banner>}
          {rep.loading && !r && <Spinner />}
          {r && (
            <>
              <div className="kpis">
                <Kpi label={t("Income")} value={money(r.income, cur)} />
                <Kpi label={t("Expenses")} value={money(r.expenses, cur)} />
                <Kpi label={t("Net saved")} value={money(r.net, cur)} cls={signClass(r.net)}
                  sub={t("Savings rate {v}", { v: pct(r.savings_rate) })} />
                <Kpi label={t("Net worth (end of month)")} value={money(r.net_worth, cur)}
                  sub={`${r.net_worth_change >= 0 ? "+" : ""}${money(r.net_worth_change)} ${t("vs. previous month")}`} />
              </div>
              {(r.uncategorised.count > 0 || r.missing_fx.length > 0) && (
                <Banner kind="warning" title={t("Data notes")}>
                  {r.uncategorised.count > 0 && t("{n} uncategorised expenses totalling {v}.",
                    { n: r.uncategorised.count, v: money(r.uncategorised.amount, cur) })}{" "}
                  {r.missing_fx.length > 0 && t("No exchange rate for {list}.", { list: r.missing_fx.join(", ") })}
                </Banner>)}
              <div className="grid g2">
                <Section title={t("Spending by category")}>
                  {r.categories.length === 0 ? <Empty>{t("No expenses this month.")}</Empty> : (
                    <div className="table-wrap"><table>
                      <thead><tr><th>{t("Category")}</th><th className="num">{t("This month")}</th>
                        <th className="num">{t("Previous")}</th><th className="num">{t("3-month avg.")}</th></tr></thead>
                      <tbody>{r.categories.map((c) => (
                        <tr key={c.category}><td>{catLabel(c.category, t)}</td>
                          <td className="num">{money(c.this)}</td>
                          <td className="num muted">{money(c.prev)}</td>
                          <td className={`num ${c.this > c.avg3 * 1.2 && c.this - c.avg3 > 50 ? "neg" : "muted"}`}>
                            {money(c.avg3)}</td></tr>))}</tbody>
                    </table></div>)}
                </Section>
                <Section title={t("Largest expenses")}>
                  {r.largest.length === 0 ? <Empty>{t("No expenses this month.")}</Empty> : (
                    <div className="table-wrap"><table>
                      <tbody>{r.largest.map((x, i) => (
                        <tr key={i}><td>{date(x.date)}</td>
                          <td><span className="cell-main">{x.description}</span>
                            <span className="cell-sub">{catLabel(x.category, t)}</span></td>
                          <td className="num">{money(x.amount, cur)}</td></tr>))}</tbody>
                    </table></div>)}
                </Section>
                <Section title={t("Budgets")}>
                  {r.budgets.length === 0 ? <Empty>{t("No budgets.")}</Empty> : (
                    <div className="table-wrap"><table>
                      <tbody>{r.budgets.map((b) => (
                        <tr key={b.id}><td>{catLabel(b.category, t)}</td>
                          <td className="num">{money(b.spent)} / {money(b.budget)}</td>
                          <td><StatusBadge status={b.status} /></td></tr>))}</tbody>
                    </table></div>)}
                </Section>
                <Section title={t("Top payees")}>
                  {r.payees.length === 0 ? <Empty>{t("No expenses this month.")}</Empty> : (
                    <div className="table-wrap"><table>
                      <tbody>{r.payees.map((p) => (
                        <tr key={p.payee}><td>{p.payee}</td>
                          <td className="num muted">{t("{n}×", { n: p.count })}</td>
                          <td className="num">{money(p.amount, cur)}</td></tr>))}</tbody>
                    </table></div>)}
                  {r.portfolio_value > 0 && (
                    <p className="caption" style={{ marginTop: 12 }}>
                      {t("Portfolio {v} · return this month {r} · dividends {d}", {
                        v: money(r.portfolio_value, cur), r: pct(r.month_return),
                        d: money(r.dividends, cur) })}</p>)}
                </Section>
              </div>
            </>)}
        </>)}

      {tab === "networth" && (
        <>
          <div className="filters">
            <TabList size="small" selectedValue={months} onTabSelect={(_, d) => setMonths(Number(d.value))}>
              {[12, 24, 60].map((m) => <Tab key={m} value={m}>{t("{n} months", { n: m })}</Tab>)}
            </TabList>
          </div>
          {nw.loading && !nw.data && <Spinner />}
          {nw.error && <Banner kind="error">{nw.error}</Banner>}
          {nw.data && (
            <>
              <Section><Plot figure={nwFig} height={360} /></Section>
              <Section title={t("Month-end values")}>
                <div className="table-wrap" style={{ maxHeight: 380 }}><table>
                  <thead><tr><th>{t("Month end")}</th><th className="num">{t("Liquid")}</th>
                    <th className="num">{t("Investments")}</th><th className="num">{t("Net worth")}</th>
                    <th className="num">{t("Change")}</th></tr></thead>
                  <tbody>{[...nw.data.points].reverse().map((p) => (
                    <tr key={p.date}><td>{date(p.date)}</td><td className="num">{money(p.liquid)}</td>
                      <td className="num">{money(p.investments)}</td><td className="num"><b>{money(p.total)}</b></td>
                      <td className={`num ${signClass(p.change)}`}>{p.change == null ? "—"
                        : `${p.change > 0 ? "+" : ""}${money(p.change)}`}</td></tr>))}</tbody>
                </table></div>
              </Section>
            </>)}
        </>)}
    </>
  );
}
