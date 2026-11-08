"use client";
import { useState } from "react";
import { accountOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, PageHead, Progress, Spinner, clean, useLoad,
} from "@/components/ui";
import { Goal, del, get, post, put } from "@/lib/api";
import { CURRENCIES, date, money, pct } from "@/lib/format";

const STATUS: Record<string, [string, string]> = {
  completed: ["ok", "Completed"], on_track: ["ok", "On track"], behind: ["warn", "Behind"],
  overdue: ["err", "Overdue"], no_deadline: ["", "No deadline"], manual: ["info", "Manual tracking"],
};

export default function Goals() {
  const refs = useRefs();
  const goals = useLoad(() => get<Goal[]>("/api/goals"));
  const [edit, setEdit] = useState<Goal | "new" | null>(null);
  const [remove, setRemove] = useState<Goal | null>(null);
  const accounts = refs.data?.accounts ?? [];

  return (
    <>
      <PageHead title="Savings goals" sub="Link a goal to a savings account to track it automatically">
        <button className="primary" onClick={() => setEdit("new")}>+ Add goal</button>
      </PageHead>
      {goals.error && <Banner kind="error">{goals.error}</Banner>}
      {goals.loading && !goals.data && <Spinner />}
      {goals.data?.length === 0 && <div className="card"><Empty>No goals yet — e.g. an emergency fund of 3–6 months of expenses.</Empty></div>}
      <div className="grid g3">
        {goals.data?.map((g) => {
          const [cls, label] = STATUS[g.status] ?? ["", g.status];
          const acc = accounts.find((a) => a.id === g.account_id);
          return (
            <div className="card" key={g.id}>
              <div className="page-head" style={{ marginBottom: 8 }}>
                <h3 style={{ margin: 0 }}>{g.name}</h3>
                <span className={`badge ${cls}`}>{label}</span>
              </div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{money(g.saved_amount, g.currency, 0)}
                <span className="muted small"> of {money(g.target_amount, undefined, 0)}</span></div>
              <Progress value={g.progress} />
              <div className="small muted" style={{ marginTop: 4 }}>{pct(g.progress, 0)}
                {acc ? ` · tracked from ${acc.name}` : " · manual amount"}</div>
              <table className="small" style={{ marginTop: 12 }}><tbody>
                <tr><td>Target date</td><td className="num">{date(g.target_date)}</td></tr>
                <tr><td>Needed per month</td><td className="num">{money(g.required_monthly, g.currency, 0)}</td></tr>
                <tr><td>Saved per month (last 90 days)</td><td className="num">{money(g.recent_monthly_saving, g.currency, 0)}</td></tr>
                <tr><td>Projected completion</td><td className="num">{date(g.projected_completion)}</td></tr>
              </tbody></table>
              {g.note && <div className="small muted">{g.note}</div>}
              <div className="toolbar" style={{ marginTop: 8 }}>
                <button className="link" onClick={() => setEdit(g)}>Edit</button>
                <button className="link danger" onClick={() => setRemove(g)}>Delete</button>
              </div>
            </div>);
        })}
      </div>
      {edit && (() => {
        const g = edit === "new" ? null : edit;
        return (
          <FormModal title={g ? `Edit ${g.name}` : "Add savings goal"} onClose={() => setEdit(null)}
            initial={g ? { name: g.name, target_amount: g.target_amount, currency: g.currency,
              target_date: g.target_date, account_id: g.account_id, saved_amount: g.manual_saved_amount,
              priority: g.priority, notes: g.notes }
              : { name: "", target_amount: "", currency: refs.data?.settings.base_currency ?? "CHF",
                target_date: "", account_id: "", saved_amount: "0", priority: 0, notes: "" }}
            fields={[
              { name: "name", label: "Name", required: true, full: true },
              { name: "target_amount", label: "Target amount", type: "number", step: "0.01", required: true },
              { name: "currency", label: "Currency", type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
              { name: "target_date", label: "Target date", type: "date" },
              { name: "account_id", label: "Linked account", type: "select", options: accountOptions(accounts),
                help: "Balance of this account counts as saved." },
              { name: "saved_amount", label: "Saved so far (if no account)", type: "number", step: "0.01" },
              { name: "priority", label: "Priority (higher first)", type: "number" },
              { name: "notes", label: "Notes", type: "textarea", full: true },
            ]}
            onSubmit={async (v) => {
              const b = clean(v, ["account_id", "priority"]);
              const body = { ...b, target_amount: String(b.target_amount),
                saved_amount: String(b.saved_amount ?? 0), priority: b.priority ?? 0 };
              if (g) await put(`/api/goals/${g.id}`, body); else await post("/api/goals", body);
              goals.reload();
            }} />);
      })()}
      {remove && <Confirm onClose={() => setRemove(null)} text={`Delete the goal “${remove.name}”?`}
        onYes={async () => { await del(`/api/goals/${remove.id}`); goals.reload(); }} />}
    </>
  );
}
