"use client";
// First-run setup: language and currency, accounts, a starter budget, then
// where the history comes from. Shown once, on an empty database.
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button, Checkbox, Field, Input, Select } from "@fluentui/react-components";
import { Add20Regular, Delete20Regular } from "@fluentui/react-icons";
import { I } from "./icons";
import { Category, get, post, put } from "@/lib/api";
import { CURRENCIES, money, today } from "@/lib/format";
import { LANGS, Lang, useT } from "@/lib/i18n";

/** Share of take-home pay suggested per category (adds up to 80 %, the
 *  rest is left for savings). */
const STARTER: [string, number][] = [
  ["Housing", 0.30], ["Food", 0.12], ["Transport", 0.10], ["Health", 0.05],
  ["Shopping", 0.06], ["Leisure", 0.07], ["Finance", 0.03], ["Family & Gifts", 0.02],
  ["Education", 0.02], ["Other Expense", 0.03],
];
const TYPES = ["checking", "savings", "cash", "credit_card", "investment", "loan"];
const TYPE_LABEL: Record<string, string> = {
  checking: "Checking", savings: "Savings", cash: "Cash", credit_card: "Credit card",
  investment: "Investment", loan: "Loan",
};

type Row = { name: string; type: string; balance: string };

export function SetupAssistant({ base, lang, onLang, onDone }: {
  base: string; lang: Lang; onLang: (l: Lang) => void; onDone: () => void;
}) {
  const t = useT();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [currency, setCurrency] = useState(base || "USD");
  const [rows, setRows] = useState<Row[]>([{ name: t("Main account"), type: "checking", balance: "" }]);
  const [income, setIncome] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set(STARTER.map(([n]) => n)));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const pay = Number(income.replace(",", ".")) || 0;
  const plan = useMemo(() => STARTER.map(([n, share]) => [n, Math.round(pay * share)] as [string, number]), [pay]);

  const finish = async (go?: string) => {
    await put("/api/settings", { setup_done: true });
    onDone();
    if (go) router.push(go);
    else window.location.reload();
  };
  const saveCurrency = async () => {
    setBusy(true); setErr(null);
    try { await put("/api/settings", { base_currency: currency, language: lang }); setStep(1); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const saveAccounts = async () => {
    setBusy(true); setErr(null);
    try {
      for (const r of rows.filter((x) => x.name.trim())) {
        await post("/api/accounts", {
          name: r.name.trim(), type: r.type, currency, opening_date: today(),
          opening_balance: String(Number(r.balance.replace(",", ".")) || 0),
        });
      }
      setStep(2);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const saveBudget = async () => {
    setBusy(true); setErr(null);
    try {
      if (pay > 0) {
        const cats = await get<Category[]>("/api/categories");
        for (const [name, amount] of plan) {
          const c = cats.find((x) => x.name === name && x.kind === "expense" && !x.parent_id);
          if (c && amount > 0 && picked.has(name)) {
            await post("/api/budgets", { category_id: c.id, monthly_amount: String(amount) });
          }
        }
      }
      setStep(3);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const steps = [t("Welcome"), t("Accounts"), t("Budget"), t("History")];
  return (
    <div className="setup" role="dialog" aria-modal="true" aria-labelledby="setup-title">
      <div className="setup-card">
        <div className="setup-shape" aria-hidden />
        <ol className="setup-steps" aria-label={t("Steps")}>
          {steps.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined}
              className={i < step ? "done" : undefined}>{s}</li>))}
        </ol>
        {step === 0 && (<>
          <span className="icon setup-icon" aria-hidden>{I.wavingHand}</span>
          <h1 id="setup-title">{t("Welcome to Personal Finance")}</h1>
          <p className="caption">{t("Four quick steps and your money has a home. Everything stays on this PC; there is no account to create.")}</p>
          <div className="form-grid">
            <Field label={t("Language")}>
              <Select value={lang} onChange={(_, d) => onLang(d.value as Lang)}>
                {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </Select>
            </Field>
            <Field label={t("Main currency")} hint={t("Totals and reports use it; accounts can be in any currency.")}>
              <Select value={currency} onChange={(_, d) => setCurrency(d.value)}>
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Field>
          </div>
          <div className="setup-actions">
            <Button appearance="primary" size="large" disabled={busy} onClick={saveCurrency}>{t("Start")}</Button>
            <Button appearance="subtle" onClick={() => finish("/settings/#sync")}>
              {t("I already use Personal Finance on another device")}</Button>
          </div>
        </>)}
        {step === 1 && (<>
          <span className="icon setup-icon" aria-hidden>{I.accountBalance}</span>
          <h1 id="setup-title">{t("Where is your money?")}</h1>
          <p className="caption">{t("Add the accounts you use: bank accounts, cash, cards and loans. You can add more later.")}</p>
          {rows.map((r, i) => (
            <div key={i} className="setup-row">
              <Input aria-label={t("Name")} value={r.name} placeholder={t("Name")}
                onChange={(_, d) => setRows(rows.map((x, j) => j === i ? { ...x, name: d.value } : x))} />
              <Select aria-label={t("Type")} value={r.type}
                onChange={(_, d) => setRows(rows.map((x, j) => j === i ? { ...x, type: d.value } : x))}>
                {TYPES.map((ty) => <option key={ty} value={ty}>{t(TYPE_LABEL[ty])}</option>)}
              </Select>
              <Input aria-label={t("Balance today")} value={r.balance} inputMode="decimal"
                placeholder={t("Balance today")} contentAfter={currency}
                onChange={(_, d) => setRows(rows.map((x, j) => j === i ? { ...x, balance: d.value } : x))} />
              <Button appearance="subtle" icon={<Delete20Regular />} aria-label={t("Remove")}
                disabled={rows.length === 1} onClick={() => setRows(rows.filter((_, j) => j !== i))} />
            </div>))}
          <Button appearance="subtle" icon={<Add20Regular />}
            onClick={() => setRows([...rows, { name: "", type: "savings", balance: "" }])}>{t("Add another")}</Button>
          <div className="setup-actions">
            <Button appearance="primary" size="large" disabled={busy || !rows.some((r) => r.name.trim())}
              onClick={saveAccounts}>{t("Next")}</Button>
            <Button appearance="subtle" onClick={() => setStep(2)}>{t("Skip")}</Button>
          </div>
        </>)}
        {step === 2 && (<>
          <span className="icon setup-icon" aria-hidden>{I.accountBalanceWallet}</span>
          <h1 id="setup-title">{t("A starter budget")}</h1>
          <p className="caption">{t("Enter what you earn per month after tax. Personal Finance suggests a monthly limit per category and leaves 20 % for savings. Untick anything you don't need; you can change every amount later.")}</p>
          <Field label={t("Monthly take-home pay")}>
            <Input value={income} inputMode="decimal" contentAfter={currency}
              onChange={(_, d) => setIncome(d.value)} />
          </Field>
          {pay > 0 && (
            <ul className="setup-plan">
              {plan.map(([n, a]) => (
                <li key={n}>
                  <Checkbox checked={picked.has(n)} label={t(n)} onChange={(_, d) => {
                    const s = new Set(picked); if (d.checked) s.add(n); else s.delete(n); setPicked(s);
                  }} />
                  <span className="num">{money(a, currency, 0)}</span>
                </li>))}
              <li className="setup-save"><span>{t("Left for savings")}</span>
                <span className="num">{money(pay - plan.filter(([n]) => picked.has(n)).reduce((x, [, a]) => x + a, 0), currency, 0)}</span></li>
            </ul>)}
          <div className="setup-actions">
            <Button appearance="primary" size="large" disabled={busy} onClick={saveBudget}>{pay > 0 ? t("Create budget") : t("Next")}</Button>
            <Button appearance="subtle" onClick={() => setStep(3)}>{t("Skip")}</Button>
          </div>
        </>)}
        {step === 3 && (<>
          <span className="icon setup-icon" aria-hidden>{I.celebration}</span>
          <h1 id="setup-title">{t("Bring in your history")}</h1>
          <p className="caption">{t("Import a statement from your bank's website (CSV, OFX, QIF, camt.053) or connect your bank. You can also just start adding transactions.")}</p>
          <div className="setup-choices">
            <button type="button" className="setup-choice" onClick={() => finish("/import/")}>
              <span className="icon" aria-hidden>{I.uploadFile}</span><b>{t("Import a statement")}</b>
              <span className="caption">{t("From a file you download from your bank")}</span></button>
            <button type="button" className="setup-choice" onClick={() => finish("/settings/#bank-sync")}>
              <span className="icon" aria-hidden>{I.syncAlt}</span><b>{t("Connect my bank")}</b>
              <span className="caption">{t("SimpleFIN (US, Canada) or Enable Banking (Europe)")}</span></button>
            <button type="button" className="setup-choice" onClick={() => finish()}>
              <span className="icon" aria-hidden>{I.add}</span><b>{t("Start fresh")}</b>
              <span className="caption">{t("Add transactions as you go with Ctrl+N")}</span></button>
          </div>
        </>)}
        {err && <p className="setup-error" role="alert">{err}</p>}
      </div>
    </div>
  );
}
