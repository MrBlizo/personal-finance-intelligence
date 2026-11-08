"use client";
import { useEffect, useState } from "react";
import {
  Badge, Button, Checkbox, Input, Select, Tooltip,
} from "@fluentui/react-components";
import {
  Add20Regular, ArrowDownload20Regular, ArrowSwap20Regular, Delete20Regular,
  Edit20Regular, Search20Regular, Sparkle20Regular,
} from "@fluentui/react-icons";
import { accountOptions, catLabel, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Modal, PageHead, Spinner, Values, clean,
  useLoad,
} from "@/components/ui";
import { Suggestion, Txn, del, downloadUrl, get, patch, post } from "@/lib/api";
import { date, money, pct, signClass, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

const PAGE = 100;

function SuggestionsDialog({ onClose, onDone }: { onClose: () => void; onDone: (n: number) => void }) {
  const t = useT();
  const list = useLoad(() => get<Suggestion[]>("/api/learn/suggestions"));
  const [picked, setPicked] = useState<Set<number> | null>(null);
  const rows = list.data ?? [];
  const sel = picked ?? new Set(rows.filter((r) => r.confidence >= 0.6).map((r) => r.id));
  const [busy, setBusy] = useState(false);
  return (
    <Modal wide title={t("Suggested categories")} onClose={onClose} actions={<>
      <Button appearance="primary" disabled={busy || sel.size === 0} onClick={async () => {
        setBusy(true);
        const r = await post<{ updated: number }>("/api/learn/apply",
          { ids: [...sel], min_confidence: 0 });
        onDone(r.updated); onClose();
      }}>{t("Accept {n} suggestions", { n: sel.size })}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      <div className="caption">
        {t("Learned from transactions you categorised yourself. Untick any suggestion you do not want.")}
      </div>
      {list.loading && <Spinner label={t("Loading…")} />}
      {list.data && rows.length === 0 && (
        <Empty>{t("No suggestions. Either everything is categorised, or there is not enough history yet (at least 20 categorised transactions).")}</Empty>)}
      {rows.length > 0 && (
        <div className="table-wrap" style={{ maxHeight: 420 }}>
          <table>
            <thead><tr><th /><th>{t("Date")}</th><th>{t("Description")}</th>
              <th className="num">{t("Amount")}</th><th>{t("Suggested category")}</th>
              <th className="num">{t("Confidence")}</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td><Checkbox checked={sel.has(r.id)} onChange={(_, d) => {
                  const s = new Set(sel); if (d.checked) s.add(r.id); else s.delete(r.id);
                  setPicked(s);
                }} /></td>
                <td>{date(r.txn_date)}</td>
                <td><span className="cell-main">{r.description}</span>
                  {r.why.length > 0 && <span className="cell-sub">
                    {t("because of: {w}", { w: r.why.join(", ") })}</span>}</td>
                <td className={`num ${signClass(r.amount)}`}>{money(r.amount, r.currency)}</td>
                <td>{catLabel(r.category_name, t)}</td>
                <td className="num">
                  <Badge appearance="tint" color={r.confidence >= 0.8 ? "success"
                    : r.confidence >= 0.6 ? "informative" : "warning"}>{pct(r.confidence, 0)}</Badge>
                </td>
              </tr>))}
            </tbody>
          </table>
        </div>)}
    </Modal>
  );
}

export default function Transactions() {
  const t = useT();
  const refs = useRefs();
  const [f, setF] = useState<Record<string, string>>({
    q: "", account_id: "", category_id: "", kind: "", start: "", end: "",
    uncategorized: "",
  });
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const acc = q.get("account");
    if (acc || q.get("uncategorized")) {
      setF((old) => ({ ...old, account_id: acc ?? "",
        uncategorized: q.get("uncategorized") ? "true" : "" }));
    }
  }, []);
  const list = useLoad(() => get<{ total: number; items: Txn[] }>(
    "/api/transactions", { ...f, limit: PAGE, offset }),
  [JSON.stringify(f), offset]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [modal, setModal] = useState<null | "add" | "transfer" | "suggest" | Txn>(null);
  const [confirm, setConfirm] = useState<Txn | null>(null);
  const [bulkCat, setBulkCat] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const accounts = refs.data?.accounts ?? [];
  const cats = refs.data?.categories ?? [];
  const setFilter = (k: string, v: string) => {
    setF({ ...f, [k]: v }); setOffset(0); setSel(new Set());
  };
  const reload = () => { list.reload(); refs.reload(); setSel(new Set()); };
  const items = list.data?.items ?? [];
  const base = refs.data?.settings.base_currency ?? "CHF";

  return (
    <>
      <PageHead title={t("Transactions")}
        sub={list.data ? t("{n} found", { n: list.data.total }) : ""}>
        <Button icon={<Sparkle20Regular />} onClick={() => setModal("suggest")}>
          {t("Suggest categories")}</Button>
        <Button icon={<ArrowDownload20Regular />} as="a"
          href={downloadUrl("/api/export/transactions.csv",
            { start: f.start, end: f.end, account_id: f.account_id })}>
          {t("Export CSV")}</Button>
        <Button icon={<ArrowSwap20Regular />} onClick={() => setModal("transfer")}>
          {t("Transfer")}</Button>
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setModal("add")}>
          {t("Add transaction")}</Button>
      </PageHead>
      {msg && <Banner kind="success" onClose={() => setMsg(null)}>{msg}</Banner>}
      {list.error && <Banner kind="error">{list.error}</Banner>}
      <div className="filters">
        <Input contentBefore={<Search20Regular />} style={{ minWidth: 260 }}
          placeholder={t("Search description, payee, notes…")} value={f.q}
          onChange={(_, d) => setFilter("q", d.value)} />
        <Select value={f.account_id} onChange={(_, d) => setFilter("account_id", d.value)}>
          <option value="">{t("All accounts")}</option>
          {accountOptions(accounts).map((o) =>
            <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select value={f.category_id} onChange={(_, d) => setFilter("category_id", d.value)}>
          <option value="">{t("All categories")}</option>
          {categoryOptions(cats, undefined, t).map((o) =>
            <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select value={f.kind} onChange={(_, d) => setFilter("kind", d.value)}>
          <option value="">{t("All kinds")}</option>
          <option value="income">{t("Income")}</option>
          <option value="expense">{t("Expense")}</option>
          <option value="transfer">{t("Transfer")}</option>
        </Select>
        <Input type="date" value={f.start} aria-label={t("From")}
          onChange={(_, d) => setFilter("start", d.value)} />
        <Input type="date" value={f.end} aria-label={t("To")}
          onChange={(_, d) => setFilter("end", d.value)} />
        <Checkbox label={t("Uncategorised only")} checked={f.uncategorized === "true"}
          onChange={(_, d) => setFilter("uncategorized", d.checked ? "true" : "")} />
      </div>
      {sel.size > 0 && (
        <div className="filters card" style={{ padding: "8px 12px" }}>
          <b>{t("{n} selected", { n: sel.size })}</b>
          <Select value={bulkCat} onChange={(_, d) => setBulkCat(d.value)}>
            <option value="">{t("Choose category…")}</option>
            {categoryOptions(cats, undefined, t).map((o) =>
              <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
          <Button appearance="primary" disabled={!bulkCat} onClick={async () => {
            const r = await post<{ updated: number }>("/api/transactions/bulk-categorize",
              { ids: [...sel], category_id: Number(bulkCat) });
            setMsg(t("{n} transactions categorised (transfers are skipped).", { n: r.updated }));
            reload();
          }}>{t("Apply category")}</Button>
          <Button appearance="subtle" onClick={() => setSel(new Set())}>{t("Clear selection")}</Button>
        </div>)}
      <div className="card table-wrap" style={{ padding: "4px 8px" }}>
        {list.loading && !list.data && <div style={{ padding: 16 }}><Spinner label={t("Loading…")} /></div>}
        {list.data && items.length === 0 && <Empty>{t("No transactions match these filters.")}</Empty>}
        {items.length > 0 && (
          <table>
            <thead><tr>
              <th style={{ width: 36 }}><Checkbox checked={sel.size === items.length ? true
                : sel.size ? "mixed" : false} aria-label={t("Select all")}
                onChange={(_, d) => setSel(d.checked ? new Set(items.map((x) => x.id)) : new Set())} /></th>
              <th>{t("Date")}</th><th>{t("Description")}</th><th>{t("Category")}</th>
              <th>{t("Account")}</th><th className="num">{t("Amount")}</th>
              <th className="num">{t("In {cur}", { cur: base })}</th><th />
            </tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.id} className={sel.has(x.id) ? "selected" : ""}>
                  <td><Checkbox checked={sel.has(x.id)} onChange={(_, d) => {
                    const s = new Set(sel); if (d.checked) s.add(x.id); else s.delete(x.id); setSel(s);
                  }} /></td>
                  <td>{date(x.txn_date)}</td>
                  <td><span className="cell-main">{x.description || "—"}</span>
                    {x.merchant && <span className="cell-sub">{x.merchant}</span>}</td>
                  <td>{x.kind === "transfer"
                    ? <Badge appearance="tint" color="informative">{t("Transfer")}</Badge>
                    : x.category_name ? catLabel(x.category_name, t)
                    : <Badge appearance="tint" color="warning">{t("Uncategorised")}</Badge>}</td>
                  <td>{x.account_name}</td>
                  <td className={`num ${signClass(x.amount)}`}>{money(x.amount, x.currency)}</td>
                  <td className="num muted">{x.currency === base ? "" : money(x.amount_base)}</td>
                  <td className="actions">
                    {x.trade_id ? <span className="caption">{t("trade")}</span> : <>
                      <Tooltip content={t("Edit")} relationship="label">
                        <Button appearance="subtle" size="small" icon={<Edit20Regular />}
                          onClick={() => setModal(x)} /></Tooltip>
                      <Tooltip content={t("Delete")} relationship="label">
                        <Button appearance="subtle" size="small" icon={<Delete20Regular />}
                          onClick={() => setConfirm(x)} /></Tooltip></>}
                  </td>
                </tr>))}
            </tbody>
          </table>)}
      </div>
      {list.data && list.data.total > PAGE && (
        <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
          <span className="caption">{t("{a}–{b} of {n}", { a: offset + 1,
            b: Math.min(offset + PAGE, list.data.total), n: list.data.total })}</span>
          <Button disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>{t("Previous")}</Button>
          <Button disabled={offset + PAGE >= list.data.total}
            onClick={() => setOffset(offset + PAGE)}>{t("Next")}</Button>
        </div>)}

      {modal === "suggest" && (
        <SuggestionsDialog onClose={() => setModal(null)} onDone={(n) => {
          setMsg(t("{n} transactions categorised from suggestions.", { n })); reload();
        }} />)}

      {(modal === "add" || (modal && typeof modal === "object")) && (() => {
        const x = typeof modal === "object" ? modal : null;
        const isTransfer = x?.kind === "transfer";
        const typeOf = (y: Txn) => y.kind === "income" ? "income"
          : y.amount > 0 ? "refund" : "expense";
        const catKind = (type: unknown) => (type === "income" ? "income" : "expense");
        return (
          <FormModal title={x ? t("Edit transaction") : t("Add transaction")}
            onClose={() => setModal(null)}
            initial={x ? {
              account_id: x.account_id, txn_date: x.txn_date, amount: Math.abs(x.amount),
              type: isTransfer ? "expense" : typeOf(x),
              description: x.description, merchant: x.merchant, category_id: x.category_id,
              notes: x.notes,
            } : { account_id: accounts.find((a) => !a.is_archived)?.id ?? "", txn_date: today(),
              type: "expense", amount: "", description: "", merchant: "", category_id: "", notes: "" }}
            onChange={(v) => {
              const cat = cats.find((c) => c.id === Number(v.category_id));
              return cat && cat.kind !== catKind(v.type) ? { ...v, category_id: "" } : v;
            }}
            fields={(v) => [
              { name: "account_id", label: t("Account"), type: "select", required: true,
                options: accountOptions(accounts), hidden: !!x },
              { name: "type", label: t("Type"), type: "select", required: true, hidden: isTransfer,
                options: [{ value: "expense", label: t("Expense (money out)") },
                  { value: "income", label: t("Income (money in)") },
                  { value: "refund", label: t("Refund (money back on an expense)") }] },
              { name: "txn_date", label: t("Date"), type: "date", required: true },
              { name: "amount", label: t("Amount"), type: "number", step: "0.01",
                required: true, hidden: isTransfer, placeholder: "910.00",
                help: t("Always positive; the type decides the direction.") },
              { name: "category_id", label: t("Category"), type: "select",
                options: categoryOptions(cats, catKind(v.type), t), hidden: isTransfer },
              { name: "description", label: t("Description"), full: true },
              { name: "merchant", label: t("Payee / merchant") },
              { name: "notes", label: t("Notes"), type: "textarea", full: true },
            ]}
            onSubmit={async (v: Values) => {
              const body = clean(v, ["account_id", "category_id"]);
              const size = Math.abs(Number(body.amount));
              if (!isTransfer && !(size > 0)) throw new Error(t("Enter an amount above 0."));
              const signed = String(v.type === "expense" ? -size : size);
              const kind = v.type === "income" ? "income" : "expense";
              if (x) {
                const p: Values = { txn_date: body.txn_date, description: body.description ?? "",
                  merchant: body.merchant, notes: body.notes };
                if (!isTransfer) {
                  p.amount = signed;
                  p.kind = kind;
                  if (body.category_id) p.category_id = body.category_id; else p.clear_category = true;
                }
                await patch(`/api/transactions/${x.id}`, p);
              } else {
                await post("/api/transactions", { account_id: body.account_id, txn_date: body.txn_date,
                  amount: signed, kind, category_id: body.category_id,
                  description: body.description ?? "", merchant: body.merchant, notes: body.notes });
              }
              reload();
            }} />);
      })()}

      {modal === "transfer" && (
        <FormModal title={t("Transfer between accounts")} onClose={() => setModal(null)}
          initial={{ from_account_id: "", to_account_id: "", txn_date: today(), amount: "",
            to_amount: "", description: t("Transfer") }}
          fields={[
            { name: "from_account_id", label: t("From"), type: "select", required: true, options: accountOptions(accounts) },
            { name: "to_account_id", label: t("To"), type: "select", required: true, options: accountOptions(accounts) },
            { name: "txn_date", label: t("Date"), type: "date", required: true },
            { name: "amount", label: t("Amount sent"), type: "number", step: "0.01", required: true },
            { name: "to_amount", label: t("Amount received (if other currency)"), type: "number", step: "0.01",
              help: t("Leave empty to convert with the stored exchange rate.") },
            { name: "description", label: t("Description") },
          ]}
          onSubmit={async (v) => {
            const b = clean(v, ["from_account_id", "to_account_id"]);
            await post("/api/transfers", { ...b, amount: String(b.amount),
              to_amount: b.to_amount === null ? null : String(b.to_amount) });
            setMsg(t("Transfer saved.")); reload();
          }} />)}

      {confirm && (
        <Confirm danger yesLabel={t("Delete")} onClose={() => setConfirm(null)}
          text={confirm.transfer_group
            ? t("Delete this transfer? Both sides of the transfer will be deleted.")
            : t("Delete “{d}” ({a})?", { d: confirm.description || t("transaction"),
              a: money(confirm.amount, confirm.currency) })}
          onYes={async () => { await del(`/api/transactions/${confirm.id}`); reload(); }} />)}
    </>
  );
}
