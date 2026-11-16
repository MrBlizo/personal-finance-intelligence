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
  const fmt2 = (n: number) => n.toFixed(2);
  const [text, setText] = useState(fmt2(row.assigned));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setText(fmt2(row.assigned)), [row.assigned]);
  if (row.category_id === null) return <span className="muted">—</span>;
  const save = async () => {
    const v = evalAmount(text);
    if (v === null) { setErr(t("Not a number")); return; }
    setErr(null);
    if (v === row.assigned) { setText(fmt2(v)); return; }
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

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="stat"><div className="stat-label">{label}</div><div className="stat-value">{value}</div></div>;
}

type Group = { key: string; label: string; items: EnvelopeRow[]; parentId: Id | null };

/** Category groups for the table: parents with their children, singles together. */
function buildGroups(v: EnvelopeMonth, t: ReturnType<typeof useT>): Group[] {
  const out: Group[] = [];
  const singles: EnvelopeRow[] = [];
  for (const g of v.groups) {
    if (g.items.length > 1) {
      const parent = g.items[0];
      const items = g.items.filter((r, i) => i > 0 || r.assigned !== 0 || r.activity !== 0 || r.available !== 0);
      out.push({ key: String(g.id), label: catLabel(parent.name, t), items, parentId: parent.category_id });
    } else singles.push(...g.items);
  }
  const plain = singles.filter((r) => r.category_id !== null);
  const none = singles.filter((r) => r.category_id === null);
  if (plain.length) out.push({ key: "singles", label: t("Other categories"), items: plain, parentId: null });
  if (none.length) out.push({ key: "none", label: t("Uncategorised"), items: none, parentId: null });
  return out;
}

const sum = (rows: EnvelopeRow[], k: "assigned" | "activity" | "available") =>
  rows.reduce((s, r) => s + r[k], 0);

function rowLabel(r: EnvelopeRow, g: Group, t: ReturnType<typeof useT>) {
  if (r.category_id === null) return t("Uncategorised spending");
  if (r.category_id === g.parentId) return t("{c} (general)", { c: catLabel(r.name, t) });
  return catLabel(r.name, t);
}

/** Status text and progress bar of one category row. */
function state(r: EnvelopeRow): { label: string; cls: string; share: number } {
  const funds = r.carry_in + r.assigned;
  const spent = -Math.min(0, r.activity);
  if (r.available < 0) return { label: "Overspent", cls: "overspent", share: 1 };
  if (r.status === "underfunded")
    return { label: "Underfunded", cls: "underfunded", share: r.need > 0 ? Math.min(1, r.assigned / r.need) : 0 };
  if (funds > 0 && r.available === 0 && spent > 0) return { label: "Fully spent", cls: "spent", share: 1 };
  if (funds > 0) return { label: "Funded", cls: "funded", share: Math.min(1, spent / funds) };
  return { label: "", cls: "none", share: 0 };
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
  const [filter, setFilter] = useState<"all" | "overspent" | "underfunded" | "available">("all");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Id | null>(null);
  const age = useLoad(() => get<{ age: number | null }>("/api/analytics/age-of-money", { months: 3 }), []);
  const qUnder = useLoad(() => post<QuickAssign>("/api/envelopes/quick-assign", { month, mode: "underfunded" }), [month, view.data]);
  const qLast = useLoad(() => post<QuickAssign>("/api/envelopes/quick-assign", { month, mode: "last_month" }), [month, view.data]);
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

  const groups = v ? buildGroups(v, t) : [];
  const counts = {
    overspent: rows.filter((r) => r.available < 0).length,
    underfunded: rows.filter((r) => r.status === "underfunded").length,
    available: rows.filter((r) => r.available > 0).length,
  };
  const keep = (r: EnvelopeRow) => filter === "all" ? true
    : filter === "overspent" ? r.available < 0
      : filter === "underfunded" ? r.status === "underfunded" : r.available > 0;
  const carried = rows.reduce((s, r) => s + r.carry_in, 0);
  const sel = selected === null ? null : rows.find((r) => r.category_id === selected) ?? null;

  return (
    <>
      <div className="budget-top">
        <div className="month-nav">
          <Button appearance="subtle" icon={<ChevronLeft20Regular />} aria-label={t("Previous month")}
            onClick={() => setMonth(shift(month, -1))} />
          <span className="label">{monthName(month, lang)}</span>
          <Button appearance="subtle" icon={<ChevronRight20Regular />} aria-label={t("Next month")}
            onClick={() => setMonth(shift(month, 1))} />
        </div>
        <span className="grow" />
        <Button icon={<ArrowSwap20Regular />} onClick={() => setMove({})}>{t("Move money")}</Button>
      </div>
      {(error || view.error) && <Banner kind="error" onClose={() => setError(null)}>{error ?? view.error}</Banner>}
      {view.loading && !v && <Spinner />}
      {v && (
        <>
          <div className="budget-stats">
            <div className={`unassigned ${ready < 0 ? "bad" : ready > 0 ? "good" : ""}`}>
              <div className="stat-label">{t("Ready to Assign")}</div>
              <div className="stat-big">{money(ready, cur)}</div>
              <div className="stat-note">{ready > 0 ? t("Give this money a job")
                : ready < 0 ? t("More assigned than you have") : t("All of it is assigned")}</div>
            </div>
            <Stat label={t("Assigned")} value={money(v.total_assigned, cur)} />
            <Stat label={t("Activity")} value={money(v.total_activity, cur)} />
            <Stat label={t("Available")} value={money(v.total_available, cur)} />
            <Stat label={t("Age of money")} value={age.data?.age == null ? "—"
              : t("{n} days", { n: age.data.age })} />
          </div>
          {v.missing_fx.length > 0 && (
            <Banner kind="warning">{t("No exchange rate for {c}; those transactions are left out.",
              { c: v.missing_fx.join(", ") })}</Banner>)}
          <div className="budget-layout">
            <div className="budget-main">
              <div className="budget-filters">
                {([["all", t("All"), null], ["overspent", t("Overspent"), counts.overspent],
                  ["underfunded", t("Underfunded"), counts.underfunded],
                  ["available", t("Money available"), counts.available]] as const).map(([k, label, n]) => (
                  <button key={k} className={`chip ${filter === k ? "on" : ""} ${k}`}
                    onClick={() => setFilter(k)}>
                    {label}{n !== null && <span className="count">{n}</span>}
                  </button>))}
                <span className="grow" />
                <Button size="small" appearance="subtle" onClick={() => setCollapsed(
                  collapsed.size ? new Set() : new Set(groups.map((g) => g.key)))}>
                  {collapsed.size ? t("Expand all") : t("Collapse all")}</Button>
              </div>
              <div className="card env-card">
                <table className="env-table">
                  <thead><tr>
                    <th>{t("Category")}</th><th className="num">{t("Assigned")}</th>
                    <th className="num">{t("Activity")}</th><th className="num">{t("Available")}</th>
                  </tr></thead>
                  <tbody>
                    {groups.map((g) => {
                      const items = g.items.filter(keep);
                      if (!items.length) return null;
                      const open = !collapsed.has(g.key);
                      return [
                        <tr key={`h-${g.key}`} className="env-group-row" onClick={() => {
                          const next = new Set(collapsed);
                          if (open) next.add(g.key); else next.delete(g.key);
                          setCollapsed(next);
                        }}>
                          <td><span className={`chev ${open ? "open" : ""}`}><ChevronRight20Regular /></span>
                            <span className="group-name">{g.label}</span>
                            <span className="count">{g.items.length}</span></td>
                          <td className="num">{money(sum(g.items, "assigned"))}</td>
                          <td className="num">{money(sum(g.items, "activity"))}</td>
                          <td className="num">{money(sum(g.items, "available"))}</td>
                        </tr>,
                        ...(open ? items.map((r) => (
                          <tr key={`${g.key}-${r.category_id}`}
                            className={`env-row ${r.category_id !== null && r.category_id === selected ? "selected" : ""}`}
                            onClick={() => setSelected(r.category_id === selected ? null : r.category_id)}>
                            <td>
                              <div className="cat-cell">
                                <CategoryIcon name={r.name} icon={r.icon} color={r.color} size={30} />
                                <div className="cat-text">
                                  <div className="cat-line">
                                    <span className="cell-main">{rowLabel(r, g, t)}</span>
                                    <span className={`state ${state(r).cls}`}>{t(state(r).label)}</span>
                                  </div>
                                  <div className={`bar ${state(r).cls}`}><span style={{ width: `${state(r).share * 100}%` }} /></div>
                                </div>
                              </div>
                            </td>
                            <td className="num" onClick={(e) => e.stopPropagation()}>
                              <AssignCell row={r} month={month} onSaved={view.setData} /></td>
                            <td className="num muted">{money(r.activity)}</td>
                            <td className="num">
                              <span className={`pill ${r.available === 0 && r.status === "ok" ? "zero" : r.available < 0 ? "overspent" : r.status === "underfunded" ? "underfunded" : "funded"}`}>
                                {money(r.available)}</span>
                            </td>
                          </tr>)) : []),
                      ];
                    })}
                  </tbody>
                  <tfoot><tr>
                    <td>{t("Total")}</td><td className="num">{money(v.total_assigned)}</td>
                    <td className="num">{money(v.total_activity)}</td>
                    <td className="num">{money(v.total_available)}</td>
                  </tr></tfoot>
                </table>
              </div>
              <p className="caption" style={{ marginTop: 8 }}>
                {t("Money left in a category carries over to next month. Ready to Assign counts the balances of checking, savings, cash and card accounts; transfers to investment or loan accounts leave the budget.")}</p>
            </div>
            <aside className="budget-side card">
              {sel ? (<>
                <div className="side-head">
                  <CategoryIcon name={sel.name} icon={sel.icon} color={sel.color} size={36} />
                  <div><h3>{catLabel(sel.name, t)}</h3>
                    <div className="caption">{monthName(month, lang)}</div></div>
                  <span className="grow" />
                  <Button size="small" appearance="subtle" onClick={() => setSelected(null)}>{t("Close")}</Button>
                </div>
                <dl className="ledger">
                  <dt>{t("Carried over")}</dt><dd>{money(sel.carry_in, cur)}</dd>
                  <dt>{t("Assigned")}</dt><dd>+ {money(sel.assigned, cur)}</dd>
                  <dt>{t("Activity")}</dt><dd>{money(sel.activity, cur)}</dd>
                  <dt className="total">{t("Available")}</dt><dd className="total">{money(sel.available, cur)}</dd>
                </dl>
                {sel.available < 0
                  ? <div className="side-note bad">{t("{a} overspent. Cover it from a category that has money left.", { a: money(-sel.available, cur) })}</div>
                  : sel.status === "underfunded"
                    ? <div className="side-note warn">{t("{a} more needed this month", { a: money(sel.shortfall, cur) })}</div>
                    : sel.target ? <div className="side-note good">{t("You've met this month's target.")}</div> : null}
                <div className="side-title">{t("Target")}</div>
                <p className="caption">{sel.target ? t("Target: {a}", { a: money(sel.need, cur) }) : t("No target yet.")}</p>
                <div className="side-actions">
                  <Button icon={<Target20Regular />} onClick={() => setTarget(sel)}>
                    {sel.target ? t("Edit target") : t("Set a target")}</Button>
                  {sel.available < 0 && <Button appearance="primary" onClick={() =>
                    setMove({ to: sel.category_id, amount: -sel.available })}>{t("Cover")}</Button>}
                  <Button icon={<ArrowSwap20Regular />} onClick={() =>
                    setMove({ from: sel.category_id })}>{t("Move money")}</Button>
                </div>
              </>) : (<>
                <h3>{t("This month")}</h3>
                <p className="caption">{t("Select a category to see its details.")}</p>
                <dl className="ledger">
                  <dt>{t("Carried over")}</dt><dd>{money(carried, cur)}</dd>
                  <dt>{t("Assigned")}</dt><dd>+ {money(v.total_assigned, cur)}</dd>
                  <dt>{t("Activity")}</dt><dd>{money(v.total_activity, cur)}</dd>
                  <dt className="total">{t("Available")}</dt><dd className="total">{money(v.total_available, cur)}</dd>
                </dl>
                {v.overspent > 0
                  ? <div className="side-note bad">{t("{a} overspent", { a: money(v.overspent, cur) })}</div>
                  : v.underfunded > 0
                    ? <div className="side-note warn">{t("{a} still needed for targets", { a: money(v.underfunded, cur) })}</div>
                    : <div className="side-note good">{t("This month's funding is complete")}</div>}
                <div className="side-title">{t("Quick assign")}</div>
                <p className="caption">{t("Each option shows its changes first.")}</p>
                <button className="quick" onClick={() => previewQuick("underfunded")}>
                  <Flash20Regular /><span>{t("Fund targets")}</span>
                  <b>{qUnder.data ? money(qUnder.data.total) : "…"}</b></button>
                <button className="quick" onClick={() => previewQuick("last_month")}>
                  <Flash20Regular /><span>{t("Assigned last month")}</span>
                  <b>{qLast.data ? money(qLast.data.total) : "…"}</b></button>
              </>)}
            </aside>
          </div>
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
