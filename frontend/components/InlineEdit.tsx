"use client";
// Edit a transaction where it is listed: click the category, double-click
// the description or the amount. Enter saves, Escape cancels.
import { ReactNode, useState } from "react";
import {
  Button, Input, Popover, PopoverSurface, PopoverTrigger, Select,
} from "@fluentui/react-components";
import { QuestionCircle20Regular } from "@fluentui/react-icons";
import { CategoryIcon } from "./CategoryIcon";
import { catLabel, categoryOptions } from "./refs";
import { Category, Txn, patch } from "@/lib/api";
import { evalAmount } from "@/lib/calc";
import { useT } from "@/lib/i18n";

type Saved = (msg?: string) => void;

export function CategoryCell({ x, cats, onSaved, onError }: {
  x: Txn; cats: Category[]; onSaved: Saved; onError: (m: string) => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const cat = cats.find((c) => c.id === x.category_id);
  const kind = x.kind === "income" ? "income" : "expense";
  if (editing) {
    return (
      <Select autoFocus size="small" defaultValue={x.category_id ?? ""}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}
        onChange={async (_, d) => {
          setEditing(false);
          try {
            await patch(`/api/transactions/${x.id}`, d.value
              ? { category_id: Number(d.value) } : { clear_category: true });
            onSaved();
          } catch (e) { onError((e as Error).message); }
        }}>
        <option value="">{t("Uncategorised")}</option>
        {categoryOptions(cats, kind, t).map((o) =>
          <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>);
  }
  return (
    <button type="button" className="cat-cell cell-button" title={t("Click to change the category")}
      onClick={() => setEditing(true)}>
      {cat ? <>
        <CategoryIcon name={cat.name} icon={cat.icon} color={cat.color} size={26} />
        <span>{catLabel(x.category_name, t)}</span></>
        : <span className="pill underfunded">{t("Uncategorised")}</span>}
    </button>);
}

export function TextCell({ value, label, onSave, children }: {
  value: string; label: string; onSave: (v: string) => Promise<void>; children: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);
  if (!editing) {
    return <div onDoubleClick={() => { setText(value); setEditing(true); }}
      title={label}>{children}</div>;
  }
  const done = async (save: boolean) => {
    setEditing(false);
    if (save && text !== value) await onSave(text);
  };
  return (
    <Input autoFocus size="small" value={text} aria-label={label}
      onChange={(_, d) => setText(d.value)} onBlur={() => done(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter") done(true);
        if (e.key === "Escape") done(false);
      }} />);
}

/** Amount editing keeps the direction (money in or out) of the original. */
export function AmountCell({ x, onSaved, onError, children }: {
  x: Txn; onSaved: Saved; onError: (m: string) => void; children: ReactNode;
}) {
  const t = useT();
  const locked = x.reconciled || x.kind === "transfer" || x.splits.length > 0 || !!x.trade_id;
  if (locked) return <>{children}</>;
  return (
    <TextCell value={String(Math.abs(x.amount))}
      label={t("Double-click to change the amount (sums like 12+3 work)")}
      onSave={async (v) => {
        const size = evalAmount(v);
        if (size === null || size === 0) { onError(t("“{v}” is not an amount.", { v })); return; }
        const signed = x.amount < 0 ? -Math.abs(size) : Math.abs(size);
        try {
          await patch(`/api/transactions/${x.id}`, { amount: String(signed), kind: x.kind });
          onSaved();
        } catch (e) { onError((e as Error).message); }
      }}>{children}</TextCell>);
}

export function SearchHelp() {
  const t = useT();
  const rows: [string, string][] = [
    ["payee:migros", t("Payee or description contains “migros”")],
    ["category:food", t("Category (or its parent) contains “food”")],
    ['account:"UBS card"', t("Account name; use quotes for spaces")],
    ["tag:holiday", t("Has a tag containing “holiday”")],
    ["amount:>50", t("Amount above 50 (also <, >=, <=)")],
    ["amount:10..20", t("Amount between 10 and 20")],
    ["after:2026-01-01", t("On or after a date (before: for earlier)")],
    ["is:unreviewed", t("Waiting for review; also is:cleared, is:reconciled, is:uncategorized, is:split, is:transfer")],
  ];
  return (
    <Popover withArrow>
      <PopoverTrigger disableButtonEnhancement>
        <Button appearance="subtle" icon={<QuestionCircle20Regular />} aria-label={t("Search help")} />
      </PopoverTrigger>
      <PopoverSurface className="search-help" style={{ maxWidth: 440 }}>
        <div className="detail-head">{t("Search filters")}</div>
        <div className="caption" style={{ marginBottom: 8 }}>
          {t("Combine words and filters, for example: payee:coop amount:>20 after:2026-01-01")}</div>
        <table className="facts"><tbody>{rows.map(([code, text]) => (
          <tr key={code}><td><code>{code}</code></td><td>{text}</td></tr>))}</tbody></table>
      </PopoverSurface>
    </Popover>);
}
