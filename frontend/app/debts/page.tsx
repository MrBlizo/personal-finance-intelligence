"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge, Button, Input, Tab, TabList, Tooltip } from "@fluentui/react-components";
import { Edit20Regular } from "@fluentui/react-icons";
import Plot from "@/components/Plot";
import {
  Banner, Empty, FormModal, Kpi, PageHead, Section, Spinner, useLoad,
} from "@/components/ui";
import { DebtInfo, DebtPlan, PlotFigure, get, post, put } from "@/lib/api";
import { money, num } from "@/lib/format";
import { useI18n, useT } from "@/lib/i18n";

const STRATEGIES = [
  { id: "avalanche", label: "Highest interest first", help: "Avalanche: extra money goes to the debt with the highest interest rate. Usually the cheapest." },
  { id: "snowball", label: "Smallest balance first", help: "Snowball: extra money goes to the smallest debt, so debts disappear sooner. Often easier to keep up." },
  { id: "minimum", label: "Minimum payments only", help: "Only the minimum payment on each debt, for comparison." },
] as const;
type StrategyId = typeof STRATEGIES[number]["id"];
const COLOURS: Record<StrategyId, string> = { avalanche: "#0072B2", snowball: "#E69F00", minimum: "#999999" };

function monthLabel(iso: string | null, lang: string) {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "ar" ? "ar" : lang, { month: "long", year: "numeric" });
}

function duration(months: number | null, t: ReturnType<typeof useT>) {
  if (months === null) return t("never");
  const y = Math.floor(months / 12), m = months % 12;
  if (!y) return t("{m} months", { m });
  return m ? t("{y} years {m} months", { y, m }) : t("{y} years", { y });
}

export default function Debts() {
  const t = useT();
  const { lang } = useI18n();
  const debts = useLoad(() => get<DebtInfo>("/api/debts"));
  const [extra, setExtra] = useState("100");
  const [shown, setShown] = useState<StrategyId>("avalanche");
  const [edit, setEdit] = useState<DebtInfo["debts"][number] | null>(null);
  const extraNum = Math.max(Number(extra.replace(",", ".")) || 0, 0);
  const plan = useLoad(() => post<DebtPlan>("/api/debts/plan", { extra: extraNum.toFixed(2) }),
    [extraNum, debts.data]);
  const p = plan.data;
  const cur = debts.data?.currency ?? "CHF";
  const owing = (debts.data?.debts ?? []).filter((d) => d.owed > 0);
  const missingTerms = owing.filter((d) => !d.has_terms);
  const figure = useMemo<PlotFigure | null>(() => {
    if (!p) return null;
    const start = new Date(p.start + "T00:00:00");
    const x = (n: number) => {
      const d = new Date(start.getFullYear(), start.getMonth() + n + 1, 1);
      return d.toISOString().slice(0, 10);
    };
    return {
      data: STRATEGIES.map((s) => ({
        type: "scatter", mode: "lines", name: t(s.label),
        line: { color: COLOURS[s.id], width: s.id === shown ? 3 : 1.5, dash: s.id === "minimum" ? "dot" : "solid" },
        x: p.plans[s.id].schedule.map((_, i) => x(i)), y: p.plans[s.id].schedule,
        hovertemplate: `%{y:,.0f} ${p.currency}<extra>${t(s.label)}</extra>`,
      })),
      layout: { margin: { l: 56, r: 16, t: 8, b: 40 }, showlegend: true,
        legend: { orientation: "h", y: -0.2 },
        yaxis: { title: { text: t("Still owed ({cur})", { cur: p.currency }) }, rangemode: "tozero" } },
    };
  }, [p, shown, t]);
  const best = p?.plans[shown];
  const minimum = p?.plans.minimum;

  return (
    <>
      <PageHead title={t("Debt payoff")}
        sub={t("Plan how to pay off loans and credit cards, and what each extra amount saves")} />
      {debts.error && <Banner kind="error">{debts.error}</Banner>}
      {debts.data?.warnings.map((w) => <Banner key={w} kind="warning">{w}</Banner>)}
      {debts.loading && !debts.data && <Spinner />}
      {debts.data && debts.data.debts.length === 0 && (
        <div className="card"><Empty action={<Link href="/accounts/"><Button appearance="primary">{t("Open accounts")}</Button></Link>}>
          {t("No loan or credit-card accounts yet. Add one under Accounts (type “Loan” or “Credit card”) with what you owe as a negative opening balance.")}
        </Empty></div>)}
      {missingTerms.length > 0 && (
        <Banner kind="warning">{t("Add the interest rate and minimum payment of {list}; without them the plan assumes 0 % interest and no minimum payment.",
          { list: missingTerms.map((d) => d.name).join(", ") })}</Banner>)}
      {debts.data && debts.data.debts.length > 0 && (
        <>
          <Section title={t("Your debts")}>
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("Account")}</th><th className="num">{t("Owed")}</th>
                  <th className="num">{t("Interest rate")}</th><th className="num">{t("Minimum payment")}</th>
                  <th>{t("Paid off ({plan})", { plan: t(STRATEGIES.find((s) => s.id === shown)!.label) })}</th><th /></tr></thead>
                <tbody>{debts.data.debts.map((d) => {
                  const row = best?.debts.find((x) => x.account_id === d.account_id);
                  return (
                    <tr key={d.account_id}>
                      <td>{d.name}</td>
                      <td className="num">{d.owed > 0 ? money(d.owed, d.currency) : <Badge appearance="tint" color="success">{t("Paid off")}</Badge>}</td>
                      <td className="num">{d.has_terms ? `${num(d.apr, 2)} %` : "—"}</td>
                      <td className="num">{d.has_terms ? money(d.min_payment, d.currency) : "—"}</td>
                      <td>{d.owed > 0 && row ? <>{monthLabel(row.payoff_date, lang)}
                        <span className="cell-sub">{t("interest {v}", { v: money(row.interest, cur) })}</span></> : ""}</td>
                      <td className="actions"><Tooltip content={t("Interest and minimum payment")} relationship="label">
                        <Button appearance="subtle" size="small" icon={<Edit20Regular />} onClick={() => setEdit(d)} />
                      </Tooltip></td>
                    </tr>);
                })}</tbody>
              </table>
            </div>
          </Section>

          {owing.length > 0 && (
            <Section title={t("Payoff plan")}
              sub={t("An estimate: interest is charged monthly on what is left, amounts in {cur}.", { cur })}
              actions={<div className="row">
                <span className="caption">{t("Extra each month")}</span>
                <Input type="number" min={0} step="10" value={extra} style={{ width: 120 }}
                  contentAfter={<span className="caption">{cur}</span>}
                  onChange={(_, v) => setExtra(v.value)} />
              </div>}>
              <TabList selectedValue={shown} onTabSelect={(_, d) => setShown(d.value as StrategyId)}>
                {STRATEGIES.map((s) => <Tab key={s.id} value={s.id}>{t(s.label)}</Tab>)}
              </TabList>
              <div className="caption" style={{ margin: "8px 0 12px" }}>{t(STRATEGIES.find((s) => s.id === shown)!.help)}</div>
              {plan.error && <Banner kind="error">{plan.error}</Banner>}
              {best && minimum && (
                <div className="kpis">
                  <Kpi label={t("Debt-free")} value={best.months === null ? t("never") : monthLabel(best.payoff_date, lang)}
                    sub={duration(best.months, t)} />
                  <Kpi label={t("Total interest")} value={money(best.interest, cur, 0)}
                    sub={shown !== "minimum" && minimum.months !== null && best.months !== null
                      ? t("{v} less than minimum payments only", { v: money(minimum.interest - best.interest, cur, 0) }) : undefined} />
                  <Kpi label={t("Monthly payment")} value={money(
                    owing.reduce((s, d) => s + (d.min_payment_base ?? 0), 0) + (shown === "minimum" ? 0 : extraNum), cur, 0)}
                    sub={shown === "minimum" ? t("minimums only") : t("minimums + extra")} />
                </div>)}
              {best && best.months === null && (
                <Banner kind="warning">{t("With these payments at least one debt is never paid off: the payment does not cover the interest. Raise the minimum payment or the extra amount.")}</Banner>)}
              {figure && <Plot figure={figure} height={300} />}
            </Section>)}
        </>)}

      {edit && (
        <FormModal title={t("{name}: interest and minimum payment", { name: edit.name })} onClose={() => setEdit(null)}
          initial={{ apr: edit.has_terms ? edit.apr : "", min_payment: edit.has_terms ? edit.min_payment : "" }}
          fields={[
            { name: "apr", label: t("Interest rate per year (%)"), type: "number", step: "0.01", required: true,
              help: t("The effective annual rate on your statement or contract, e.g. 12.9.") },
            { name: "min_payment", label: t("Minimum payment per month ({cur})", { cur: edit.currency }),
              type: "number", step: "0.01", required: true,
              help: t("For a loan, the fixed monthly instalment.") },
          ]}
          onSubmit={async (v) => {
            await put(`/api/debts/${edit.account_id}`, { apr: String(v.apr), min_payment: String(v.min_payment) });
            debts.reload();
          }} />)}
    </>
  );
}
