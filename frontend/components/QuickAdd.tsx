"use client";
// Quick add: a transaction in a few keystrokes, from any page (Ctrl+N).
// The payee remembers its last category, amounts accept sums (12.50+3),
// and the last account used is pre-selected.
import { useEffect, useRef, useState } from "react";
import {
  Button, Combobox, Field, Input, Option, Select, Tab, TabList,
} from "@fluentui/react-components";
import { CategoryIcon } from "./CategoryIcon";
import { accountOptions, catLabel, categoryOptions, useRefs } from "./refs";
import { Banner, Modal } from "./ui";
import { PayeeHint, get, post } from "@/lib/api";
import { evalAmount, isFormula } from "@/lib/calc";
import { money, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

const LAST_ACCOUNT = "pfi.quickadd.account";
const remember = (id: string) => { try { localStorage.setItem(LAST_ACCOUNT, id); } catch { /* private mode */ } };
const recall = () => { try { return localStorage.getItem(LAST_ACCOUNT) ?? ""; } catch { return ""; } };

export function QuickAdd({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const t = useT();
  const refs = useRefs();
  const accounts = refs.data?.accounts ?? [];
  const cats = refs.data?.categories ?? [];
  const [type, setType] = useState<"expense" | "income">("expense");
  const [amount, setAmount] = useState("");
  const [payee, setPayee] = useState("");
  const [hints, setHints] = useState<PayeeHint[]>([]);
  const [category, setCategory] = useState("");
  const [account, setAccount] = useState("");
  const [day, setDay] = useState(today());
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const touchedCat = useRef(false);
  const amountRef = useRef<HTMLInputElement>(null);

  useEffect(() => { amountRef.current?.focus(); }, []);
  useEffect(() => {
    if (account || !accounts.length) return;
    const last = recall();
    const open = accounts.filter((a) => !a.is_archived);
    setAccount(open.some((a) => String(a.id) === last) ? last : String(open[0]?.id ?? ""));
  }, [accounts, account]);
  useEffect(() => {
    const h = setTimeout(() => {
      get<PayeeHint[]>("/api/payees", { q: payee, limit: 8 }).then(setHints).catch(() => {});
    }, 150);
    return () => clearTimeout(h);
  }, [payee]);

  const pickPayee = (name: string) => {
    setPayee(name);
    const hit = hints.find((h) => h.payee.toLowerCase() === name.toLowerCase());
    if (hit?.category_id && !touchedCat.current) {
      const cat = cats.find((c) => c.id === hit.category_id);
      if (cat) {
        setCategory(String(cat.id));
        setType(cat.kind === "income" ? "income" : "expense");
      }
    }
  };
  const value = evalAmount(amount);
  const cat = cats.find((c) => String(c.id) === category);

  const save = async (again: boolean) => {
    if (value === null || value <= 0) { setError(t("Enter an amount above 0, for example 12.50 or 10+2.50.")); return; }
    if (!account) { setError(t("Choose an account.")); return; }
    setBusy(true);
    setError(null);
    try {
      await post("/api/transactions", {
        account_id: Number(account), txn_date: day,
        amount: String(type === "expense" ? -value : value), kind: type,
        category_id: category ? Number(category) : null,
        description: payee, merchant: payee || null, notes: note || null,
      });
      remember(account);
      onSaved?.();
      if (again) {
        setAmount(""); setPayee(""); setCategory(""); setNote("");
        touchedCat.current = false;
        amountRef.current?.focus();
      } else onClose();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={t("Quick add")} onClose={onClose} actions={<>
      <Button appearance="primary" disabled={busy} onClick={() => save(false)}>{t("Save")}</Button>
      <Button disabled={busy} onClick={() => save(true)}>{t("Save and add another")}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); save(false); }}>
        <TabList className="full" selectedValue={type}
          onTabSelect={(_, d) => { setType(d.value as "expense" | "income"); setCategory(""); }}>
          <Tab value="expense">{t("Expense")}</Tab>
          <Tab value="income">{t("Income")}</Tab>
        </TabList>
        <Field label={t("Amount")} required className="full"
          hint={isFormula(amount) && value !== null ? `= ${money(value)}` : t("You can type a sum such as 12.50+3.")}>
          <Input ref={amountRef} size="large" inputMode="decimal" value={amount}
            onChange={(_, d) => setAmount(d.value)} placeholder="0.00" />
        </Field>
        <Field label={t("Payee")}>
          <Combobox freeform value={payee} placeholder={t("e.g. Migros")}
            onChange={(e) => setPayee((e.target as HTMLInputElement).value)}
            onOptionSelect={(_, d) => pickPayee(d.optionText ?? "")}
            onBlur={() => pickPayee(payee)}>
            {hints.map((h) => {
              const c = cats.find((x) => x.id === h.category_id);
              return (
                <Option key={h.payee} text={h.payee}>
                  <span className="cat-cell">
                    {c && <CategoryIcon name={c.name} icon={c.icon} color={c.color} size={22} />}
                    <span>{h.payee}{c && <span className="caption"> · {catLabel(c.full_name, t)}</span>}</span>
                  </span>
                </Option>);
            })}
          </Combobox>
        </Field>
        <Field label={t("Category")}>
          <Select value={category} onChange={(_, d) => { touchedCat.current = true; setCategory(d.value); }}>
            <option value="">{t("Uncategorised")}</option>
            {categoryOptions(cats, type, t).map((o) =>
              <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label={t("Account")} required>
          <Select value={account} onChange={(_, d) => setAccount(d.value)}>
            {accountOptions(accounts).map((o) =>
              <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label={t("Date")} required>
          <Input type="date" value={day} onChange={(_, d) => setDay(d.value)} />
        </Field>
        <Field label={t("Note")} className="full">
          <Input value={note} onChange={(_, d) => setNote(d.value)} />
        </Field>
        {cat && (
          <div className="full cat-cell caption">
            <CategoryIcon name={cat.name} icon={cat.icon} color={cat.color} size={24} />
            <span>{t("{a} to {c}", { a: value !== null ? money(type === "expense" ? -value : value) : "—",
              c: catLabel(cat.full_name, t) })}</span>
          </div>)}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

/** Opens Quick add with Ctrl+N anywhere in the app. */
export function QuickAddHotkey() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        setOpen(true);
      }
    };
    const onEvent = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("pfi:quick-add", onEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pfi:quick-add", onEvent);
    };
  }, []);
  return open ? <QuickAdd onClose={() => setOpen(false)}
    onSaved={() => window.dispatchEvent(new Event("pfi:transactions-changed"))} /> : null;
}

/** Open Quick add from a button. */
export const openQuickAdd = () => window.dispatchEvent(new Event("pfi:quick-add"));
