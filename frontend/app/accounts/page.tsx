"use client";
import Link from "next/link";
import { useState } from "react";
import { useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Spinner, clean,
} from "@/components/ui";
import { Account, del, post, put } from "@/lib/api";
import { ACCOUNT_TYPES, CURRENCIES, money, signClass, today } from "@/lib/format";

export default function Accounts() {
  const refs = useRefs();
  const [edit, setEdit] = useState<Account | "new" | null>(null);
  const [remove, setRemove] = useState<Account | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const base = refs.data?.settings.base_currency ?? "CHF";
  const accounts = (refs.data?.accounts ?? []).filter((a) => showArchived || !a.is_archived);
  const total = (types: string[]) => accounts.filter((a) => types.includes(a.type))
    .reduce((s, a) => s + (a.balance_base ?? 0) + a.holdings_base, 0);
  const missing = accounts.filter((a) => a.balance_base === null);

  return (
    <>
      <PageHead title="Accounts" sub="Bank accounts, cards, cash, investments and loans">
        <label className="check"><input type="checkbox" checked={showArchived}
          onChange={(e) => setShowArchived(e.target.checked)} />Show archived</label>
        <button className="primary" onClick={() => setEdit("new")}>+ Add account</button>
      </PageHead>
      {refs.error && <Banner kind="error">{refs.error}</Banner>}
      {missing.length > 0 && (
        <Banner kind="warning">
          {missing.map((a) => a.currency).filter((c, i, l) => l.indexOf(c) === i).join(", ")}
          {" "}cannot be converted to {base}. <Link href="/settings/">Add an exchange rate</Link>.
        </Banner>)}
      {refs.loading && !refs.data && <Spinner />}
      {refs.data && (
        <div className="stack">
          <div className="grid kpis">
            <Kpi label="Liquid" value={money(total(["checking", "savings", "cash", "credit_card"]), base)} />
            <Kpi label="Investments" value={money(total(["investment"]), base)} />
            <Kpi label="Loans" value={money(total(["loan"]), base)} />
            <Kpi label="Net worth" value={money(total(Object.keys(ACCOUNT_TYPES)), base)} />
          </div>
          <div className="card table-wrap">
            {accounts.length === 0 ? <Empty>No accounts yet. Add your first account to start.</Empty> : (
              <table>
                <thead><tr><th>Name</th><th>Type</th><th>Institution</th>
                  <th className="num">Balance</th><th className="num">In {base}</th><th /></tr></thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id} style={{ opacity: a.is_archived ? 0.55 : 1 }}>
                      <td><Link href={`/transactions/?account=${a.id}`}>{a.name}</Link>
                        {a.is_demo && <> <span className="badge info">demo</span></>}
                        {a.is_archived && <> <span className="badge">archived</span></>}</td>
                      <td>{ACCOUNT_TYPES[a.type]}</td>
                      <td className="muted">{a.institution ?? ""}</td>
                      <td className={`num ${signClass(a.balance)}`}>{money(a.balance, a.currency)}
                        {a.holdings_base > 0 && <div className="small muted">+ holdings {money(a.holdings_base, base)}</div>}</td>
                      <td className="num">{money((a.balance_base ?? NaN) + a.holdings_base)}</td>
                      <td className="num">
                        <button className="link" onClick={() => setEdit(a)}>Edit</button>
                        <button className="link danger" onClick={() => setRemove(a)}>Delete</button>
                      </td>
                    </tr>))}
                </tbody>
              </table>)}
          </div>
        </div>)}

      {edit && (() => {
        const a = edit === "new" ? null : edit;
        return (
          <FormModal title={a ? `Edit ${a.name}` : "Add account"} onClose={() => setEdit(null)}
            initial={a ? { ...a } as never : {
              name: "", type: "checking", currency: base, institution: "",
              opening_balance: "0", opening_date: today(), is_archived: false, notes: "",
            }}
            fields={[
              { name: "name", label: "Name", required: true, full: true },
              { name: "type", label: "Type", type: "select", required: true,
                options: Object.entries(ACCOUNT_TYPES).map(([value, label]) => ({ value, label })) },
              { name: "currency", label: "Currency", type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
              { name: "institution", label: "Bank / institution" },
              { name: "opening_date", label: "Opening date", type: "date", required: true },
              { name: "opening_balance", label: "Opening balance", type: "number", step: "0.01",
                help: "Balance on the opening date, before any transaction you enter or import." },
              { name: "is_archived", label: "Archived (hidden from lists and forecast)", type: "checkbox", full: true },
              { name: "notes", label: "Notes", type: "textarea", full: true },
            ]}
            onSubmit={async (v) => {
              const b = clean(v);
              const body = { ...b, opening_balance: String(b.opening_balance ?? "0") };
              if (a) await put(`/api/accounts/${a.id}`, body);
              else await post("/api/accounts", body);
              refs.reload();
            }} />);
      })()}
      {remove && (
        <Confirm onClose={() => setRemove(null)}
          text={<>Delete <b>{remove.name}</b> and <b>all its transactions</b>? This cannot be undone.
            To keep the history, edit the account and tick “Archived” instead.</>}
          onYes={async () => { await del(`/api/accounts/${remove.id}`, { confirm: true }); refs.reload(); }} />)}
    </>
  );
}
