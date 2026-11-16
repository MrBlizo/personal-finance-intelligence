"use client";
// Budgets for a week, a month or a custom range such as a trip.
import { useState } from "react";
import { Button, Tooltip } from "@fluentui/react-components";
import { Add20Regular, Delete20Regular, Edit20Regular } from "@fluentui/react-icons";
import { categoryOptions, useRefs } from "./refs";
import {
  Banner, Confirm, Empty, FormModal, Progress, Section, Spinner, useLoad,
} from "./ui";
import { PeriodBudget, TagInfo, del, get, post, put } from "@/lib/api";
import { date, money, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

export function PeriodBudgets() {
  const t = useT();
  const list = useLoad(() => get<PeriodBudget[]>("/api/period-budgets"));
  const refs = useRefs();
  const tags = useLoad(() => get<TagInfo[]>("/api/tags"));
  const [edit, setEdit] = useState<PeriodBudget | "new" | null>(null);
  const [remove, setRemove] = useState<PeriodBudget | null>(null);
  const cats = refs.data?.categories ?? [];
  const periodLabel = (p: string) => t(p === "weekly" ? "Every week"
    : p === "monthly" ? "Every month" : "Once");

  return (
    <Section title={t("Weekly, monthly and trip budgets")}
      sub={t("A limit for a period, for chosen categories or a tag such as “Holiday 2026”.")}
      actions={<Button icon={<Add20Regular />} onClick={() => setEdit("new")}>{t("Add")}</Button>}>
      {list.error && <Banner kind="error">{list.error}</Banner>}
      {list.loading && !list.data && <Spinner />}
      {list.data?.length === 0 && (
        <Empty>{t("No period budgets yet. Try a weekly groceries budget or one for a trip.")}</Empty>)}
      <div className="pb-grid">
        {list.data?.map((b) => {
          const c = b.current;
          const status = c.spent > b.amount ? "over"
            : (c.pct ?? 0) > 0.85 ? "at_risk" : "ok";
          const top = Math.max(b.amount, ...b.history.map((h) => h.spent), c.spent) || 1;
          return (
            <div key={b.id} className="card pb-card">
              <div className="row">
                <strong className="grow">{b.name}</strong>
                <Tooltip content={t("Edit")} relationship="label">
                  <Button size="small" appearance="subtle" icon={<Edit20Regular />}
                    onClick={() => setEdit(b)} /></Tooltip>
                <Tooltip content={t("Delete")} relationship="label">
                  <Button size="small" appearance="subtle" icon={<Delete20Regular />}
                    onClick={() => setRemove(b)} /></Tooltip>
              </div>
              <div className="caption">
                {periodLabel(b.period)} · {date(c.start)} – {date(c.end)}
                {b.tag && ` · #${b.tag}`}
                {b.categories.length > 0 && ` · ${b.categories.map((n) => t(n)).join(", ")}`}
              </div>
              <div className="row">
                <span className="kpi-value grow">{money(c.spent, b.currency)}</span>
                <span className="muted">{t("of {a}", { a: money(b.amount) })}</span>
              </div>
              <Progress value={c.pct ?? 0} status={status} />
              <div className="caption">
                {c.upcoming ? t("Starts on {d}", { d: date(c.start) })
                  : c.ended ? t("Ended. {a} left.", { a: money(c.remaining) })
                    : c.remaining < 0 ? t("{a} over", { a: money(-c.remaining) })
                      : t("{a} left · {d} days · {p} per day", {
                        a: money(c.remaining), d: c.days_left, p: money(c.per_day) })}
              </div>
              {b.history.length > 0 && (
                <div className="pb-history" title={t("Earlier periods")}>
                  {b.history.map((h) => (
                    <span key={h.start} className={h.spent > b.amount ? "over" : ""}
                      style={{ height: `${Math.max(4, (h.spent / top) * 100)}%` }}
                      title={`${date(h.start)}: ${money(h.spent, b.currency)}`} />))}
                  <span style={{ height: `${Math.max(4, (c.spent / top) * 100)}%`,
                    background: "var(--accent)" }} title={t("This period")} />
                </div>)}
            </div>);
        })}
      </div>
      {edit && (
        <FormModal title={edit === "new" ? t("Add a budget") : t("Edit {n}", { n: edit.name })}
          onClose={() => setEdit(null)} wide
          initial={edit === "new" ? { name: "", amount: "", period: "weekly", start_date: today(),
            end_date: "", tag_id: "", category_id: "" }
            : { name: edit.name, amount: edit.amount, period: edit.period,
              start_date: edit.start_date, end_date: edit.end_date ?? "",
              tag_id: edit.tag_id ?? "", category_id: edit.category_ids[0] ?? "" }}
          fields={(f) => [
            { name: "name", label: t("Name"), required: true, placeholder: t("e.g. Groceries this week") },
            { name: "amount", label: t("Limit"), type: "number", step: "0.01", required: true },
            { name: "period", label: t("Repeats"), type: "select", required: true, options: [
              { value: "weekly", label: t("Every week") },
              { value: "monthly", label: t("Every month") },
              { value: "custom", label: t("Once (a trip or project)") }] },
            { name: "start_date", label: f.period === "custom" ? t("From")
              : t("First day of the first period"), type: "date", required: true },
            { name: "end_date", label: t("To"), type: "date", required: f.period === "custom",
              hidden: f.period !== "custom" },
            { name: "category_id", label: t("Category"), type: "select",
              placeholder: t("All spending"), options: categoryOptions(cats, "expense", t),
              help: t("A parent category includes its sub-categories.") },
            { name: "tag_id", label: t("Only with tag"), type: "select", placeholder: t("Any"),
              options: (tags.data ?? []).map((g) => ({ value: g.id, label: g.name })) },
          ]}
          onSubmit={async (f) => {
            const body = {
              name: f.name, amount: String(f.amount), period: f.period,
              start_date: f.start_date, end_date: f.period === "custom" ? f.end_date || null : null,
              tag_id: f.tag_id ? Number(f.tag_id) : null,
              category_ids: f.category_id ? [Number(f.category_id)] : [],
            };
            if (edit === "new") await post("/api/period-budgets", body);
            else await put(`/api/period-budgets/${edit.id}`, body);
            list.reload();
          }} />)}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete the budget “{n}”? Transactions are not touched.", { n: remove.name })}
        onYes={async () => { await del(`/api/period-budgets/${remove.id}`); list.reload(); }} />}
    </Section>
  );
}
