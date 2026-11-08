"use client";
import { useState } from "react";
import { categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, PageHead, Spinner, useLoad,
} from "@/components/ui";
import { Backup, Category, FxRate, Rule, api, del, get, post, put } from "@/lib/api";
import { CURRENCIES, date, num, today } from "@/lib/format";

type Info = { version: string; data_dir: string; database: string };

export default function SettingsPage() {
  const refs = useRefs();
  const rates = useLoad(() => get<FxRate[]>("/api/fx-rates"));
  const missing = useLoad(() => get<{ missing: string[] }>("/api/fx-rates/missing"));
  const rules = useLoad(() => get<Rule[]>("/api/rules"));
  const info = useLoad(() => get<Info>("/api/info"));
  const presets = useLoad(() => get<{ id: number; name: string }[]>("/api/import/presets"));
  const backups = useLoad(() => get<{ folder: string; available: boolean; backups: Backup[] }>("/api/backups"));
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [rateModal, setRateModal] = useState(false);
  const [catModal, setCatModal] = useState<Category | "new" | null>(null);
  const [ruleModal, setRuleModal] = useState<Rule | "new" | null>(null);
  const [confirm, setConfirm] = useState<{ text: string; run: () => Promise<void> } | null>(null);
  const s = refs.data?.settings;
  const cats = refs.data?.categories ?? [];
  const catName = (id: number) => cats.find((c) => c.id === id)?.full_name ?? `#${id}`;
  const run = async (f: () => Promise<string>) => {
    try { setMsg({ kind: "success", text: await f() }); }
    catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  };

  return (
    <>
      <PageHead title="Settings" />
      {msg && <Banner kind={msg.kind} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {!s && <Spinner />}
      {s && (
        <div className="stack">
          <div className="grid g2">
            <div className="card">
              <h2>Reporting currency</h2>
              <div className="toolbar">
                <select value={s.base_currency} onChange={(e) => run(async () => {
                  await put("/api/settings", { base_currency: e.target.value });
                  refs.reload(); missing.reload();
                  return `Reports are now shown in ${e.target.value}.`;
                })}>
                  {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                </select>
                <span className="muted small">Currencies in use: {s.currencies_in_use.join(", ") || "—"}</span>
              </div>
            </div>
            <div className="card">
              <h2>Demo data</h2>
              <p className="muted small">Synthetic accounts and ~14 months of random transactions to explore
                every screen. Demo items are labelled and can be removed at any time.</p>
              <div className="toolbar">
                <button onClick={() => run(async () => {
                  const r = await post<{ transactions: number }>("/api/demo"); refs.reload(); rates.reload(); rules.reload();
                  return `Demo data created (${r.transactions} transactions).`;
                })}>Load demo data</button>
                <button className="danger" onClick={() => setConfirm({ text: "Remove all demo accounts, transactions, goals, budgets and demo rates?",
                  run: async () => { await del("/api/demo"); refs.reload(); rates.reload(); setMsg({ kind: "success", text: "Demo data removed." }); } })}>
                  Remove demo data</button>
              </div>
            </div>
          </div>

          <div className="card table-wrap">
            <div className="page-head" style={{ marginBottom: 8 }}>
              <h2 style={{ margin: 0 }}>Exchange rates</h2>
              <div className="toolbar">
                <button disabled={busy === "fx"} onClick={() => run(async () => {
                  setBusy("fx");
                  try {
                    const r = await post<{ stored: number; currencies: string[]; missing: string[]; date: string | null }>(
                      "/api/fx-rates/fetch");
                    rates.reload(); missing.reload(); refs.reload();
                    return r.currencies.length
                      ? `Downloaded rates of ${r.date} for ${r.currencies.join(", ")} (${r.stored} new values incl. monthly history).`
                        + (r.missing.length ? ` Not available: ${r.missing.join(", ")}.` : "")
                      : "Only the reporting currency is in use; no rates needed.";
                  } finally { setBusy(null); }
                })}>{busy === "fx" ? "Downloading…" : "Update rates now"}</button>
                <button className="primary" onClick={() => setRateModal(true)}>+ Add rate</button>
              </div>
            </div>
            <label className="check" style={{ marginBottom: 8 }}>
              <input type="checkbox" checked={s.fx_auto_update} onChange={(e) => run(async () => {
                await put("/api/settings", { base_currency: s.base_currency, fx_auto_update: e.target.checked });
                refs.reload();
                return e.target.checked ? "Rates will be updated automatically once a day."
                  : "Automatic rate updates are off.";
              })} />
              Update automatically once a day (free Exchange API; only currency codes are sent)
              {s.fx_last_update && <span className="muted small"> · last update {date(s.fx_last_update)}</span>}
            </label>
            {!!missing.data?.missing.length && (
              <Banner kind="warning">Missing a rate to {s.base_currency} for: <b>{missing.data.missing.join(", ")}</b>.</Banner>)}
            <p className="small muted">Each transaction is converted with the latest rate on or before its date
              (inverse and cross rates are derived automatically). Enter rates from your bank or the SNB.</p>
            {rates.data?.length === 0 && <Empty>No rates yet.</Empty>}
            {!!rates.data?.length && (
              <table><thead><tr><th>Date</th><th>Pair</th><th className="num">Rate</th><th>Source</th><th /></tr></thead>
                <tbody>{rates.data.map((r) => (
                  <tr key={r.id}><td>{date(r.rate_date)}</td>
                    <td>1 {r.from_currency} = … {r.to_currency}</td>
                    <td className="num">{num(r.rate, 6)}</td><td className="muted">{r.source}</td>
                    <td className="num"><button className="link danger" onClick={async () => {
                      await del(`/api/fx-rates/${r.id}`); rates.reload(); missing.reload();
                    }}>Delete</button></td></tr>))}</tbody></table>)}
          </div>

          <div className="grid g2">
            <div className="card table-wrap">
              <div className="page-head" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Categories</h2>
                <button className="primary" onClick={() => setCatModal("new")}>+ Add</button>
              </div>
              <div style={{ maxHeight: 480, overflow: "auto" }}>
                <table><tbody>{cats.map((c) => (
                  <tr key={c.id}>
                    <td><span className="dot" style={{ display: "inline-block", marginRight: 8,
                      background: c.color ?? "var(--muted)" }} />{c.full_name}</td>
                    <td><span className={`badge ${c.kind === "income" ? "ok" : ""}`}>{c.kind}</span></td>
                    <td className="num"><button className="link" onClick={() => setCatModal(c)}>Edit</button>
                      <button className="link danger" onClick={() => setConfirm({
                        text: `Delete “${c.full_name}”? Its transactions become uncategorized.`,
                        run: async () => { await del(`/api/categories/${c.id}`); refs.reload(); } })}>Delete</button></td>
                  </tr>))}</tbody></table>
              </div>
            </div>
            <div className="card table-wrap">
              <div className="page-head" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Categorization rules</h2>
                <div className="toolbar">
                  <button onClick={() => run(async () => {
                    const r = await post<{ updated: number }>("/api/rules/apply");
                    return `${r.updated} uncategorized transactions were categorized.`;
                  })}>Apply to uncategorized</button>
                  <button className="primary" onClick={() => setRuleModal("new")}>+ Add</button>
                </div>
              </div>
              <p className="small muted">Imported transactions whose text contains the pattern get the category.
                Higher priority wins.</p>
              {rules.data?.length === 0 && <Empty>No rules yet. Example: “migros” → Groceries.</Empty>}
              {!!rules.data?.length && (
                <table><thead><tr><th>Pattern</th><th>Field</th><th>Category</th><th className="num">Prio</th><th /></tr></thead>
                  <tbody>{rules.data.map((r) => (
                    <tr key={r.id}><td><code>{r.pattern}</code>{r.is_regex && <span className="badge">regex</span>}</td>
                      <td>{r.match_field}</td><td>{catName(r.category_id)}</td><td className="num">{r.priority}</td>
                      <td className="num"><button className="link" onClick={() => setRuleModal(r)}>Edit</button>
                        <button className="link danger" onClick={async () => { await del(`/api/rules/${r.id}`); rules.reload(); }}>Delete</button></td>
                    </tr>))}</tbody></table>)}
            </div>
          </div>
          <div className="grid g2">
            <div className="card table-wrap">
              <div className="page-head" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Backups</h2>
                <div className="toolbar">
                  <label className="btn" style={{ display: "inline-flex", alignItems: "center" }}>
                    Restore from file…
                    <input type="file" accept=".dump" hidden onChange={async (e) => {
                      const f = e.target.files?.[0]; e.target.value = "";
                      if (!f) return;
                      const d = new FormData(); d.append("file", f);
                      try {
                        const up = await api<Backup>("/api/backups/upload", { method: "POST", body: d });
                        backups.reload();
                        setConfirm({ text: `Restore “${f.name}”? Your current data is backed up first, then replaced.`,
                          run: async () => {
                            const r = await post<{ safety_backup: string }>(`/api/backups/${up.name}/restore`);
                            refs.reload(); backups.reload();
                            setMsg({ kind: "success", text: `Restored. Previous data saved as ${r.safety_backup}.` });
                          } });
                      } catch (err) { setMsg({ kind: "error", text: (err as Error).message }); }
                    }} />
                  </label>
                  <button className="primary" disabled={busy === "bk" || !backups.data?.available} onClick={() => run(async () => {
                    setBusy("bk");
                    try { const b = await post<Backup>("/api/backups"); backups.reload(); return `Backup ${b.name} created.`; }
                    finally { setBusy(null); }
                  })}>{busy === "bk" ? "Backing up…" : "Back up now"}</button>
                </div>
              </div>
              <p className="small muted">A weekly automatic backup is made when the app starts (the newest 8 are kept).
                A safety backup is always made before a restore. Folder: <code>{backups.data?.folder}</code></p>
              {backups.data?.backups.length === 0 && <Empty>No backups yet.</Empty>}
              {!!backups.data?.backups.length && (
                <div style={{ maxHeight: 320, overflow: "auto" }}>
                  <table><thead><tr><th>Created</th><th>Kind</th><th className="num">Size</th><th /></tr></thead>
                    <tbody>{backups.data.backups.map((b) => (
                      <tr key={b.name}><td>{new Date(b.created).toLocaleString("de-CH")}</td>
                        <td><span className="badge">{b.kind}</span></td>
                        <td className="num">{b.size < 1048576 ? `${num(b.size / 1024, 0)} KB` : `${num(b.size / 1048576, 1)} MB`}</td>
                        <td className="num">
                          <a className="link" href={`/api/backups/${b.name}/download`} download>Download</a>
                          <button className="link danger" onClick={() => setConfirm({
                            text: `Restore the backup from ${new Date(b.created).toLocaleString("de-CH")}? Your current data is backed up first, then replaced.`,
                            run: async () => {
                              const r = await post<{ safety_backup: string }>(`/api/backups/${b.name}/restore`);
                              refs.reload(); backups.reload(); rates.reload(); rules.reload(); presets.reload();
                              setMsg({ kind: "success", text: `Restored. Previous data saved as ${r.safety_backup}.` });
                            } })}>Restore</button></td></tr>))}</tbody></table>
                </div>)}
            </div>
            <div className="card table-wrap">
              <h2>Import presets</h2>
              <p className="small muted">Saved column settings per bank file format. They are applied automatically
                when a file with the same columns is imported.</p>
              {presets.data?.length === 0 && <Empty>No presets yet. They are saved on the Import page.</Empty>}
              {!!presets.data?.length && (
                <table><tbody>{presets.data.map((p) => (
                  <tr key={p.id}><td>{p.name}</td><td className="num">
                    <button className="link danger" onClick={async () => {
                      await del(`/api/import/presets/${p.id}`); presets.reload();
                    }}>Delete</button></td></tr>))}</tbody></table>)}
            </div>
          </div>
          {info.data && (
            <div className="card small muted">
              PFI {info.data.version} · Database: {info.data.database} · Data folder: <code>{info.data.data_dir}</code>
              {" "}(back up this folder while the app is closed).
            </div>)}
        </div>)}

      {rateModal && (
        <FormModal title="Add exchange rate" onClose={() => setRateModal(false)}
          initial={{ rate_date: today(), from_currency: missing.data?.missing[0] ?? "EUR",
            to_currency: s?.base_currency ?? "CHF", rate: "" }}
          fields={[
            { name: "rate_date", label: "Valid from", type: "date", required: true },
            { name: "rate", label: "Rate", type: "number", step: "any", required: true,
              help: "How many units of the second currency one unit of the first buys." },
            { name: "from_currency", label: "1 unit of", type: "select", required: true,
              options: CURRENCIES.map((c) => ({ value: c, label: c })) },
            { name: "to_currency", label: "equals … of", type: "select", required: true,
              options: CURRENCIES.map((c) => ({ value: c, label: c })) },
          ]}
          onSubmit={async (v) => {
            await post("/api/fx-rates", { ...v, rate: String(v.rate) });
            rates.reload(); missing.reload(); refs.reload();
          }} />)}
      {catModal && (() => {
        const c = catModal === "new" ? null : catModal;
        return (
          <FormModal title={c ? `Edit ${c.name}` : "Add category"} onClose={() => setCatModal(null)}
            initial={c ? { name: c.name, kind: c.kind, parent_id: c.parent_id, color: c.color ?? "#0072B2" }
              : { name: "", kind: "expense", parent_id: "", color: "#0072B2" }}
            fields={[
              { name: "name", label: "Name", required: true },
              { name: "kind", label: "Kind", type: "select", required: true,
                options: [{ value: "expense", label: "Expense" }, { value: "income", label: "Income" }] },
              { name: "parent_id", label: "Parent (optional)", type: "select",
                options: cats.filter((x) => !x.parent_id && x.id !== c?.id).map((x) => ({ value: x.id, label: `${x.name} (${x.kind})` })) },
              { name: "color", label: "Colour", type: "text", placeholder: "#0072B2" },
            ]}
            onSubmit={async (v) => {
              const body = { name: v.name, kind: v.kind, parent_id: v.parent_id ? Number(v.parent_id) : null,
                color: v.color || null };
              if (c) await put(`/api/categories/${c.id}`, body); else await post("/api/categories", body);
              refs.reload();
            }} />);
      })()}
      {ruleModal && (() => {
        const r = ruleModal === "new" ? null : ruleModal;
        return (
          <FormModal title={r ? "Edit rule" : "Add rule"} onClose={() => setRuleModal(null)}
            initial={r ? { ...r } as never : { pattern: "", match_field: "any", is_regex: false, category_id: "", priority: 0 }}
            fields={[
              { name: "pattern", label: "Text contains", required: true },
              { name: "category_id", label: "Category", type: "select", required: true, options: categoryOptions(cats) },
              { name: "match_field", label: "Look in", type: "select", required: true, options: [
                { value: "any", label: "Description or payee" }, { value: "description", label: "Description" },
                { value: "merchant", label: "Payee" }] },
              { name: "priority", label: "Priority", type: "number" },
              { name: "is_regex", label: "Pattern is a regular expression", type: "checkbox", full: true },
            ]}
            onSubmit={async (v) => {
              const body = { ...v, category_id: Number(v.category_id), priority: Number(v.priority || 0) };
              if (r) await put(`/api/rules/${r.id}`, body); else await post("/api/rules", body);
              rules.reload();
            }} />);
      })()}
      {confirm && <Confirm text={confirm.text} onYes={confirm.run} onClose={() => setConfirm(null)} />}
    </>
  );
}
