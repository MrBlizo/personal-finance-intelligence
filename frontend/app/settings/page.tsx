"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Badge, Button, Select, Switch, Tooltip,
} from "@fluentui/react-components";
import {
  Add20Regular, ArrowDownload20Regular, ArrowSync20Regular, Delete20Regular,
  Edit20Regular, LockClosed20Regular,
} from "@fluentui/react-icons";
import { usePrefs } from "@/components/AppFrame";
import { catLabel, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, PageHead, SettingRow, Spinner, useLoad,
} from "@/components/ui";
import {
  Backup, Category, FxRate, LearnStatus, Rule, Settings, api, del, downloadUrl,
  get, post, put,
} from "@/lib/api";
import { CURRENCIES, date, num, pct, today } from "@/lib/format";
import { LANGS, Lang, useT } from "@/lib/i18n";
import { inShell, notifyLockSettings, queryHello, requestLock } from "@/lib/shell";

type Info = { version: string; data_dir: string; database: string };

export default function SettingsPage() {
  const t = useT();
  const { setLang } = usePrefs();
  const refs = useRefs();
  const rates = useLoad(() => get<FxRate[]>("/api/fx-rates"));
  const missing = useLoad(() => get<{ missing: string[] }>("/api/fx-rates/missing"));
  const rules = useLoad(() => get<Rule[]>("/api/rules"));
  const info = useLoad(() => get<Info>("/api/info"));
  const learn = useLoad(() => get<LearnStatus>("/api/learn/status"));
  const presets = useLoad(() => get<{ id: number; name: string }[]>("/api/import/presets"));
  const backups = useLoad(() => get<{ folder: string; available: boolean; backups: Backup[] }>("/api/backups"));
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error" | "warning"; text: string } | null>(null);
  const [rateModal, setRateModal] = useState(false);
  const [showRates, setShowRates] = useState(false);
  const [catModal, setCatModal] = useState<Category | "new" | null>(null);
  const [ruleModal, setRuleModal] = useState<Rule | "new" | null>(null);
  const [confirm, setConfirm] = useState<{ text: string; run: () => Promise<void>; danger?: boolean } | null>(null);
  const [hello, setHello] = useState<boolean | null>(null);
  const restoreInput = useRef<HTMLInputElement>(null);
  useEffect(() => { queryHello().then(setHello); }, []);
  const s = refs.data?.settings;
  const cats = refs.data?.categories ?? [];
  const catName = (id: number) => catLabel(cats.find((c) => c.id === id)?.full_name, t) || `#${id}`;
  const run = async (f: () => Promise<string>) => {
    try { setMsg({ kind: "success", text: await f() }); }
    catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  };
  const save = async (body: Partial<Settings>) => {
    const out = await put<Settings>("/api/settings", body);
    refs.reload();
    return out;
  };
  const shell = typeof window !== "undefined" && inShell();

  return (
    <>
      <PageHead title={t("Settings")} />
      {msg && <Banner kind={msg.kind} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {!s && <Spinner />}
      {s && (
        <div style={{ maxWidth: 1000 }}>
          <div className="group-title">{t("General")}</div>
          <div className="settings-group">
            <SettingRow icon={""} title={t("Language")}
              description={t("Language of the app and the monthly PDF report (Arabic reports are generated in English).")}>
              <Select value={s.language} onChange={(_, d) => run(async () => {
                await save({ language: d.value as Lang });
                setLang(d.value as Lang);
                return t("Language changed.");
              })}>
                {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </Select>
            </SettingRow>
            <SettingRow icon={""} title={t("Reporting currency")}
              description={t("Currencies in use: {list}", { list: s.currencies_in_use.join(", ") || "—" })}>
              <Select value={s.base_currency} onChange={(_, d) => run(async () => {
                await save({ base_currency: d.value }); missing.reload();
                return t("Reports are now shown in {cur}.", { cur: d.value });
              })}>
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </SettingRow>
          </div>

          <div className="group-title">{t("Privacy & security")}</div>
          <div className="settings-group">
            <SettingRow icon={""} title={t("App lock with Windows Hello")}
              description={!shell ? t("Only available in the desktop app.")
                : hello === false ? t("Windows Hello is not set up on this PC. Set up a PIN, fingerprint or face in Windows Settings › Accounts › Sign-in options.")
                : t("Ask for your face, fingerprint or Windows PIN when PFI opens and after it has been idle.")}>
              {s.app_lock === "hello" && shell && (
                <Button icon={<LockClosed20Regular />} onClick={() => requestLock()}>{t("Lock now")}</Button>)}
              <Switch checked={s.app_lock === "hello"} disabled={!shell || hello === false}
                onChange={(_, d) => run(async () => {
                  const mode = d.checked ? "hello" : "off";
                  const out = await save({ app_lock: mode });
                  notifyLockSettings(mode, out.lock_after_minutes);
                  return d.checked ? t("App lock is on.") : t("App lock is off.");
                })} />
            </SettingRow>
            {s.app_lock === "hello" && (
              <SettingRow title={t("Lock after inactivity")}
                description={t("Also locks when the window is minimised for this long.")}>
                <Select value={String(s.lock_after_minutes)} onChange={(_, d) => run(async () => {
                  const out = await save({ lock_after_minutes: Number(d.value) });
                  notifyLockSettings(out.app_lock, out.lock_after_minutes);
                  return t("Saved.");
                })}>
                  {[1, 5, 15, 30, 60, 0].map((m) => (
                    <option key={m} value={m}>{m === 0 ? t("Only when the app starts")
                      : t("{n} minutes", { n: m })}</option>))}
                </Select>
              </SettingRow>)}
            <div className="caption" style={{ padding: "4px 16px" }}>
              {t("The lock protects the app window. Your data stays on this PC; to encrypt the disk use BitLocker or Device encryption.")}</div>
          </div>

          <div className="group-title">{t("Smart categories")}</div>
          <div className="settings-group">
            <SettingRow icon={""} title={t("Categorise imports automatically")}
              description={t("Uses what PFI learned from the transactions you categorised yourself. Rules always come first.")}>
              <Switch checked={s.auto_categorize} onChange={(_, d) => run(async () => {
                await save({ auto_categorize: d.checked });
                return d.checked ? t("Automatic categorisation is on.") : t("Automatic categorisation is off.");
              })} />
            </SettingRow>
            <SettingRow title={t("Minimum confidence")}
              description={t("Suggestions below this are left for you to review.")}>
              <Select value={String(s.auto_categorize_threshold)} onChange={(_, d) => run(async () => {
                await save({ auto_categorize_threshold: Number(d.value) }); learn.reload();
                return t("Saved.");
              })}>
                {[0.6, 0.7, 0.8, 0.9, 0.95].map((x) => <option key={x} value={x}>{pct(x, 0)}</option>)}
              </Select>
            </SettingRow>
            <SettingRow title={t("How well it works on your data")}
              description={learn.data?.accuracy == null
                ? t("Needs at least {n} categorised transactions in 2+ categories ({have} so far).",
                  { n: learn.data?.min_examples ?? 20, have: learn.data?.examples ?? 0 })
                : t("Trained on your older {a} transactions and tested on the newest {b}: {acc} correct (always guessing the most common category: {base}). At {thr} confidence it decides {cov} of them, {acc2} correctly.", {
                  a: learn.data.n_train, b: learn.data.n_test, acc: pct(learn.data.accuracy, 0),
                  base: pct(learn.data.baseline, 0), thr: pct(learn.data.threshold, 0),
                  cov: pct(learn.data.coverage_at_threshold, 0),
                  acc2: pct(learn.data.accuracy_at_threshold, 0) })}>
              <Link href="/transactions/?uncategorized=1"><Button>{t("Review uncategorised")}</Button></Link>
            </SettingRow>
          </div>

          <div className="group-title">{t("Exchange rates & prices")}</div>
          <div className="settings-group">
            <SettingRow icon={""} title={t("Update exchange rates automatically")}
              description={(s.fx_last_update ? t("Last update {d}.", { d: date(s.fx_last_update) }) + " " : "")
                + t("Free Exchange API, once a day; only currency codes are sent.")}>
              <Button icon={<ArrowSync20Regular />} disabled={busy === "fx"} onClick={() => run(async () => {
                setBusy("fx");
                try {
                  const r = await post<{ stored: number; currencies: string[]; missing: string[]; date: string | null }>(
                    "/api/fx-rates/fetch");
                  rates.reload(); missing.reload(); refs.reload();
                  return r.currencies.length
                    ? t("Downloaded rates of {d} for {list} ({n} new values incl. monthly history).",
                      { d: r.date ?? "", list: r.currencies.join(", "), n: r.stored })
                      + (r.missing.length ? " " + t("Not available: {list}.", { list: r.missing.join(", ") }) : "")
                    : t("Only the reporting currency is in use; no rates needed.");
                } finally { setBusy(null); }
              })}>{busy === "fx" ? t("Downloading…") : t("Update now")}</Button>
              <Switch checked={s.fx_auto_update} onChange={(_, d) => run(async () => {
                await save({ fx_auto_update: d.checked });
                return d.checked ? t("Rates will be updated automatically once a day.")
                  : t("Automatic rate updates are off.");
              })} />
            </SettingRow>
            {!!missing.data?.missing.length && (
              <Banner kind="warning">{t("Missing a rate to {cur} for: {list}.",
                { cur: s.base_currency, list: missing.data.missing.join(", ") })}</Banner>)}
            <SettingRow title={t("Exchange-rate table")}
              description={t("Each transaction uses the latest rate on or before its date; inverse and cross rates are derived automatically.")}>
              <Button icon={<Add20Regular />} onClick={() => setRateModal(true)}>{t("Add rate")}</Button>
              <Button appearance="subtle" onClick={() => setShowRates(!showRates)}>
                {showRates ? t("Hide") : t("Show ({n})", { n: rates.data?.length ?? 0 })}</Button>
            </SettingRow>
            {showRates && (
              <div className="setting-body table-wrap" style={{ maxHeight: 320 }}>
                {rates.data?.length === 0 && <Empty>{t("No rates yet.")}</Empty>}
                {!!rates.data?.length && (
                  <table><thead><tr><th>{t("Date")}</th><th>{t("Pair")}</th><th className="num">{t("Rate")}</th>
                    <th>{t("Source")}</th><th /></tr></thead>
                    <tbody>{rates.data.map((r) => (
                      <tr key={r.id}><td>{date(r.rate_date)}</td>
                        <td>1 {r.from_currency} = … {r.to_currency}</td>
                        <td className="num">{num(r.rate, 6)}</td><td className="muted">{r.source}</td>
                        <td className="actions"><Button appearance="subtle" size="small" icon={<Delete20Regular />}
                          aria-label={t("Delete")} onClick={async () => {
                            await del(`/api/fx-rates/${r.id}`); rates.reload(); missing.reload();
                          }} /></td></tr>))}</tbody></table>)}
              </div>)}
            <SettingRow icon={""} title={t("Update investment prices automatically")}
              description={(s.price_last_update ? t("Last update {d}.", { d: date(s.price_last_update) }) + " " : "")
                + t("Once a day for holdings with stooq or CoinGecko as price source; only the symbol is sent.")}>
              <Switch checked={s.price_auto_update} onChange={(_, d) => run(async () => {
                await save({ price_auto_update: d.checked });
                return t("Saved.");
              })} />
            </SettingRow>
          </div>

          <div className="group-title">{t("Categories & rules")}</div>
          <div className="grid g2">
            <section className="card section">
              <div className="section-head">
                <h2>{t("Categories")}</h2>
                <Button size="small" icon={<Add20Regular />} onClick={() => setCatModal("new")}>{t("Add")}</Button>
              </div>
              <div className="table-wrap" style={{ maxHeight: 420 }}>
                <table><tbody>{cats.map((c) => (
                  <tr key={c.id}>
                    <td><span className="dot" style={{ background: c.color ?? "var(--text-3)" }} />
                      {catLabel(c.full_name, t)}</td>
                    <td><Badge appearance="tint" color={c.kind === "income" ? "success" : "informative"}>
                      {t(c.kind === "income" ? "Income" : "Expense")}</Badge></td>
                    <td className="actions">
                      <Button appearance="subtle" size="small" icon={<Edit20Regular />} aria-label={t("Edit")}
                        onClick={() => setCatModal(c)} />
                      <Button appearance="subtle" size="small" icon={<Delete20Regular />} aria-label={t("Delete")}
                        onClick={() => setConfirm({ danger: true,
                          text: t("Delete “{c}”? Its transactions become uncategorised.", { c: catLabel(c.full_name, t) }),
                          run: async () => { await del(`/api/categories/${c.id}`); refs.reload(); } })} />
                    </td>
                  </tr>))}</tbody></table>
              </div>
            </section>
            <section className="card section">
              <div className="section-head">
                <div><h2>{t("Categorisation rules")}</h2>
                  <div className="caption">{t("Text that appears in a description or payee gets the category. Higher priority wins.")}</div></div>
                <div className="commands">
                  <Button size="small" onClick={() => run(async () => {
                    const r = await post<{ updated: number }>("/api/rules/apply");
                    return t("{n} uncategorised transactions were categorised.", { n: r.updated });
                  })}>{t("Apply to uncategorised")}</Button>
                  <Button size="small" icon={<Add20Regular />} onClick={() => setRuleModal("new")}>{t("Add")}</Button>
                </div>
              </div>
              {rules.data?.length === 0 && <Empty>{t("No rules yet. Example: “migros” → Groceries.")}</Empty>}
              {!!rules.data?.length && (
                <div className="table-wrap"><table><thead><tr><th>{t("Pattern")}</th><th>{t("Category")}</th>
                  <th className="num">{t("Priority")}</th><th /></tr></thead>
                  <tbody>{rules.data.map((r) => (
                    <tr key={r.id}><td><code>{r.pattern}</code>{" "}
                      {r.is_regex && <Badge appearance="outline" size="small">regex</Badge>}</td>
                      <td>{catName(r.category_id)}</td><td className="num">{r.priority}</td>
                      <td className="actions">
                        <Button appearance="subtle" size="small" icon={<Edit20Regular />} aria-label={t("Edit")}
                          onClick={() => setRuleModal(r)} />
                        <Button appearance="subtle" size="small" icon={<Delete20Regular />} aria-label={t("Delete")}
                          onClick={async () => { await del(`/api/rules/${r.id}`); rules.reload(); }} /></td>
                    </tr>))}</tbody></table></div>)}
            </section>
          </div>

          <div className="group-title">{t("Backup & data")}</div>
          <div className="settings-group">
            <SettingRow icon={""} title={t("Backups")}
              description={t("A weekly automatic backup is made when the app starts (the newest 8 are kept). A safety backup is always made before a restore.")}>
              <input ref={restoreInput} type="file" accept=".dump" hidden onChange={async (e) => {
                const f = e.target.files?.[0]; e.target.value = "";
                if (!f) return;
                const d = new FormData(); d.append("file", f);
                try {
                  const up = await api<Backup>("/api/backups/upload", { method: "POST", body: d });
                  backups.reload();
                  setConfirm({ danger: true, text: t("Restore “{f}”? Your current data is backed up first, then replaced.", { f: f.name }),
                    run: async () => {
                      const r = await post<{ safety_backup: string }>(`/api/backups/${up.name}/restore`);
                      refs.reload(); backups.reload();
                      setMsg({ kind: "success", text: t("Restored. Previous data saved as {n}.", { n: r.safety_backup }) });
                    } });
                } catch (err) { setMsg({ kind: "error", text: (err as Error).message }); }
              }} />
              <Button onClick={() => restoreInput.current?.click()}>{t("Restore from file…")}</Button>
              <Button appearance="primary" disabled={busy === "bk" || !backups.data?.available} onClick={() => run(async () => {
                setBusy("bk");
                try { const b = await post<Backup>("/api/backups"); backups.reload(); return t("Backup {n} created.", { n: b.name }); }
                finally { setBusy(null); }
              })}>{busy === "bk" ? t("Backing up…") : t("Back up now")}</Button>
            </SettingRow>
            <div className="setting-body table-wrap" style={{ maxHeight: 280 }}>
              <div className="caption" style={{ marginBottom: 8 }}>{t("Folder:")} <code>{backups.data?.folder}</code></div>
              {backups.data?.backups.length === 0 && <Empty>{t("No backups yet.")}</Empty>}
              {!!backups.data?.backups.length && (
                <table><thead><tr><th>{t("Created")}</th><th>{t("Kind")}</th><th className="num">{t("Size")}</th><th /></tr></thead>
                  <tbody>{backups.data.backups.map((b) => (
                    <tr key={b.name}><td>{new Date(b.created).toLocaleString("de-CH")}</td>
                      <td><Badge appearance="tint">{t(b.kind)}</Badge></td>
                      <td className="num">{b.size < 1048576 ? `${num(b.size / 1024, 0)} KB` : `${num(b.size / 1048576, 1)} MB`}</td>
                      <td className="actions">
                        <Tooltip content={t("Download")} relationship="label">
                          <Button appearance="subtle" size="small" icon={<ArrowDownload20Regular />} as="a"
                            href={downloadUrl(`/api/backups/${b.name}/download`)} /></Tooltip>
                        <Button appearance="subtle" size="small" onClick={() => setConfirm({ danger: true,
                          text: t("Restore the backup from {d}? Your current data is backed up first, then replaced.",
                            { d: new Date(b.created).toLocaleString("de-CH") }),
                          run: async () => {
                            const r = await post<{ safety_backup: string }>(`/api/backups/${b.name}/restore`);
                            refs.reload(); backups.reload(); rates.reload(); rules.reload(); presets.reload();
                            setMsg({ kind: "success", text: t("Restored. Previous data saved as {n}.", { n: r.safety_backup }) });
                          } })}>{t("Restore")}</Button></td></tr>))}</tbody></table>)}
            </div>
            <SettingRow icon={""} title={t("Import presets")}
              description={t("Saved column settings per bank file format, applied automatically to files with the same columns.")}>
              {presets.data?.length === 0 && <span className="caption">{t("None yet")}</span>}
            </SettingRow>
            {!!presets.data?.length && (
              <div className="setting-body">
                {presets.data.map((p) => (
                  <div className="list-row" key={p.id}><span className="grow">{p.name}</span>
                    <Button appearance="subtle" size="small" icon={<Delete20Regular />} aria-label={t("Delete")}
                      onClick={async () => { await del(`/api/import/presets/${p.id}`); presets.reload(); }} /></div>))}
              </div>)}
            <SettingRow icon={""} title={t("Export everything")}
              description={t("All transactions, accounts, holdings and monthly summaries as an Excel workbook.")}>
              <Button icon={<ArrowDownload20Regular />} as="a" href={downloadUrl("/api/export/workbook.xlsx")}>
                {t("Excel workbook")}</Button>
            </SettingRow>
            <SettingRow icon={""} title={t("Demo data")}
              description={t("Synthetic accounts and about 14 months of random transactions to explore every screen. Demo items are labelled and can be removed at any time.")}>
              <Button onClick={() => run(async () => {
                const r = await post<{ transactions: number }>("/api/demo"); refs.reload(); rates.reload(); rules.reload();
                return t("Demo data created ({n} transactions).", { n: r.transactions });
              })}>{t("Load")}</Button>
              <Button onClick={() => setConfirm({ danger: true,
                text: t("Remove all demo accounts, transactions, goals, budgets and demo rates?"),
                run: async () => { await del("/api/demo"); refs.reload(); rates.reload();
                  setMsg({ kind: "success", text: t("Demo data removed.") }); } })}>{t("Remove")}</Button>
            </SettingRow>
          </div>

          {info.data && (
            <>
              <div className="group-title">{t("About")}</div>
              <SettingRow icon={""} title={`Personal Finance Intelligence ${info.data.version}`}
                description={<>{t("Database: {d}", { d: info.data.database })} · {t("Data folder:")}{" "}
                  <code>{info.data.data_dir}</code></>}>
                <a className="link" href="https://github.com/MrBlizo/personal-finance-intelligence"
                  target="_blank" rel="noreferrer">GitHub</a>
              </SettingRow>
            </>)}
        </div>)}

      {rateModal && (
        <FormModal title={t("Add exchange rate")} onClose={() => setRateModal(false)}
          initial={{ rate_date: today(), from_currency: missing.data?.missing[0] ?? "EUR",
            to_currency: s?.base_currency ?? "CHF", rate: "" }}
          fields={[
            { name: "rate_date", label: t("Valid from"), type: "date", required: true },
            { name: "rate", label: t("Rate"), type: "number", step: "any", required: true,
              help: t("How many units of the second currency one unit of the first buys.") },
            { name: "from_currency", label: t("1 unit of"), type: "select", required: true,
              options: CURRENCIES.map((c) => ({ value: c, label: c })) },
            { name: "to_currency", label: t("equals … of"), type: "select", required: true,
              options: CURRENCIES.map((c) => ({ value: c, label: c })) },
          ]}
          onSubmit={async (v) => {
            await post("/api/fx-rates", { ...v, rate: String(v.rate) });
            rates.reload(); missing.reload(); refs.reload();
          }} />)}
      {catModal && (() => {
        const c = catModal === "new" ? null : catModal;
        return (
          <FormModal title={c ? t("Edit {name}", { name: catLabel(c.name, t) }) : t("Add category")}
            onClose={() => setCatModal(null)}
            initial={c ? { name: c.name, kind: c.kind, parent_id: c.parent_id, color: c.color ?? "#0072B2" }
              : { name: "", kind: "expense", parent_id: "", color: "#0072B2" }}
            fields={[
              { name: "name", label: t("Name"), required: true },
              { name: "kind", label: t("Kind"), type: "select", required: true,
                options: [{ value: "expense", label: t("Expense") }, { value: "income", label: t("Income") }] },
              { name: "parent_id", label: t("Parent (optional)"), type: "select",
                options: cats.filter((x) => !x.parent_id && x.id !== c?.id)
                  .map((x) => ({ value: x.id, label: `${t(x.name)} (${t(x.kind === "income" ? "Income" : "Expense")})` })) },
              { name: "color", label: t("Colour"), type: "text", placeholder: "#0072B2" },
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
          <FormModal title={r ? t("Edit rule") : t("Add rule")} onClose={() => setRuleModal(null)}
            initial={r ? { ...r } as never : { pattern: "", match_field: "any", is_regex: false, category_id: "", priority: 0 }}
            fields={[
              { name: "pattern", label: t("Text contains"), required: true },
              { name: "category_id", label: t("Category"), type: "select", required: true,
                options: categoryOptions(cats, undefined, t) },
              { name: "match_field", label: t("Look in"), type: "select", required: true, options: [
                { value: "any", label: t("Description or payee") }, { value: "description", label: t("Description") },
                { value: "merchant", label: t("Payee") }] },
              { name: "priority", label: t("Priority"), type: "number" },
              { name: "is_regex", label: t("Pattern is a regular expression"), type: "switch", full: true },
            ]}
            onSubmit={async (v) => {
              const body = { ...v, category_id: Number(v.category_id), priority: Number(v.priority || 0) };
              if (r) await put(`/api/rules/${r.id}`, body); else await post("/api/rules", body);
              rules.reload();
            }} />);
      })()}
      {confirm && <Confirm danger={confirm.danger} text={confirm.text} onYes={confirm.run}
        onClose={() => setConfirm(null)} />}
    </>
  );
}
