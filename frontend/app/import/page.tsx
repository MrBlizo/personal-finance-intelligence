"use client";
import Link from "next/link";
import { useState } from "react";
import { accountOptions, useRefs } from "@/components/refs";
import { Banner, Confirm, Empty, PageHead, Spinner, useLoad } from "@/components/ui";
import { ImportBatch, ImportPreview, ImportResult, api, del, get } from "@/lib/api";
import { date } from "@/lib/format";

type Mapping = {
  account_id: string; date_column: string; description_column: string;
  amount_column: string; debit_column: string; credit_column: string;
  merchant_column: string; date_format: string; dayfirst: boolean;
  decimal: "." | ","; invert_sign: boolean; skip_rows: number;
};

export default function Import() {
  const refs = useRefs();
  const batches = useLoad(() => get<ImportBatch[]>("/api/import/batches"));
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
  const preview = async () => {
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const p = await api<ImportPreview>("/api/import/preview",
        { method: "POST", body: form(file), query: { skip_rows: skip } });
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
        setPresetName(file.name.replace(/\.[^.]+$/, ""));
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
    <label className="field">{label}{required ? " *" : ""}
      <select value={String(m?.[key] ?? "")} onChange={(e) => setM({ ...m!, [key]: e.target.value })}>
        <option value="">—</option>
        {prev?.columns.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </label>);

  return (
    <>
      <PageHead title="Import bank statement"
        sub="CSV export from your bank. The original file is archived unchanged (read-only)." />
      {error && <Banner kind="error" onClose={() => setError(null)}>{error}</Banner>}
      {result && (
        <Banner kind={result.rows_failed ? "warning" : "success"} onClose={() => setResult(null)}>
          Imported <b>{result.rows_imported}</b> of {result.rows_total} rows
          ({result.categorized} auto-categorized, {result.rows_duplicate} duplicates skipped,
          {" "}{result.rows_failed} failed){result.preset ? `; settings saved as “${result.preset}”` : ""}.
          {" "}<Link href="/transactions/?uncategorized=1">Review uncategorized</Link>
          {result.errors.length > 0 && (
            <ul className="small">{result.errors.slice(0, 10).map((e) => <li key={e}>{e}</li>)}</ul>)}
        </Banner>)}
      <div className="stack">
        <div className="card">
          <h3>1. Choose file</h3>
          {accounts.length === 0 && refs.data && (
            <Banner kind="info">Create an account first on the <Link href="/accounts/">Accounts</Link> page.</Banner>)}
          <div className="toolbar">
            <input type="file" accept=".csv,.txt,text/csv"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPrev(null); }} />
            <label className="field">Skip lines before header
              <input type="number" min={0} value={skip} style={{ width: 90 }}
                onChange={(e) => setSkip(Number(e.target.value))} /></label>
            <button className="primary" disabled={!file || busy} onClick={preview}>
              {busy && !prev ? "Reading…" : "Preview"}</button>
          </div>
        </div>
        {prev && m && (
          <div className="card">
            <h3>2. Map columns</h3>
            {prev.preset && (
              <Banner kind="success">Recognised this file format: settings from preset
                {" "}<b>{prev.preset.name}</b> were applied. Check them and click Import.</Banner>)}
            {!prev.preset && prev.guess.mostly_positive === true && (
              <Banner kind="info">Most amounts in this file are positive, so purchases are probably
                listed as positive numbers. <b>Invert signs</b> has been ticked for you; untick it if
                the positive amounts are income.</Banner>)}
            {prev.already_imported && (
              <Banner kind="warning">This exact file was imported before. Rows already present will be skipped as duplicates.</Banner>)}
            <p className="muted small">Detected: delimiter “{prev.delimiter === "\t" ? "tab" : prev.delimiter}”,
              encoding {prev.encoding}, {prev.columns.length} columns.</p>
            <div className="form-grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
              <label className="field">Account *
                <select value={m.account_id} onChange={(e) => setM({ ...m, account_id: e.target.value })}>
                  {accountOptions(accounts).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select></label>
              {col("date_column", "Date", true)}
              {col("description_column", "Description", true)}
              {col("merchant_column", "Payee (optional)")}
              {col("amount_column", "Signed amount")}
              {col("debit_column", "…or debit (out)")}
              {col("credit_column", "…and credit (in)")}
              <label className="field">Decimal separator
                <select value={m.decimal} onChange={(e) => setM({ ...m, decimal: e.target.value as "." | "," })}>
                  <option value=".">1&apos;234.50 (dot)</option><option value=",">1.234,50 (comma)</option>
                </select></label>
              <label className="field">Date format (optional)
                <input placeholder="e.g. %d.%m.%Y" value={m.date_format}
                  onChange={(e) => setM({ ...m, date_format: e.target.value })} /></label>
              <label className="check"><input type="checkbox" checked={m.dayfirst}
                onChange={(e) => setM({ ...m, dayfirst: e.target.checked })} />Day before month</label>
              <label className="check"><input type="checkbox" checked={m.invert_sign}
                onChange={(e) => setM({ ...m, invert_sign: e.target.checked })} />Invert signs</label>
            </div>
            <div className="table-wrap" style={{ marginTop: 16, maxHeight: 320, overflow: "auto" }}>
              <table className="small">
                <thead><tr>{prev.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                <tbody>{prev.rows.map((r, i) => (
                  <tr key={i}>{prev.columns.map((c) => <td key={c}>{r[c]}</td>)}</tr>))}</tbody>
              </table>
            </div>
            <div className="toolbar" style={{ marginTop: 16 }}>
              <label className="check"><input type="checkbox" checked={savePreset}
                onChange={(e) => setSavePreset(e.target.checked)} />Remember these settings as</label>
              <input value={presetName} placeholder="e.g. UBS account" style={{ width: 240 }}
                onChange={(e) => setPresetName(e.target.value)} disabled={!savePreset} />
              <span className="small muted">Files with the same columns are recognised next time.</span>
            </div>
            <div className="modal-actions">
              <button onClick={() => setPrev(null)}>Cancel</button>
              <button className="primary" disabled={busy || !m.account_id || !m.date_column
                || !m.description_column || !(m.amount_column || m.debit_column || m.credit_column)}
                onClick={commit}>{busy ? "Importing…" : "Import"}</button>
            </div>
          </div>)}
        <div className="card table-wrap">
          <h3>Import history</h3>
          {batches.loading && !batches.data && <Spinner />}
          {batches.data?.length === 0 && <Empty>No imports yet.</Empty>}
          {!!batches.data?.length && (
            <table><thead><tr><th>Date</th><th>File</th><th>Account</th>
              <th className="num">Imported</th><th className="num">Duplicates</th>
              <th className="num">Failed</th><th /></tr></thead>
              <tbody>{batches.data.map((b) => (
                <tr key={b.id}><td>{date(b.imported_at)}</td><td>{b.filename}</td>
                  <td>{accName(b.account_id)}</td><td className="num">{b.rows_imported}</td>
                  <td className="num">{b.rows_duplicate}</td><td className="num">{b.rows_failed}</td>
                  <td className="num"><button className="link danger" onClick={() => setUndo(b)}>Undo</button></td>
                </tr>))}</tbody></table>)}
        </div>
      </div>
      {undo && <Confirm onClose={() => setUndo(null)}
        text={`Remove the ${undo.rows_imported} transactions imported from “${undo.filename}”? The archived original file is kept.`}
        onYes={async () => { await del(`/api/import/batches/${undo.id}`); batches.reload(); }} />}
    </>
  );
}
