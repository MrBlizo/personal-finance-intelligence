"use client";
import { useEffect, useState } from "react";
import { accountOptions, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, PageHead, Spinner, Values, clean, useLoad,
} from "@/components/ui";
import { Txn, del, get, patch, post } from "@/lib/api";
import { date, money, signClass, today } from "@/lib/format";

const PAGE = 100;

export default function Transactions() {
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
  const [modal, setModal] = useState<null | "add" | "transfer" | Txn>(null);
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
      <PageHead title="Transactions" sub={list.data ? `${list.data.total} found` : ""}>
        <button onClick={() => setModal("transfer")}>Transfer</button>
        <button className="primary" onClick={() => setModal("add")}>
          + Add transaction</button>
      </PageHead>
      {msg && <Banner kind="success" onClose={() => setMsg(null)}>{msg}</Banner>}
      {list.error && <Banner kind="error">{list.error}</Banner>}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="toolbar">
          <input placeholder="Search description, payee, notes…" value={f.q}
            style={{ minWidth: 260 }} onChange={(e) => setFilter("q", e.target.value)} />
          <select value={f.account_id} onChange={(e) => setFilter("account_id", e.target.value)}>
            <option value="">All accounts</option>
            {accountOptions(accounts).map((o) =>
              <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={f.category_id} onChange={(e) => setFilter("category_id", e.target.value)}>
            <option value="">All categories</option>
            {categoryOptions(cats).map((o) =>
              <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={f.kind} onChange={(e) => setFilter("kind", e.target.value)}>
            <option value="">All kinds</option><option value="income">Income</option>
            <option value="expense">Expense</option><option value="transfer">Transfer</option>
          </select>
          <input type="date" value={f.start} onChange={(e) => setFilter("start", e.target.value)} title="From" />
          <input type="date" value={f.end} onChange={(e) => setFilter("end", e.target.value)} title="To" />
          <label className="check"><input type="checkbox" checked={f.uncategorized === "true"}
            onChange={(e) => setFilter("uncategorized", e.target.checked ? "true" : "")} />
            Uncategorized only</label>
        </div>
        {sel.size > 0 && (
          <div className="toolbar" style={{ marginTop: 12 }}>
            <b>{sel.size} selected</b>
            <select value={bulkCat} onChange={(e) => setBulkCat(e.target.value)}>
              <option value="">Choose category…</option>
              {categoryOptions(cats).map((o) =>
                <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button disabled={!bulkCat} onClick={async () => {
              const r = await post<{ updated: number }>("/api/transactions/bulk-categorize",
                { ids: [...sel], category_id: Number(bulkCat) });
              setMsg(`${r.updated} transactions categorized (transfers are skipped).`);
              reload();
            }}>Apply category</button>
          </div>)}
      </div>
      <div className="card table-wrap">
        {list.loading && !list.data && <Spinner label="Loading…" />}
        {list.data && items.length === 0 && <Empty>No transactions match these filters.</Empty>}
        {items.length > 0 && (
          <table>
            <thead><tr>
              <th><input type="checkbox" checked={sel.size === items.length}
                onChange={(e) => setSel(e.target.checked ? new Set(items.map((t) => t.id)) : new Set())} /></th>
              <th>Date</th><th>Description</th><th>Category</th><th>Account</th>
              <th className="num">Amount</th><th className="num">In {base}</th><th />
            </tr></thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id}>
                  <td><input type="checkbox" checked={sel.has(t.id)} onChange={(e) => {
                    const s = new Set(sel); if (e.target.checked) s.add(t.id); else s.delete(t.id); setSel(s);
                  }} /></td>
                  <td>{date(t.txn_date)}</td>
                  <td>{t.description || <span className="muted">—</span>}
                    {t.merchant && <div className="small muted">{t.merchant}</div>}</td>
                  <td>{t.kind === "transfer" ? <span className="badge info">Transfer</span>
                    : t.category_name ?? <span className="badge warn">Uncategorized</span>}</td>
                  <td>{t.account_name}</td>
                  <td className={`num ${signClass(t.amount)}`}>{money(t.amount, t.currency)}</td>
                  <td className="num muted">{t.currency === base ? "" : money(t.amount_base)}</td>
                  <td className="num">
                    {t.trade_id ? <span className="small muted">trade</span> : <>
                      <button className="link" onClick={() => setModal(t)}>Edit</button>
                      <button className="link danger" onClick={() => setConfirm(t)}>Delete</button></>}
                  </td>
                </tr>))}
            </tbody>
          </table>)}
        {list.data && list.data.total > PAGE && (
          <div className="toolbar" style={{ marginTop: 12, justifyContent: "flex-end" }}>
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE, list.data.total)} of {list.data.total}</span>
            <button disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>‹ Previous</button>
            <button disabled={offset + PAGE >= list.data.total} onClick={() => setOffset(offset + PAGE)}>Next ›</button>
          </div>)}
      </div>

      {(modal === "add" || (modal && typeof modal === "object")) && (() => {
        const t = typeof modal === "object" ? modal : null;
        const isTransfer = t?.kind === "transfer";
        const typeOf = (x: Txn) => x.kind === "income" ? "income"
          : x.amount > 0 ? "refund" : "expense";
        const catKind = (type: unknown) => (type === "income" ? "income" : "expense");
        return (
          <FormModal title={t ? "Edit transaction" : "Add transaction"} onClose={() => setModal(null)}
            initial={t ? {
              account_id: t.account_id, txn_date: t.txn_date, amount: Math.abs(t.amount),
              type: isTransfer ? "expense" : typeOf(t),
              description: t.description, merchant: t.merchant, category_id: t.category_id,
              notes: t.notes,
            } : { account_id: accounts.find((a) => !a.is_archived)?.id ?? "", txn_date: today(),
              type: "expense", amount: "", description: "", merchant: "", category_id: "", notes: "" }}
            onChange={(v) => {
              const cat = cats.find((c) => c.id === Number(v.category_id));
              return cat && cat.kind !== catKind(v.type) ? { ...v, category_id: "" } : v;
            }}
            fields={(v) => [
              { name: "account_id", label: "Account", type: "select", required: true,
                options: accountOptions(accounts), hidden: !!t },
              { name: "type", label: "Type", type: "select", required: true, hidden: isTransfer,
                options: [{ value: "expense", label: "Expense (money out)" },
                  { value: "income", label: "Income (money in)" },
                  { value: "refund", label: "Refund (money back on an expense)" }] },
              { name: "txn_date", label: "Date", type: "date", required: true },
              { name: "amount", label: "Amount", type: "number", step: "0.01",
                required: true, hidden: isTransfer, placeholder: "e.g. 910.00",
                help: "Always positive; the type decides the direction." },
              { name: "category_id", label: "Category", type: "select",
                options: categoryOptions(cats, catKind(v.type)), hidden: isTransfer },
              { name: "description", label: "Description", full: true },
              { name: "merchant", label: "Payee / merchant" },
              { name: "notes", label: "Notes", type: "textarea", full: true },
            ]}
            onSubmit={async (v: Values) => {
              const body = clean(v, ["account_id", "category_id"]);
              const size = Math.abs(Number(body.amount));
              if (!isTransfer && !(size > 0)) throw new Error("Enter an amount above 0.");
              const signed = String(v.type === "expense" ? -size : size);
              const kind = v.type === "income" ? "income" : "expense";
              if (t) {
                const p: Values = { txn_date: body.txn_date, description: body.description ?? "",
                  merchant: body.merchant, notes: body.notes };
                if (!isTransfer) {
                  p.amount = signed;
                  p.kind = kind;
                  if (body.category_id) p.category_id = body.category_id; else p.clear_category = true;
                }
                await patch(`/api/transactions/${t.id}`, p);
              } else {
                await post("/api/transactions", { account_id: body.account_id, txn_date: body.txn_date,
                  amount: signed, kind, category_id: body.category_id,
                  description: body.description ?? "", merchant: body.merchant, notes: body.notes });
              }
              reload();
            }} />);
      })()}

      {modal === "transfer" && (
        <FormModal title="Transfer between accounts" onClose={() => setModal(null)}
          initial={{ from_account_id: "", to_account_id: "", txn_date: today(), amount: "",
            to_amount: "", description: "Transfer" }}
          fields={[
            { name: "from_account_id", label: "From", type: "select", required: true, options: accountOptions(accounts) },
            { name: "to_account_id", label: "To", type: "select", required: true, options: accountOptions(accounts) },
            { name: "txn_date", label: "Date", type: "date", required: true },
            { name: "amount", label: "Amount sent", type: "number", step: "0.01", required: true },
            { name: "to_amount", label: "Amount received (if other currency)", type: "number", step: "0.01",
              help: "Leave empty to convert with the stored exchange rate." },
            { name: "description", label: "Description" },
          ]}
          onSubmit={async (v) => {
            const b = clean(v, ["from_account_id", "to_account_id"]);
            await post("/api/transfers", { ...b, amount: String(b.amount),
              to_amount: b.to_amount === null ? null : String(b.to_amount) });
            setMsg("Transfer saved."); reload();
          }} />)}

      {confirm && (
        <Confirm onClose={() => setConfirm(null)}
          text={confirm.transfer_group
            ? "Delete this transfer? Both sides of the transfer will be deleted."
            : `Delete “${confirm.description || "transaction"}” (${money(confirm.amount, confirm.currency)})?`}
          onYes={async () => { await del(`/api/transactions/${confirm.id}`); reload(); }} />)}
    </>
  );
}
