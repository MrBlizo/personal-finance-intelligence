"use client";
// Month-by-month schedule of one loan or card, and the payment needed to be
// debt-free by a chosen date.
import { useState } from "react";
import { Button, Field, Input } from "@fluentui/react-components";
import { Banner, Kpi, Modal, Spinner, useLoad } from "./ui";
import { Id, LoanSchedule, get } from "@/lib/api";
import { evalAmount } from "@/lib/calc";
import { date, money } from "@/lib/format";
import { useT } from "@/lib/i18n";

export function LoanScheduleDialog({ accountId, name, onClose }: {
  accountId: Id; name: string; onClose: () => void;
}) {
  const t = useT();
  const [payment, setPayment] = useState("");
  const [finishBy, setFinishBy] = useState("");
  const pay = evalAmount(payment);
  const data = useLoad(() => get<LoanSchedule>(`/api/debts/${accountId}/schedule`, {
    payment: pay ?? undefined, finish_by: finishBy || undefined }), [pay, finishBy]);
  const d = data.data;
  const s = d?.schedule;
  const [all, setAll] = useState(false);
  const rows = s ? (all ? s.rows : s.rows.slice(0, 24)) : [];
  return (
    <Modal wide title={t("{name}: repayment schedule", { name })} onClose={onClose}
      actions={<Button onClick={onClose}>{t("Close")}</Button>}>
      <div className="form-grid">
        <Field label={t("Monthly payment")} hint={d ? t("Leave empty for the minimum payment ({a}).",
          { a: money(d.payment, d.currency) }) : undefined}>
          <Input value={payment} inputMode="decimal" onChange={(_, v) => setPayment(v.value)}
            placeholder={d ? String(d.payment) : ""} />
        </Field>
        <Field label={t("Debt-free by")} hint={t("Shows the payment needed to finish by this date.")}>
          <Input type="date" value={finishBy} onChange={(_, v) => setFinishBy(v.value)} />
        </Field>
      </div>
      {data.error && <Banner kind="error">{data.error}</Banner>}
      {data.loading && !d && <Spinner />}
      {d && s && (<>
        {d.payment_to_finish !== undefined && (
          <Banner kind="info" title={t("Pay {a} a month to be debt-free by {d}",
            { a: money(d.payment_to_finish, d.currency), d: date(d.finish_by ?? "") })}>
            {d.payment_to_finish > d.payment
              ? t("That is {a} more than you pay now.", { a: money(d.payment_to_finish - d.payment, d.currency) })
              : t("Your current payment already gets you there.")}
          </Banner>)}
        {s.never ? (
          <Banner kind="warning">{t("This payment does not cover the monthly interest, so the debt never shrinks. Raise the payment.")}</Banner>
        ) : (
          <div className="kpis">
            <Kpi label={t("Owed now")} value={money(d.owed, d.currency)} />
            <Kpi label={t("Paid off")} value={s.payoff_date ? date(s.payoff_date) : "—"}
              sub={t("{n} payments", { n: s.months ?? 0 })} />
            <Kpi label={t("Total interest")} value={money(s.total_interest, d.currency)} />
          </div>)}
        {rows.length > 0 && (
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table>
              <thead><tr><th>{t("Month")}</th><th className="num">{t("Payment")}</th>
                <th className="num">{t("Interest")}</th><th className="num">{t("Principal")}</th>
                <th className="num">{t("Left to pay")}</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.date}><td>{date(r.date)}</td><td className="num">{money(r.payment)}</td>
                  <td className="num muted">{money(r.interest)}</td><td className="num">{money(r.principal)}</td>
                  <td className="num">{money(r.balance)}</td></tr>))}</tbody>
            </table>
          </div>)}
        {s.rows.length > 24 && !all && (
          <Button appearance="subtle" onClick={() => setAll(true)}>
            {t("Show all {n} months", { n: s.rows.length })}</Button>)}
        <p className="caption">{t("An estimate in {cur}: interest is charged monthly at the yearly rate ÷ 12 on what is left.",
          { cur: d.currency })}</p>
      </>)}
    </Modal>
  );
}
