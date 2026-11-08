"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import {
  Button, Checkbox, Field, Input, Select, SpinButton,
} from "@fluentui/react-components";
import { ArrowUpload20Regular, DocumentTable20Regular } from "@fluentui/react-icons";
import { accountOptions, useRefs } from "@/components/refs";
import { Banner, Confirm, Empty, PageHead, Section, Spinner, useLoad } from "@/components/ui";
import { ImportBatch, ImportPreview, ImportResult, api, del, get } from "@/lib/api";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Mapping = {
  account_id: string; date_column: string; description_column: string;
  amount_column: string; debit_column: string; credit_column: string;
  merchant_column: string; date_format: string; dayfirst: boolean;
  decimal: "." | ","; invert_sign: boolean; skip_rows: number;
};

export default function Import() {
  const t = useT();
  const refs = useRefs();
  const batches = useLoad(() => get<ImportBatch[]>("/api/import/batches"));
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [skip, setSkip] = useState(0);
  const [prev, setPrev] = useState<ImportPreview | null>(null);
  const [m, setM] = useState<Mapping | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<ImportBatch | null>(null);
  const [presetName, setPresetName] = useState("");
  const [savePreset, setSavePreset] = useState(true);
  const accounts = refs.data?.accounts ?? [];
  const accName = (id: number) => accounts.find((a) => a.id === id)?.name ?? `#${id}`;

  const form = (f: File) => { const d = new FormData(); d.append("file", f); return d; };
  const preview = async (f: File | null = file) => {
    if (!f) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const p = await api<ImportPreview>("/api/import/preview",
        { method: "POST", body: form(f), query: { skip_rows: skip } });
      setPrev(p);
      const g = p.guess;
      const s = (k: string) => (typeof g[k] === "string" ? (g[k] as string) : "");
      if (p.preset) {
        const pm = p.preset.mapping as Record<string, unknown>;
        const str = (k: string) => (pm[k] == null ? "" : String(pm[k]));
        setM({
          account_id: str("account_id"), date_column: str("date_column"),
          description_column: str("description_column"), amount_column: str("amount_column"),
          debit_column: str("debit_column"), credit_column: str("credit_column"),
          merchant_column: str("merchant_column"), date_format: str("date_format"),
          dayfirst: pm.dayfirst !== false, decimal: pm.decimal === "," ? "," : ".",
          invert_sign: pm.invert_sign === true, skip_rows: skip,
        });
        setPresetName(p.preset.name);
      } else {
        setM({
          account_id: m?.account_id || String(accounts.find((a) => !a.is_archived)?.id ?? ""),
          date_column: s("date_column"), description_column: s("description_column"),
          amount_column: s("amount_column"),
          debit_column: s("amount_column") ? "" : s("debit_column"),
          credit_column: s("amount_column") ? "" : s("credit_column"),
          merchant_column: s("merchant_column"), date_format: "", dayfirst: true,
          decimal: g.decimal === "," ? "," : ".", invert_sign: g.mostly_positive === true,
          skip_rows: skip,
        });
        setPresetName(f.name.replace(/\.[^.]+$/, ""));
      }
    } catch (e) { setError((e as Error).message); setPrev(null); }
    finally { setBusy(false); }
  };
  const commit = async () => {
    if (!file || !m) return;
    setBusy(true); setError(null);
    try {
      const d = form(file);
      const body: Record<string, unknown> = { ...m, account_id: Number(m.account_id) };
      for (const k of ["amount_column", "debit_column", "credit_column", "merchant_column", "date_format"]) {
        if (!body[k]) body[k] = null;
      }
      d.append("mapping", JSON.stringify(body));
      if (savePreset && presetName.trim()) d.append("save_preset", presetName.trim());
      setResult(await api<ImportResult>("/api/import/commit", { method: "POST", body: d }));
      setPrev(null); setFile(null); batches.reload();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const col = (key: keyof Mapping, label: string, required = false) => (
    <Field label={label} required={required}>
      <Select value={String(m?.[key] ?? "")} onChange={(_, d) => setM({ ...m!, [key]: d.value })}>
        <option value="">—</option>
        {prev?.columns.map((c) => <option key={c} value={c}>{c}</option>)}
      </Select>
    </Field>);

  return (
    <>
      <PageHead title={t("Import bank statement")}
        sub={t("CSV export from your bank. The original file is archived unchanged (read-only).")} />
      {error && <Banner kind="error" onClose={() => setError(null)}>{error}</Banner>}
      {result && (
        <Banner kind={result.rows_failed ? "warning" : "success"} onClose={() => setResult(null)}
          title={t("Imported {a} of {b} rows", { a: result.rows_imported, b: result.rows_total })}
          action={<Link href="/transactions/?uncategorized=1">
            <Button size="small">{t("Review uncategorised")}</Button></Link>}>
          {t("{r} categorised by rules, {l} by learned suggestions, {d} duplicates skipped, {f} failed.", {
            r: result.categorized, l: result.learned ?? 0, d: result.rows_duplicate,
            f: result.rows_failed })}
          {result.preset ? " " + t("Settings saved as “{p}”.", { p: result.preset }) : ""}
          {result.errors.length > 0 && (
            <ul className="hint-list">{result.errors.slice(0, 10).map((e) => <li key={e}>{e}</li>)}</ul>)}
        </Banner>)}
      <Section title={t("1. Choose a file")}>
        {accounts.length === 0 && refs.data && (
          <Banner kind="info" action={<Link href="/accounts/"><Button size="small">{t("Accounts")}</Button></Link>}>
            {t("Create an account first.")}</Banner>)}
        <div className="row" style={{ alignItems: "flex-end", gap: 16 }}>
          <input ref={fileInput} type="file" accept=".csv,.txt,text/csv" hidden
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f); setPrev(null);
              if (f) preview(f);
              e.target.value = "";
            }} />
          <Button icon={<DocumentTable20Regular />} onClick={() => fileInput.current?.click()}>
            {file ? file.name : t("Browse…")}</Button>
          <Field label={t("Skip lines before header")}>
            <SpinButton min={0} max={50} value={skip} style={{ width: 110 }}
              onChange={(_, d) => setSkip(Number(d.value ?? d.displayValue ?? 0))} />
          </Field>
          <Button appearance="primary" icon={<ArrowUpload20Regular />} disabled={!file || busy}
            onClick={() => preview()}>
            {busy && !prev ? t("Reading…") : t("Preview")}</Button>
        </div>
      </Section>
      {prev && m && (
        <Section title={t("2. Map columns")}
          sub={t("Detected: delimiter “{d}”, encoding {e}, {n} columns.", {
            d: prev.delimiter === "\t" ? "tab" : prev.delimiter, e: prev.encoding,
            n: prev.columns.length })}>
          {prev.preset && (
            <Banner kind="success">{t("Recognised this file format: settings from “{p}” were applied. Check them and click Import.",
              { p: prev.preset.name })}</Banner>)}
          {!prev.preset && prev.guess.mostly_positive === true && (
            <Banner kind="info">{t("Most amounts in this file are positive, so purchases are probably listed as positive numbers. “Invert signs” has been switched on for you; switch it off if the positive amounts are income.")}</Banner>)}
          {prev.already_imported && (
            <Banner kind="warning">{t("This exact file was imported before. Rows already present will be skipped as duplicates.")}</Banner>)}
          <div className="form-grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
            <Field label={t("Account")} required>
              <Select value={m.account_id} onChange={(_, d) => setM({ ...m, account_id: d.value })}>
                {accountOptions(accounts).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select></Field>
            {col("date_column", t("Date"), true)}
            {col("description_column", t("Description"), true)}
            {col("merchant_column", t("Payee (optional)"))}
            {col("amount_column", t("Signed amount"))}
            {col("debit_column", t("…or debit (out)"))}
            {col("credit_column", t("…and credit (in)"))}
            <Field label={t("Decimal separator")}>
              <Select value={m.decimal} onChange={(_, d) => setM({ ...m, decimal: d.value as "." | "," })}>
                <option value=".">1&apos;234.50 ({t("dot")})</option>
                <option value=",">1.234,50 ({t("comma")})</option>
              </Select></Field>
            <Field label={t("Date format (optional)")}>
              <Input placeholder="%d.%m.%Y" value={m.date_format}
                onChange={(_, d) => setM({ ...m, date_format: d.value })} /></Field>
            <Checkbox label={t("Day before month")} checked={m.dayfirst}
              onChange={(_, d) => setM({ ...m, dayfirst: Boolean(d.checked) })} />
            <Checkbox label={t("Invert signs")} checked={m.invert_sign}
              onChange={(_, d) => setM({ ...m, invert_sign: Boolean(d.checked) })} />
          </div>
          <div className="table-wrap card" style={{ marginTop: 16, maxHeight: 320, padding: 0 }}>
            <table style={{ fontSize: 12 }}>
              <thead><tr>{prev.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{prev.rows.map((r, i) => (
                <tr key={i}>{prev.columns.map((c) => <td key={c}>{r[c]}</td>)}</tr>))}</tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <Checkbox label={t("Remember these settings as")} checked={savePreset}
              onChange={(_, d) => setSavePreset(Boolean(d.checked))} />
            <Input value={presetName} placeholder={t("e.g. UBS account")} style={{ width: 240 }}
              onChange={(_, d) => setPresetName(d.value)} disabled={!savePreset} />
            <span className="caption">{t("Files with the same columns are recognised next time.")}</span>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <Button appearance="primary" disabled={busy || !m.account_id || !m.date_column
              || !m.description_column || !(m.amount_column || m.debit_column || m.credit_column)}
              onClick={commit}>{busy ? t("Importing…") : t("Import")}</Button>
            <Button onClick={() => setPrev(null)}>{t("Cancel")}</Button>
          </div>
        </Section>)}
      <Section title={t("Import history")}>
        {batches.loading && !batches.data && <Spinner />}
        {batches.data?.length === 0 && <Empty>{t("No imports yet.")}</Empty>}
        {!!batches.data?.length && (
          <div className="table-wrap">
            <table><thead><tr><th>{t("Date")}</th><th>{t("File")}</th><th>{t("Account")}</th>
              <th className="num">{t("Imported")}</th><th className="num">{t("Duplicates")}</th>
              <th className="num">{t("Failed")}</th><th /></tr></thead>
              <tbody>{batches.data.map((b) => (
                <tr key={b.id}><td>{date(b.imported_at)}</td><td>{b.filename}</td>
                  <td>{accName(b.account_id)}</td><td className="num">{b.rows_imported}</td>
                  <td className="num">{b.rows_duplicate}</td><td className="num">{b.rows_failed}</td>
                  <td className="actions"><Button appearance="subtle" size="small"
                    onClick={() => setUndo(b)}>{t("Undo")}</Button></td>
                </tr>))}</tbody></table>
          </div>)}
      </Section>
      {undo && <Confirm danger yesLabel={t("Undo import")} onClose={() => setUndo(null)}
        text={t("Remove the {n} transactions imported from “{f}”? The archived original file is kept.",
          { n: undo.rows_imported, f: undo.filename })}
        onYes={async () => { await del(`/api/import/batches/${undo.id}`); batches.reload(); }} />}
    </>
  );
}
