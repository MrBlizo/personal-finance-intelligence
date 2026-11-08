"use client";
import { useState } from "react";
import { Badge, Button, Tooltip } from "@fluentui/react-components";
import {
  Add20Regular, ArrowSync20Regular, Delete20Regular, Edit20Regular,
} from "@fluentui/react-icons";
import { accountOptions, catLabel, categoryOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Section, Spinner, clean, useLoad,
} from "@/components/ui";
import { Recurring, Reminder, del, get, post, put } from "@/lib/api";
import { FREQUENCIES, date, money, signClass, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

const PER_MONTH: Record<string, number> = {
  weekly: 52 / 12, biweekly: 26 / 12, monthly: 1, quarterly: 1 / 3, yearly: 1 / 12,
};

export default function RecurringPage() {
  const t = useT();
  const refs = useRefs();
  const rec = useLoad(() => get<Recurring[]>("/api/recurring"));
  const due = useLoad(() => get<Reminder[]>("/api/reminders", { days: 30 }));
  const [edit, setEdit] = useState<Recurring | "new" | null>(null);
  const [remove, setRemove] = useState<Recurring | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const accounts = refs.data?.accounts ?? [];
  const cats = refs.data?.categories ?? [];
  const accOf = (id: number) => accounts.find((a) => a.id === id);
  const reload = () => { rec.reload(); due.reload(); };
  const active = (rec.data ?? []).filter((r) => r.is_active);
  const monthly = (sign: number) => active.filter((r) => Math.sign(r.amount) === sign)
    .reduce((s, r) => s + Math.abs(r.amount) * PER_MONTH[r.frequency], 0);
  const base = refs.data?.settings.base_currency ?? "CHF";

  return (
    <>
      <PageHead title={t("Bills & recurring")}
        sub={t("Salary, rent, subscriptions and other regular payments")}>
        <Button icon={<ArrowSync20Regular />} onClick={async () => {
          const r = await post<{ posted: number }>("/api/recurring/post-due");
          setMsg(t("Due payments posted: {n}.", { n: r.posted })); reload();
        }}>{t("Post due now")}</Button>
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setEdit("new")}>
          {t("Add recurring item")}</Button>
      </PageHead>
      {msg && <Banner kind="success" onClose={() => setMsg(null)}>{msg}</Banner>}
      {rec.error && <Banner kind="error">{rec.error}</Banner>}
      <div className="kpis">
        <Kpi label={t("Regular income per month")} value={money(monthly(1), base, 0)} cls="pos"
          sub={t("approximate, items in all currencies")} />
        <Kpi label={t("Regular costs per month")} value={money(monthly(-1), base, 0)} cls="neg"
          sub={t("approximate, items in all currencies")} />
        <Kpi label={t("Posted automatically")}
          value={`${active.filter((r) => r.auto_post).length} / ${active.length}`}
          sub={t("active items")} />
      </div>
      <div className="grid g-split">
        <Section title={t("Recurring items")}>
          {rec.loading && !rec.data && <Spinner />}
          {rec.data?.length === 0 && (
            <Empty action={<Button appearance="primary" onClick={() => setEdit("new")}>{t("Add recurring item")}</Button>}>
              {t("Add salary, rent, insurance… Items can post themselves and remind you before they are due. See Insights for detected subscriptions.")}</Empty>)}
          {!!rec.data?.length && (
            <div className="table-wrap">
              <table><thead><tr><th>{t("Name")}</th><th>{t("Every")}</th><th>{t("Next")}</th>
                <th className="num">{t("Amount")}</th><th>{t("Automation")}</th><th /></tr></thead>
                <tbody>{rec.data.map((r) => {
                  const acc = accOf(r.account_id);
                  return (
                    <tr key={r.id} style={{ opacity: r.is_active ? 1 : 0.5 }}>
                      <td><span className="cell-main">{r.name}</span>
                        <span className="cell-sub">{acc?.name}
                          {r.category_id ? ` · ${catLabel(cats.find((c) => c.id === r.category_id)?.full_name, t)}` : ""}
                        </span></td>
                      <td>{t(FREQUENCIES[r.frequency])}</td>
                      <td>{date(r.next_date)}</td>
                      <td className={`num ${signClass(r.amount)}`}>{money(r.amount, acc?.currency)}</td>
                      <td><div className="chips">
                        {r.auto_post && <Badge appearance="tint" color="brand">{t("Auto-post")}</Badge>}
                        {r.remind_days > 0 && <Badge appearance="tint" color="informative">
                          {t("Remind {n} d", { n: r.remind_days })}</Badge>}
                      </div></td>
                      <td className="actions">
                        <Tooltip content={t("Edit")} relationship="label">
                          <Button appearance="subtle" size="small" icon={<Edit20Regular />}
                            onClick={() => setEdit(r)} /></Tooltip>
                        <Tooltip content={t("Delete")} relationship="label">
                          <Button appearance="subtle" size="small" icon={<Delete20Regular />}
                            onClick={() => setRemove(r)} /></Tooltip>
                      </td>
                    </tr>);
                })}</tbody></table>
            </div>)}
        </Section>
        <Section title={t("Due in the next 30 days")}>
          {due.data?.length === 0 && <Empty>{t("Nothing due.")}</Empty>}
          {due.data?.map((r) => (
            <div className="list-row" key={r.key}>
              <span className="glyph" aria-hidden>{r.auto_post ? "" : ""}</span>
              <div className="grow">
                <span className="cell-main">{r.name}</span>
                <span className="cell-sub">{date(r.date)} · {r.days_left === 0 ? t("today")
                  : t("in {n} days", { n: r.days_left })} · {r.account}</span>
              </div>
              <span className={`num ${signClass(r.amount)}`}>{money(r.amount, r.currency)}</span>
            </div>))}
          <p className="caption" style={{ marginTop: 12 }}>
            {t("In the desktop app you get a Windows notification when an item enters its reminder window.")}</p>
        </Section>
      </div>
      {edit && (() => {
        const r = edit === "new" ? null : edit;
        const catKind = (type: unknown) => (type === "income" ? "income" : "expense");
        return (
          <FormModal wide title={r ? t("Edit {name}", { name: r.name }) : t("Add recurring item")}
            onClose={() => setEdit(null)}
            initial={r ? { ...r, type: r.amount > 0 ? "income" : "expense", amount: Math.abs(r.amount) } as never
              : { name: "", account_id: accountOptions(accounts)[0]?.value ?? "", type: "expense",
                category_id: "", amount: "", frequency: "monthly", start_date: today(), end_date: "",
                is_active: true, auto_post: false, remind_days: 3 }}
            onChange={(v) => {
              const cat = cats.find((c) => c.id === Number(v.category_id));
              return cat && cat.kind !== catKind(v.type) ? { ...v, category_id: "" } : v;
            }}
            fields={(v) => [
              { name: "name", label: t("Name"), required: true, full: true },
              { name: "type", label: t("Type"), type: "select", required: true,
                options: [{ value: "expense", label: t("Expense (money out)") },
                  { value: "income", label: t("Income (money in)") }] },
              { name: "amount", label: t("Amount"), type: "number", step: "0.01", required: true,
                help: t("Always positive; the type decides the direction.") },
              { name: "account_id", label: t("Account"), type: "select", required: true,
                options: accountOptions(accounts) },
              { name: "category_id", label: t("Category"), type: "select",
                options: categoryOptions(cats, catKind(v.type), t),
                help: t("Needed to recognise past payments of this item.") },
              { name: "frequency", label: t("Frequency"), type: "select", required: true,
                options: Object.entries(FREQUENCIES).map(([value, label]) => ({ value, label: t(label) })) },
              { name: "start_date", label: t("First date"), type: "date", required: true },
              { name: "end_date", label: t("End date (optional)"), type: "date" },
              { name: "remind_days", label: t("Remind me (days before, 0 = off)"), type: "number" },
              { name: "is_active", label: t("Active"), type: "switch" },
              { name: "auto_post", label: t("Post automatically on the due date"), type: "switch",
                help: t("Books the transaction for you from the next due date on. Past dates are never back-filled.") },
            ]}
            onSubmit={async (v) => {
              const b = clean(v, ["account_id", "category_id", "remind_days"]);
              const size = Math.abs(Number(b.amount));
              if (!(size > 0)) throw new Error(t("Enter an amount above 0."));
              const body = { name: b.name, account_id: b.account_id, category_id: b.category_id,
                amount: String(v.type === "income" ? size : -size), frequency: b.frequency,
                start_date: b.start_date, end_date: b.end_date, is_active: Boolean(b.is_active),
                auto_post: Boolean(b.auto_post), remind_days: b.remind_days ?? 0 };
              if (r) await put(`/api/recurring/${r.id}`, body); else await post("/api/recurring", body);
              reload();
            }} />);
      })()}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete the recurring item “{name}”? Transactions it already posted are kept.", { name: remove.name })}
        onYes={async () => { await del(`/api/recurring/${remove.id}`); reload(); }} />}
    </>
  );
}
