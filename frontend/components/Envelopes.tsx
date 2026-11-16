"use client";
// Envelope (zero-based) budgeting: give every franc a job.
import { useEffect, useState } from "react";
import {
  Button, Input, Menu, MenuItem, MenuList, MenuPopover, MenuTrigger, Tooltip,
} from "@fluentui/react-components";
import {
  ArrowSwap20Regular, ChevronLeft20Regular, ChevronRight20Regular,
  Flash20Regular, Target20Regular,
} from "@fluentui/react-icons";
import { CategoryIcon } from "./CategoryIcon";
import { catLabel } from "./refs";
import { Banner, FormModal, Modal, Spinner, useLoad } from "./ui";
import {
  EnvelopeMonth, EnvelopeRow, Id, QuickAssign, del, get, post, put,
} from "@/lib/api";
import { evalAmount } from "@/lib/calc";
import { money } from "@/lib/format";
import { useT } from "@/lib/i18n";

const shift = (month: string, n: number) => {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const monthName = (month: string, lang: string) =>
  new Date(month + "-01T00:00:00").toLocaleDateString(
    lang === "ar" ? "ar-MA" : lang === "fr" ? "fr-CH" : "en-GB",
    { month: "long", year: "numeric" });

/** The editable "assigned" cell: type a number or a sum such as 120+30. */
function AssignCell({ row, month, onSaved }: {
  row: EnvelopeRow; month: string; onSaved: (m: EnvelopeMonth) => void;
}) {
  const t = useT();
  const [text, setText] = useState(String(row.assigned));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setText(String(row.assigned)), [row.assigned]);
  if (row.category_id === null) return <span className="muted">—</span>;
  const save = async () => {
    const v = evalAmount(text);
    if (v === null) { setErr(t("Not a number")); return; }
    setErr(null);
    if (v === row.assigned) { setText(String(v)); return; }
    try {
      onSaved(await put<EnvelopeMonth>(`/api/envelopes/${month}/${row.category_id}`,
        { amount: String(v) }));
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Tooltip content={err ?? t("Type an amount or a sum like 120+30, then Enter")}
      relationship="description" visible={err ? true : undefined}>
      <Input className="env-input" size="small" value={text} inputMode="decimal"
        aria-label={t("Assigned to {c}", { c: row.name })}
        onChange={(_, d) => setText(d.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </Tooltip>
  );
}

function TargetBar({ row }: { row: EnvelopeRow }) {
  if (!row.target || row.need <= 0) return null;
  const share = Math.max(0, Math.min(1, row.assigned / row.need));
  return <div className="target-bar"><span style={{ width: `${share * 100}%` }} /></div>;
}

export function Envelopes({ lang }: { lang: string }) {
  const t = useT();
  const now = new Date();
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const view = useLoad(() => get<EnvelopeMonth>("/api/envelopes", { month }), [month]);
  const [move, setMove] = useState<{ to?: Id | null; from?: Id | null; amount?: number } | null>(null);
  const [target, setTarget] = useState<EnvelopeRow | null>(null);
  const [quick, setQuick] = useState<{ mode: string; data: QuickAssign } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const v = view.data;
  const cur = v?.currency ?? "";
  const rows = v ? v.groups.flatMap((g) => g.items) : [];
  const catOptions = rows.filter((r) => r.category_id !== null).map((r) => ({
    value: r.category_id as number,
    label: `${catLabel(r.name, t)} (${money(r.available)})`,
  }));

  const previewQuick = async (mode: string) => {
    try {
      setQuick({ mode, data: await post<QuickAssign>("/api/envelopes/quick-assign",
        { month, mode }) });
    } catch (e) { setError((e as Error).message); }
  };
  const ready = v?.ready_to_assign ?? 0;

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="month-nav">
          <Button appearance="subtle" icon={<ChevronLeft20Regular />} aria-label={t("Previous month")}
            onClick={() => setMonth(shift(month, -1))} />
          <span className="label">{monthName(month, lang)}</span>
          <Button appearance="subtle" icon={<ChevronRight20Regular />} aria-label={t("Next month")}
            onClick={() => setMonth(shift(month, 1))} />
        </div>
        <span className="grow" />
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button icon={<Flash20Regular />}>{t("Quick assign")}</Button>
          </MenuTrigger>
          <MenuPopover><MenuList>
            <MenuItem onClick={() => previewQuick("underfunded")}>{t("Fund what targets still need")}</MenuItem>
            <MenuItem onClick={() => previewQuick("last_month")}>{t("Assign the same as last month")}</MenuItem>
          </MenuList></MenuPopover>
        </Menu>
        <Button icon={<ArrowSwap20Regular />} onClick={() => setMove({})}>{t("Move money")}</Button>
      </div>
      {(error || view.error) && <Banner kind="error" onClose={() => setError(null)}>{error ?? view.error}</Banner>}
      {view.loading && !v && <Spinner />}
      {v && (
        <>
          <div className={`hero ${ready < 0 ? "bad" : ready > 0 ? "good" : ""}`}>
            <div>
              <div className="hero-label">{t("Ready to Assign")}</div>
              <div className="hero-value">{money(ready, cur)}</div>
              <div className="caption">
                {ready > 0 ? t("Give this money a job: type amounts in the Assigned column.")
                  : ready < 0 ? t("You assigned more than you have. Take money back from a category.")
                    : t("All your money has a job.")}
                {v.assigned_in_future > 0 && " " + t("{a} is assigned in later months.",
                  { a: money(v.assigned_in_future, cur) })}
              </div>
            </div>
            <div className="row" style={{ gap: 24 }}>
              <div><div className="hero-label">{t("Assigned")}</div>
                <div className="kpi-value">{money(v.total_assigned, cur)}</div></div>
              <div><div className="hero-label">{t("Activity")}</div>
                <div className="kpi-value">{money(v.total_activity, cur)}</div></div>
              <div><div className="hero-label">{t("Available")}</div>
                <div className="kpi-value">{money(v.total_available, cur)}</div></div>
            </div>
          </div>
          {v.overspent > 0 && (
            <Banner kind="warning" title={t("{a} overspent", { a: money(v.overspent, cur) })}>
              {t("Cover it by moving money from a category that has some left. Overspending that is not covered is taken from Ready to Assign next month.")}
            </Banner>)}
          {v.missing_fx.length > 0 && (
            <Banner kind="warning">{t("No exchange rate for {c}; those transactions are left out.",
              { c: v.missing_fx.join(", ") })}</Banner>)}
          <div className="card table-wrap" style={{ padding: "8px 12px" }}>
            <table className="env-table">
              <thead><tr>
                <th>{t("Category")}</th><th className="num">{t("Assigned")}</th>
                <th className="num">{t("Activity")}</th><th className="num">{t("Available")}</th>
                <th />
              </tr></thead>
              <tbody>
                {v.groups.map((g) => g.items.map((r, i) => (
                  <tr key={`${g.id}-${r.category_id}`}
                    className={i === 0 && g.items.length > 1 ? "env-group" : undefined}>
                    <td>
                      <div className="cat-cell" style={{ paddingInlineStart: r.parent_id ? 28 : 0 }}>
                        <CategoryIcon name={r.name} icon={r.icon} color={r.color} size={r.parent_id ? 28 : 32} />
                        <span>
                          <span className="cell-main">{catLabel(r.name, t)}</span>
                          {r.target && (
                            <span className="cell-sub">
                              {r.status === "underfunded"
                                ? t("{a} more needed this month", { a: money(r.shortfall) })
                                : t("Target: {a}", { a: money(r.need) })}
                              <TargetBar row={r} />
                            </span>)}
                        </span>
                      </div>
                    </td>
                    <td className="num"><AssignCell row={r} month={month} onSaved={view.setData} /></td>
                    <td className="num muted">{money(r.activity)}</td>
                    <td className="num">
                      <span className={`pill ${r.available === 0 && r.status === "ok" ? "zero" : r.status}`}>
                        {money(r.available)}</span>
                    </td>
                    <td className="actions">
                      {r.category_id !== null && (<>
                        {r.available < 0 && (
                          <Button size="small" appearance="subtle" onClick={() =>
                            setMove({ to: r.category_id, amount: -r.available })}>{t("Cover")}</Button>)}
                        <Tooltip content={t("Target")} relationship="label">
                          <Button size="small" appearance="subtle" icon={<Target20Regular />}
                            onClick={() => setTarget(r)} /></Tooltip>
                      </>)}
                    </td>
                  </tr>)))}
              </tbody>
            </table>
          </div>
          <p className="caption" style={{ marginTop: 8 }}>
            {t("Money left in a category carries over to next month. Ready to Assign counts the balances of checking, savings, cash and card accounts; transfers to investment or loan accounts leave the budget.")}</p>
        </>)}
      {move && (
        <FormModal title={t("Move money")} onClose={() => setMove(null)}
          initial={{ from: move.from ?? "", to: move.to ?? "", amount: move.amount ?? "" }}
          fields={[
            { name: "from", label: t("From"), type: "select",
              placeholder: t("Ready to Assign ({a})", { a: money(ready) }),
              options: catOptions },
            { name: "to", label: t("To"), type: "select",
              placeholder: t("Ready to Assign"), options: catOptions },
            { name: "amount", label: t("Amount ({cur})", { cur }), required: true,
              help: t("You can type a sum such as 40+15.") },
          ]}
          submitLabel={t("Move")}
          onSubmit={async (f) => {
            const amount = evalAmount(String(f.amount));
            if (amount === null || amount <= 0) throw new Error(t("Enter a positive amount."));
            view.setData(await post<EnvelopeMonth>("/api/envelopes/move", {
              month, amount: String(amount),
              from_category_id: f.from === "" || f.from === null ? null : Number(f.from),
              to_category_id: f.to === "" || f.to === null ? null : Number(f.to),
            }));
          }} />)}
      {target && (
        <FormModal title={t("Target for {c}", { c: catLabel(target.name, t) })}
          onClose={() => setTarget(null)}
          initial={{ kind: target.target?.kind ?? "monthly", amount: target.target?.amount ?? "",
            due_date: target.target?.due_date ?? "" }}
          fields={(f) => [
            { name: "kind", label: t("I need"), type: "select", required: true, options: [
              { value: "monthly", label: t("An amount every month") },
              { value: "weekly", label: t("An amount every week") },
              { value: "yearly", label: t("An amount every year (saved monthly)") },
              { value: "by_date", label: t("A total by a date") },
              { value: "none", label: t("No target") }] },
            { name: "amount", label: t("Amount ({cur})", { cur }), type: "number", step: "0.01",
              required: f.kind !== "none", hidden: f.kind === "none" },
            { name: "due_date", label: f.kind === "weekly" ? t("Weekday (pick any date on it)")
              : t("Needed by"), type: "date", required: f.kind === "by_date",
            hidden: f.kind === "monthly" || f.kind === "yearly" || f.kind === "none" },
          ]}
          onSubmit={async (f) => {
            if (f.kind === "none") {
              await removeTarget(target.category_id as number);
              view.reload();
              return;
            }
            await put(`/api/budget-targets/${target.category_id}`, {
              kind: f.kind, amount: String(f.amount),
              due_date: f.due_date ? String(f.due_date) : null });
            view.reload();
          }} />)}
      {quick && (
        <Modal title={quick.mode === "underfunded" ? t("Fund what targets still need")
          : t("Assign the same as last month")} onClose={() => setQuick(null)}
        actions={<>
          <Button appearance="primary" disabled={!quick.data.changes.length} onClick={async () => {
            await post("/api/envelopes/quick-assign", { month, mode: quick.mode, apply: true });
            setQuick(null);
            view.reload();
          }}>{t("Assign {a}", { a: money(quick.data.total, cur) })}</Button>
          <Button onClick={() => setQuick(null)}>{t("Cancel")}</Button></>}>
          {quick.data.changes.length === 0 ? (
            <p>{quick.mode === "underfunded"
              ? (ready <= 0 ? t("There is nothing in Ready to Assign to give.")
                : t("Every target is already funded this month."))
              : t("Last month has no assignments to repeat, or this month already has them.")}</p>) : (
            <table><thead><tr><th>{t("Category")}</th><th className="num">{t("Now")}</th>
              <th className="num">{t("After")}</th></tr></thead>
            <tbody>{quick.data.changes.map((c) => (
              <tr key={c.category_id}><td>{catLabel(c.name, t)}</td>
                <td className="num muted">{money(c.old)}</td>
                <td className="num">{money(c.new)}</td></tr>))}</tbody></table>)}
        </Modal>)}
    </>
  );
}

/** Remove a category's target (used from the target dialog's caller). */
export const removeTarget = (categoryId: Id) => del(`/api/budget-targets/${categoryId}`);
