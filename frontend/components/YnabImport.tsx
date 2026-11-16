"use client";
// Move from YNAB: upload the zip from YNAB's "Export Plan", check what will
// be created, then import.
import { useRef, useState } from "react";
import { Button, Field, Input } from "@fluentui/react-components";
import { ArrowUpload20Regular } from "@fluentui/react-icons";
import { Banner, Section } from "./ui";
import { YnabReport, api } from "@/lib/api";
import { money } from "@/lib/format";
import { useT } from "@/lib/i18n";

export function YnabImport({ baseCurrency, onDone }: { baseCurrency: string; onDone?: () => void }) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [currency, setCurrency] = useState(baseCurrency);
  const [report, setReport] = useState<YnabReport | null>(null);
  const [done, setDone] = useState<YnabReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const send = async (dry: boolean) => {
    if (!file) return;
    setBusy(true); setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("currency", currency.toUpperCase());
    form.append("dry_run", dry ? "true" : "false");
    try {
      const r = await api<YnabReport>("/api/import/ynab", { method: "POST", body: form });
      if (dry) setReport(r); else { setDone(r); setReport(null); onDone?.(); }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const Summary = ({ r }: { r: YnabReport }) => (
    <ul className="hint-list" style={{ fontSize: 14 }}>
      <li>{t("{n} transactions ({tr} transfers, {sp} split)", { n: r.transactions, tr: r.transfers, sp: r.splits })}</li>
      {r.duplicates > 0 && <li>{t("{n} already imported, skipped", { n: r.duplicates })}</li>}
      <li>{t("Accounts: {a}", { a: r.accounts_created.join(", ") || t("none new") })}</li>
      <li>{t("{n} new categories", { n: r.categories_created.length })}</li>
      <li>{t("{n} monthly assignments for envelope budgeting", { n: r.assignments })}</li>
      {r.skipped.map((s) => <li key={s}>{s}</li>)}
    </ul>);
  return (
    <Section title={t("Move from YNAB")}
      sub={t("In YNAB's web app choose Export Plan, then upload the zip here. Accounts, categories, transactions and monthly assignments come over; nothing is sent anywhere.")}>
      {error && <Banner kind="error">{error}</Banner>}
      {done && (
        <Banner kind="success" title={t("YNAB data imported")} onClose={() => setDone(null)}>
          <Summary r={done} />
          {done.differences.length === 0 && done.checked_month
            ? t("Every category's available amount for {m} matches YNAB.", { m: done.checked_month })
            : done.differences.length > 0 && t("{n} categories differ from YNAB for {m} (often credit-card categories, which work differently here).",
              { n: done.differences.length, m: done.checked_month ?? "" })}
        </Banner>)}
      <div className="row" style={{ alignItems: "flex-end" }}>
        <input ref={input} type="file" accept=".zip,.csv,.tsv" hidden
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); }} />
        <Button icon={<ArrowUpload20Regular />} onClick={() => input.current?.click()}>
          {file ? file.name : t("Choose YNAB export…")}</Button>
        <Field label={t("Currency of your YNAB accounts")}>
          <Input value={currency} style={{ width: 90 }} maxLength={3}
            onChange={(_, d) => setCurrency(d.value.toUpperCase())} />
        </Field>
        <Button appearance="primary" disabled={!file || busy} onClick={() => send(true)}>
          {t("Check")}</Button>
      </div>
      {report && (
        <div style={{ marginTop: 12 }}>
          <div className="detail-head">{t("This will import:")}</div>
          <Summary r={report} />
          {report.differences.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary>{t("{n} categories would differ from YNAB", { n: report.differences.length })}</summary>
              <table><tbody>{report.differences.map((d) => (
                <tr key={d.category}><td>{d.category}</td><td className="num">YNAB {money(d.ynab)}</td>
                  <td className="num">PFI {money(d.pfi)}</td></tr>))}</tbody></table>
            </details>)}
          <div className="row" style={{ marginTop: 12 }}>
            <Button appearance="primary" disabled={busy} onClick={() => send(false)}>{t("Import")}</Button>
            <Button onClick={() => setReport(null)}>{t("Cancel")}</Button>
          </div>
        </div>)}
    </Section>);
}
