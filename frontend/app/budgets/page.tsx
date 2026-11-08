"use client";
import { useState } from "react";
import { categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Progress, Spinner, useLoad,
} from "@/components/ui";
import { BudgetItem, BudgetStatus, del, get, post, put } from "@/lib/api";
import { money, pct } from "@/lib/format";

const STATUS: Record<string, [string, string]> = {
  ok: ["ok", "On track"], at_risk: ["warn", "At risk"], over: ["err", "Over budget"],
};

export default function Budgets() {
  const now = new Date();
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const refs = useRefs();
  const status = useLoad(() => get<BudgetStatus>("/api/budgets/status", { month }), [month]);
  const [edit, setEdit] = useState<BudgetItem | "new" | null>(null);
  const [remove, setRemove] = useState<BudgetItem | null>(null);
  const s = status.data;
  const cur = s?.currency ?? "CHF";
  const used = new Set(s?.items.map((i) => i.category_id));

  return (
    <>
      <PageHead title="Budgets" sub={`Monthly limits per expense category, in ${cur}`}>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        <button className="primary" onClick={() => setEdit("new")}>+ Add budget</button>
      </PageHead>
      {status.error && <Banner kind="error">{status.error}</Banner>}
      {status.loading && !s && <Spinner />}
      {s && (
        <div className="stack">
          <div className="grid kpis">
            <Kpi label="Budgeted" value={money(s.total_budget, cur)} />
            <Kpi label="Spent" value={money(s.total_spent, cur)}
              sub={s.total_budget ? `${pct(s.total_spent / s.total_budget, 0)} of budget` : undefined} />
            <Kpi label="Remaining" value={money(s.total_budget - s.total_spent, cur)}
              cls={s.total_budget - s.total_spent < 0 ? "neg" : "pos"} />
            <Kpi label="Month progress" value={`${s.days_elapsed} / ${s.days_in_month} days`} />
          </div>
          <div className="card">
            {s.items.length === 0 ? <Empty>No budgets yet. Add one for a category such as Food.</Empty> : (
              <table>
                <thead><tr><th>Category</th><th style={{ width: "30%" }}>Progress</th>
                  <th className="num">Spent</th><th className="num">Budget</th>
                  <th className="num">Projected</th><th>Status</th><th /></tr></thead>
                <tbody>{s.items.map((i) => (
                  <tr key={i.id}>
                    <td>{i.category}</td>
                    <td><Progress value={(i.pct ?? 0)} status={i.status} />
                      <span className="small muted">{pct(i.pct, 0)}</span></td>
                    <td className="num">{money(i.spent)}</td>
                    <td className="num">{money(i.budget)}</td>
                    <td className="num muted" title="Linear projection to month end">{money(i.projected)}</td>
                    <td><span className={`badge ${STATUS[i.status][0]}`}>{STATUS[i.status][1]}</span></td>
                    <td className="num">
                      <button className="link" onClick={() => setEdit(i)}>Edit</button>
                      <button className="link danger" onClick={() => setRemove(i)}>Delete</button>
                    </td>
                  </tr>))}</tbody>
              </table>)}
            <p className="small muted">Spending in sub-categories counts toward a parent category&apos;s budget.
              “Projected” extrapolates the month so far linearly and is rough early in the month.</p>
          </div>
        </div>)}
      {edit && (
        <FormModal title={edit === "new" ? "Add budget" : `Edit budget: ${edit.category}`}
          onClose={() => setEdit(null)}
          initial={edit === "new" ? { category_id: "", monthly_amount: "" }
            : { category_id: edit.category_id, monthly_amount: edit.budget }}
          fields={[
            { name: "category_id", label: "Expense category", type: "select", required: true,
              options: categoryOptions(refs.data?.categories ?? [], "expense")
                .filter((o) => edit !== "new" || !used.has(Number(o.value))) },
            { name: "monthly_amount", label: `Monthly limit (${cur})`, type: "number", step: "0.01", required: true },
          ]}
          onSubmit={async (v) => {
            const body = { category_id: Number(v.category_id), monthly_amount: String(v.monthly_amount) };
            if (edit === "new") await post("/api/budgets", body);
            else await put(`/api/budgets/${edit.id}`, body);
            status.reload();
          }} />)}
      {remove && <Confirm onClose={() => setRemove(null)} text={`Delete the budget for ${remove.category}?`}
        onYes={async () => { await del(`/api/budgets/${remove.id}`); status.reload(); }} />}
    </>
  );
}
