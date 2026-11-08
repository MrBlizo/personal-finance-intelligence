"use client";
import { useState } from "react";
import { Button, Input, Tooltip } from "@fluentui/react-components";
import { Add20Regular, Delete20Regular, Edit20Regular } from "@fluentui/react-icons";
import { catLabel, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Progress, Spinner,
  StatusBadge, useLoad,
} from "@/components/ui";
import { BudgetItem, BudgetStatus, del, get, post, put } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function Budgets() {
  const t = useT();
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
      <PageHead title={t("Budgets")} sub={t("Monthly limits per expense category, in {cur}", { cur })}>
        <Input type="month" value={month} onChange={(_, d) => setMonth(d.value)}
          aria-label={t("Month")} />
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setEdit("new")}>
          {t("Add budget")}</Button>
      </PageHead>
      {status.error && <Banner kind="error">{status.error}</Banner>}
      {status.loading && !s && <Spinner />}
      {s && (
        <>
          <div className="kpis">
            <Kpi label={t("Budgeted")} value={money(s.total_budget, cur)} />
            <Kpi label={t("Spent")} value={money(s.total_spent, cur)}
              sub={s.total_budget ? t("{p} of budget", { p: pct(s.total_spent / s.total_budget, 0) }) : undefined} />
            <Kpi label={t("Remaining")} value={money(s.total_budget - s.total_spent, cur)}
              cls={s.total_budget - s.total_spent < 0 ? "neg" : "pos"} />
            <Kpi label={t("Month progress")}
              value={t("{a} / {b} days", { a: s.days_elapsed, b: s.days_in_month })} />
          </div>
          <div className="card table-wrap" style={{ padding: "4px 8px" }}>
            {s.items.length === 0 ? (
              <Empty action={<Button appearance="primary" onClick={() => setEdit("new")}>{t("Add budget")}</Button>}>
                {t("No budgets yet. Add one for a category such as Food.")}</Empty>) : (
              <table>
                <thead><tr><th>{t("Category")}</th><th style={{ width: "28%" }}>{t("Progress")}</th>
                  <th className="num">{t("Spent")}</th><th className="num">{t("Budget")}</th>
                  <th className="num">{t("Projected")}</th><th>{t("Status")}</th><th /></tr></thead>
                <tbody>{s.items.map((i) => (
                  <tr key={i.id}>
                    <td>{catLabel(i.category, t)}</td>
                    <td><Progress value={i.pct ?? 0} status={i.status} />
                      <span className="caption">{pct(i.pct, 0)}</span></td>
                    <td className="num">{money(i.spent)}</td>
                    <td className="num">{money(i.budget)}</td>
                    <td className="num muted">{money(i.projected)}</td>
                    <td><StatusBadge status={i.status} /></td>
                    <td className="actions">
                      <Tooltip content={t("Edit")} relationship="label">
                        <Button appearance="subtle" size="small" icon={<Edit20Regular />}
                          onClick={() => setEdit(i)} /></Tooltip>
                      <Tooltip content={t("Delete")} relationship="label">
                        <Button appearance="subtle" size="small" icon={<Delete20Regular />}
                          onClick={() => setRemove(i)} /></Tooltip>
                    </td>
                  </tr>))}</tbody>
              </table>)}
          </div>
          <p className="caption" style={{ marginTop: 8 }}>
            {t("Spending in sub-categories counts toward a parent category's budget. “Projected” extrapolates the month so far linearly and is rough early in the month.")}</p>
        </>)}
      {edit && (
        <FormModal title={edit === "new" ? t("Add budget")
          : t("Edit budget: {c}", { c: catLabel(edit.category, t) })}
          onClose={() => setEdit(null)}
          initial={edit === "new" ? { category_id: "", monthly_amount: "" }
            : { category_id: edit.category_id, monthly_amount: edit.budget }}
          fields={[
            { name: "category_id", label: t("Expense category"), type: "select", required: true,
              options: categoryOptions(refs.data?.categories ?? [], "expense", t)
                .filter((o) => edit !== "new" || !used.has(Number(o.value))) },
            { name: "monthly_amount", label: t("Monthly limit ({cur})", { cur }), type: "number",
              step: "0.01", required: true },
          ]}
          onSubmit={async (v) => {
            const body = { category_id: Number(v.category_id), monthly_amount: String(v.monthly_amount) };
            if (edit === "new") await post("/api/budgets", body);
            else await put(`/api/budgets/${edit.id}`, body);
            status.reload();
          }} />)}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete the budget for {c}?", { c: catLabel(remove.category, t) })}
        onYes={async () => { await del(`/api/budgets/${remove.id}`); status.reload(); }} />}
    </>
  );
}
