"use client";
// Year in review (Reports page): the year's totals, months, categories,
// payees and tax groups, with a PDF and an accountant-ready tax CSV.
import { useState } from "react";
import { Button, Select } from "@fluentui/react-components";
import { ArrowDownload20Regular, DocumentPdf20Regular } from "@fluentui/react-icons";
import Plot from "./Plot";
import { I } from "./icons";
import { catLabel, useRefs } from "./refs";
import { Banner, Empty, Kpi, Section, Spinner, useLoad } from "./ui";
import { PlotFigure, downloadUrl, get, put } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

interface YearData {
  year: number; currency: string; income: number; expenses: number; net: number;
  savings_rate: number | null;
  months: { month: string; income: number; spent: number; saved: number; net: number }[];
  categories: { category: string; amount: number; share: number }[];
  payees: { payee: string; amount: number }[];
  net_worth_start: number; net_worth_end: number;
  tax_groups: { group: string; label: string; amount: number }[];
  missing_fx: string[];
}
interface TaxGroups { groups: { id: string; label: string }[]; categories: Record<string, string> }

export function YearReport() {
  const { t, lang } = useI18n();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(new Date().getMonth() < 2 ? thisYear - 1 : thisYear);
  const [editTax, setEditTax] = useState(false);
  const rep = useLoad(() => get<YearData>("/api/reports/yearly", { year }), [year]);
  const tax = useLoad(() => get<TaxGroups>("/api/reports/tax-groups"), []);
  const refs = useRefs();
  const [taxErr, setTaxErr] = useState<string | null>(null);
  const y = rep.data;
  const cur = y?.currency;

  // Months still to come in the current year would show as zero.
  const nowMonth = new Date().toISOString().slice(0, 7);
  const shown = y?.months.filter((m) => m.month <= nowMonth) ?? [];
  const monthsFig: PlotFigure | null = y ? {
    data: [
      { type: "bar", name: "Income", x: shown.map((m) => m.month), y: shown.map((m) => m.income),
        marker: { color: "#009E73", cornerradius: 6 } },
      { type: "bar", name: "Spent", x: shown.map((m) => m.month), y: shown.map((m) => m.spent),
        marker: { color: "#CC79A7", cornerradius: 6 } },
      { type: "scatter", mode: "lines+markers", name: "Saved", x: shown.map((m) => m.month),
        y: shown.map((m) => m.net), line: { color: "#0072B2", width: 2.5, shape: "spline" } },
    ],
    layout: { barmode: "group", margin: { l: 60, r: 12, t: 8, b: 40 }, hovermode: "x unified",
      legend: { orientation: "h", y: 1.1 }, xaxis: { type: "date", tickformat: "%b" },
      yaxis: { title: { text: y.currency } } },
  } : null;

  const setGroup = async (id: number, group: string) => {
    setTaxErr(null);
    try {
      await put("/api/reports/tax-groups", { [id]: group || null });
      tax.reload(); rep.reload();
    } catch (e) { setTaxErr((e as Error).message); }
  };
  const cats = (refs.data?.categories ?? []).filter((c) => c.kind === "expense");
  const pdfLang = lang === "fr" ? "fr" : "en";

  return (
    <>
      <div className="filters">
        <Select aria-label={t("Year")} value={String(year)} onChange={(_, d) => setYear(Number(d.value))}>
          {Array.from({ length: 8 }, (_, i) => thisYear - i).map((v) => <option key={v} value={v}>{v}</option>)}
        </Select>
        <Button appearance="primary" icon={<DocumentPdf20Regular />} as="a"
          href={downloadUrl("/api/reports/yearly.pdf", { year, lang: pdfLang })}>{t("Year report (PDF)")}</Button>
        <Button icon={<ArrowDownload20Regular />} as="a" href={downloadUrl("/api/reports/tax.csv", { year })}>
          {t("Tax export (CSV)")}</Button>
      </div>
      {rep.error && <Banner kind="error">{rep.error}</Banner>}
      {rep.loading && !y && <Spinner />}
      {y && (<>
        {y.missing_fx.length > 0 && (
          <Banner kind="warning">{t("Some amounts have no exchange rate and are left out: {c}.", { c: y.missing_fx.join(", ") })}</Banner>)}
        <div className="year-hero">
          <span className="caption">{t("Your {y} in money", { y: y.year })}</span>
          <span className="year-big">{money(y.net, cur, 0)}</span>
          <span>{y.net >= 0 ? t("saved this year") : t("more spent than earned")}</span>
        </div>
        <div className="kpis">
          <Kpi tone="lime" label={t("Earned")} value={money(y.income, cur, 0)} />
          <Kpi tone="pink" label={t("Spent")} value={money(y.expenses, cur, 0)} />
          <Kpi tone="cyan" label={t("Savings rate")} value={y.savings_rate === null ? "—" : pct(y.savings_rate, 0)} />
          <Kpi tone="violet" label={t("Net worth")} value={money(y.net_worth_end, cur, 0)}
            sub={t("{d} since 1 January", { d: (y.net_worth_end >= y.net_worth_start ? "+" : "")
              + money(y.net_worth_end - y.net_worth_start, cur, 0) })} />
        </div>
        <Section title={t("Month by month")}><Plot figure={monthsFig} height={300} /></Section>
        <div className="grid g2">
          <Section title={t("Where it went")}>
            {y.categories.length === 0 ? <Empty>{t("No spending recorded in {y}.", { y: y.year })}</Empty> : (
              <div className="ybars">
                {y.categories.slice(0, 10).map((c) => (
                  <div key={c.category} className="ybar">
                    <span className="ybar-label">{catLabel(c.category, t)}</span>
                    <span className="ybar-track"><span className="ybar-fill" style={{ width: `${Math.max(2, c.share * 100)}%` }} /></span>
                    <span className="num">{money(c.amount, cur, 0)}</span>
                  </div>))}
              </div>)}
          </Section>
          <Section title={t("Top payees")}>
            {y.payees.length === 0 ? <Empty>{t("No payees yet.")}</Empty> : (
              <table><tbody>{y.payees.map((p, i) => (
                <tr key={p.payee}><td className="caption">{i + 1}</td><td>{p.payee}</td>
                  <td className="num">{money(p.amount, cur, 0)}</td></tr>))}</tbody></table>)}
          </Section>
        </div>
        <Section title={<span className="title-icon"><span className="icon" aria-hidden>{I.factCheck}</span>{t("For your tax return")}</span>}
          sub={t("Mark the categories that matter for your taxes (donations, medical, childcare…). The CSV lists every matching transaction for your accountant.")}
          actions={<Button appearance="subtle" onClick={() => setEditTax((v) => !v)}>
            {editTax ? t("Done") : t("Choose tax categories")}</Button>}>
          {taxErr && <Banner kind="error">{taxErr}</Banner>}
          {y.tax_groups.length === 0 && !editTax && (
            <Empty action={<Button onClick={() => setEditTax(true)}>{t("Choose tax categories")}</Button>}>
              {t("No categories are marked for taxes yet.")}</Empty>)}
          {y.tax_groups.length > 0 && (
            <table><thead><tr><th>{t("Group")}</th><th className="num">{t("Total {y}", { y: y.year })}</th></tr></thead>
              <tbody>{y.tax_groups.map((g) => (
                <tr key={g.group}><td>{t(g.label)}</td><td className="num">{money(g.amount, cur)}</td></tr>))}</tbody></table>)}
          {editTax && tax.data && (
            <div className="tax-edit">
              {cats.map((c) => (
                <label key={c.id} className="tax-row">
                  <span>{catLabel(c.full_name, t)}</span>
                  <Select value={tax.data!.categories[String(c.id)] ?? ""} onChange={(_, d) => setGroup(c.id, d.value)}>
                    <option value="">{t("Not for taxes")}</option>
                    {tax.data!.groups.map((g) => <option key={g.id} value={g.id}>{t(g.label)}</option>)}
                  </Select>
                </label>))}
              <p className="caption">{t("Subcategories follow their parent unless you mark them separately.")}</p>
            </div>)}
          <p className="caption">{t("PFI is not tax advice. Check what is deductible where you live.")}</p>
        </Section>
      </>)}
    </>
  );
}
