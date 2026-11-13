"use client";
import { useMemo, useState } from "react";
import { Button, Checkbox, Field as FField, Input } from "@fluentui/react-components";
import { Banner, Confirm, Empty, Kpi, Modal, Spinner, useLoad } from "@/components/ui";
import { Account, ReconcileData, del, get, post } from "@/lib/api";
import { date, money, signClass, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

/** Compare an account with a bank statement: tick the transactions that
 *  appear on it until the difference is zero, then finish. */
export function ReconcileDialog({ account, onClose, onDone }: {
  account: Account; onClose: () => void; onDone: (message: string) => void;
}) {
  const t = useT();
  const [stmtDate, setStmtDate] = useState(today());
  const [balance, setBalance] = useState("");
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [undo, setUndo] = useState(false);
  const data = useLoad(() => get<ReconcileData>(`/api/accounts/${account.id}/reconcile`,
    { statement_date: stmtDate }), [stmtDate]);
  const d = data.data;
  const rows = d?.transactions ?? [];
  const tickedSum = useMemo(() => rows.filter((r) => ticked.has(r.id))
    .reduce((s, r) => s + Math.round(r.amount * 100), 0), [rows, ticked]);
  const target = balance.trim() === "" ? null : Math.round(Number(balance.replace(",", ".")) * 100);
  const cleared = d ? Math.round(d.cleared_balance * 100) + tickedSum : 0;
  const diff = target === null || Number.isNaN(target) ? null : target - cleared;
  const cur = account.currency;
  const finish = async () => {
    setError(null);
    try {
      const r = await post<{ reconciled: number }>(`/api/accounts/${account.id}/reconcile`, {
        statement_date: stmtDate, statement_balance: (target! / 100).toFixed(2), ids: [...ticked] });
      onDone(t("{name} is reconciled up to {d} ({n} transactions).",
        { name: account.name, d: date(stmtDate), n: r.reconciled }));
      onClose();
    } catch (e) { setError((e as Error).message); }
  };
  return (
    <Modal wide title={t("Reconcile {name}", { name: account.name })} onClose={onClose} actions={<>
      <Button appearance="primary" disabled={diff !== 0} onClick={finish}>{t("Finish")}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <div className="caption">
        {t("Enter the date and the closing balance printed on your bank statement, then tick every transaction that appears on it. When the difference is zero, finish: the ticked transactions are locked so the balance stays correct.")}
      </div>
      <div className="form-grid" style={{ marginTop: 12 }}>
        <FField label={t("Statement date")}>
          <Input type="date" value={stmtDate} onChange={(_, v) => { setStmtDate(v.value); setTicked(new Set()); }} />
        </FField>
        <FField label={t("Closing balance on the statement ({cur})", { cur })}>
          <Input type="number" step="0.01" value={balance} placeholder="1234.56"
            onChange={(_, v) => setBalance(v.value)} />
        </FField>
      </div>
      {d?.last && (
        <div className="caption" style={{ marginTop: 4 }}>
          {t("Last reconciled: {d}, balance {b}.", { d: date(d.last.statement_date), b: money(d.last.statement_balance, cur) })}{" "}
          <Button appearance="transparent" size="small" onClick={() => setUndo(true)}>{t("Undo it")}</Button>
        </div>)}
      {data.loading && !d && <Spinner />}
      {d && (
        <>
          <div className="kpis recon-kpis">
            <Kpi label={t("Cleared balance")} value={money(cleared / 100, cur)} />
            <Kpi label={t("Statement")}
              value={target === null || Number.isNaN(target) ? "—" : money(target / 100, cur)} />
            <Kpi label={t("Difference")} cls={diff === 0 ? "pos" : diff === null ? "" : "neg"}
              value={diff === null ? "—" : diff === 0 ? t("None") : money(diff / 100, cur)} />
          </div>
          {rows.length === 0 ? <Empty>{t("Every transaction up to this date is already cleared.")}</Empty> : (
            <div className="table-wrap" style={{ maxHeight: 360 }}>
              <table>
                <thead><tr>
                  <th style={{ width: 36 }}><Checkbox aria-label={t("Select all")}
                    checked={ticked.size === rows.length ? true : ticked.size ? "mixed" : false}
                    onChange={(_, v) => setTicked(v.checked ? new Set(rows.map((r) => r.id)) : new Set())} /></th>
                  <th>{t("Date")}</th><th>{t("Description")}</th><th className="num">{t("Amount")}</th>
                </tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id} className={ticked.has(r.id) ? "selected" : ""}
                    onClick={() => { const s = new Set(ticked); if (s.has(r.id)) s.delete(r.id); else s.add(r.id); setTicked(s); }}>
                    <td><Checkbox checked={ticked.has(r.id)} /></td>
                    <td>{date(r.txn_date)}</td>
                    <td><span className="cell-main">{r.description || "—"}</span>
                      {r.merchant && <span className="cell-sub">{r.merchant}</span>}</td>
                    <td className={`num ${signClass(r.amount)}`}>{money(r.amount, cur)}</td>
                  </tr>))}</tbody>
              </table>
            </div>)}
          <div className="caption" style={{ marginTop: 8 }}>
            {t("{n} ticked, {s}. Balance in PFI on that date: {b}.", {
              n: ticked.size, s: money(tickedSum / 100, cur), b: money(d.balance, cur) })}
          </div>
        </>)}
      {undo && (
        <Confirm text={t("Undo the reconciliation of {d}? The transactions stay marked as seen on the statement, but they can be edited again.",
          { d: d?.last ? date(d.last.statement_date) : "" })} onClose={() => setUndo(false)}
          onYes={async () => { await del(`/api/accounts/${account.id}/reconciliations/latest`); data.reload(); }} />)}
    </Modal>
  );
}
