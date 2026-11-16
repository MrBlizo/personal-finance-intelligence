"use client";
// Money lent to or borrowed from people, outside the accounts.
import { useState } from "react";
import { Badge, Button, Tab, TabList, Tooltip } from "@fluentui/react-components";
import {
  Add20Regular, Checkmark20Regular, Delete20Regular, Edit20Regular, Money20Regular,
} from "@fluentui/react-icons";
import { useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Section, Spinner, useLoad,
} from "@/components/ui";
import { Iou, IouSummary, del, get, post, put } from "@/lib/api";
import { evalAmount } from "@/lib/calc";
import { date, money, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function Ious() {
  const t = useT();
  const refs = useRefs();
  const data = useLoad(() => get<IouSummary>("/api/ious"));
  const [show, setShow] = useState<"open" | "settled">("open");
  const [edit, setEdit] = useState<Iou | "lent" | "borrowed" | null>(null);
  const [pay, setPay] = useState<Iou | null>(null);
  const [remove, setRemove] = useState<Iou | null>(null);
  const d = data.data;
  const cur = d?.currency ?? "";
  const base = refs.data?.settings.base_currency ?? "CHF";
  const items = (d?.items ?? []).filter((i) => (show === "open") === !i.settled_on);

  return (
    <>
      <PageHead title={t("Lent & borrowed")}
        sub={t("Who owes you money and whom you owe, with repayments.")}>
        <Button icon={<Add20Regular />} onClick={() => setEdit("borrowed")}>{t("I borrowed")}</Button>
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setEdit("lent")}>{t("I lent")}</Button>
      </PageHead>
      {data.error && <Banner kind="error">{data.error}</Banner>}
      {data.loading && !d && <Spinner />}
      {d && (<>
        <div className="kpis">
          <Kpi label={t("Owed to you")} value={money(d.owed_to_me, cur)} cls="pos" />
          <Kpi label={t("You owe")} value={money(d.owed_by_me, cur)} cls={d.owed_by_me ? "neg" : ""} />
          <Kpi label={t("Net")} value={money(d.owed_to_me - d.owed_by_me, cur)} />
        </div>
        {d.people.length > 0 && (
          <Section title={t("By person")}>
            {d.people.map((p) => (
              <div key={p.person} className="list-row">
                <span className="grow">{p.person}</span>
                <span className={p.balance > 0 ? "pos" : "neg"}>
                  {p.balance > 0 ? t("owes you {a}", { a: money(p.balance, cur) })
                    : t("you owe {a}", { a: money(-p.balance, cur) })}</span>
              </div>))}
          </Section>)}
        <Section>
          <TabList selectedValue={show} onTabSelect={(_, v) => setShow(v.value as "open" | "settled")}>
            <Tab value="open">{t("Open")}</Tab><Tab value="settled">{t("Settled")}</Tab>
          </TabList>
          {items.length === 0 ? <Empty>{show === "open"
            ? t("Nothing open. Add money you lent or borrowed.") : t("Nothing settled yet.")}</Empty> : (
            <div className="table-wrap"><table>
              <thead><tr><th>{t("Person")}</th><th>{t("Date")}</th><th className="num">{t("Amount")}</th>
                <th className="num">{t("Paid back")}</th><th className="num">{t("Open")}</th><th>{t("Due")}</th><th /></tr></thead>
              <tbody>{items.map((i) => (
                <tr key={i.id}>
                  <td><span className="cell-main">{i.person}</span>
                    <span className="cell-sub">{i.direction === "lent" ? t("You lent") : t("You borrowed")}
                      {i.note ? ` · ${i.note}` : ""}</span></td>
                  <td>{date(i.iou_date)}</td>
                  <td className={`num ${i.direction === "lent" ? "pos" : "neg"}`}>{money(i.amount, i.currency)}</td>
                  <td className="num muted">{money(i.repaid)}</td>
                  <td className="num">{i.settled_on ? <Badge appearance="tint" color="success">
                    {t("Settled {d}", { d: date(i.settled_on) })}</Badge> : money(i.open)}</td>
                  <td>{i.due_date ? (i.overdue ? <Badge appearance="tint" color="danger">
                    {t("Overdue since {d}", { d: date(i.due_date) })}</Badge> : date(i.due_date)) : "—"}</td>
                  <td className="actions">
                    {!i.settled_on && <>
                      <Tooltip content={t("Record a repayment")} relationship="label">
                        <Button size="small" appearance="subtle" icon={<Money20Regular />} onClick={() => setPay(i)} /></Tooltip>
                      <Tooltip content={t("Mark as fully paid back today")} relationship="label">
                        <Button size="small" appearance="subtle" icon={<Checkmark20Regular />} onClick={async () => {
                          await post(`/api/ious/${i.id}/settle`); data.reload();
                        }} /></Tooltip></>}
                    <Tooltip content={t("Edit")} relationship="label">
                      <Button size="small" appearance="subtle" icon={<Edit20Regular />} onClick={() => setEdit(i)} /></Tooltip>
                    <Tooltip content={t("Delete")} relationship="label">
                      <Button size="small" appearance="subtle" icon={<Delete20Regular />} onClick={() => setRemove(i)} /></Tooltip>
                  </td>
                </tr>))}</tbody>
            </table></div>)}
          <p className="caption">{t("These records do not change your account balances. If the money went through an account, add that transaction too.")}</p>
        </Section>
      </>)}
      {edit && (() => {
        const x = typeof edit === "object" ? edit : null;
        const direction = x ? x.direction : edit;
        return (
          <FormModal title={x ? t("Edit") : direction === "lent" ? t("I lent money") : t("I borrowed money")}
            onClose={() => setEdit(null)}
            initial={x ? { person: x.person, amount: x.amount, currency: x.currency, iou_date: x.iou_date,
              due_date: x.due_date ?? "", note: x.note ?? "" }
              : { person: "", amount: "", currency: base, iou_date: today(), due_date: "", note: "" }}
            fields={[
              { name: "person", label: direction === "lent" ? t("To whom") : t("From whom"), required: true },
              { name: "amount", label: t("Amount"), required: true, help: t("Sums like 50+20 work.") },
              { name: "currency", label: t("Currency"), required: true },
              { name: "iou_date", label: t("Date"), type: "date", required: true },
              { name: "due_date", label: t("To be paid back by"), type: "date" },
              { name: "note", label: t("Note"), full: true },
            ]}
            onSubmit={async (v) => {
              const amount = evalAmount(String(v.amount));
              if (!amount || amount <= 0) throw new Error(t("Enter an amount above 0."));
              const body = { person: v.person, direction, amount: String(amount),
                currency: String(v.currency).toUpperCase(), iou_date: v.iou_date,
                due_date: v.due_date || null, note: v.note || null };
              if (x) await put(`/api/ious/${x.id}`, body); else await post("/api/ious", body);
              data.reload();
            }} />);
      })()}
      {pay && (
        <FormModal title={t("Repayment: {p}", { p: pay.person })} onClose={() => setPay(null)}
          initial={{ paid_on: today(), amount: pay.open, note: "" }}
          fields={[
            { name: "amount", label: t("Amount ({cur})", { cur: pay.currency }), required: true },
            { name: "paid_on", label: t("Date"), type: "date", required: true },
            { name: "note", label: t("Note"), full: true },
          ]}
          onSubmit={async (v) => {
            const amount = evalAmount(String(v.amount));
            if (!amount || amount <= 0) throw new Error(t("Enter an amount above 0."));
            await post(`/api/ious/${pay.id}/payments`, { paid_on: v.paid_on, amount: String(amount),
              note: v.note || null });
            data.reload();
          }} />)}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete this record with {p} and its repayments?", { p: remove.person })}
        onYes={async () => { await del(`/api/ious/${remove.id}`); data.reload(); }} />}
    </>
  );
}
