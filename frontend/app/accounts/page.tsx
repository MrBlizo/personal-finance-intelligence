"use client";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Link as FLink, Switch, Tooltip } from "@fluentui/react-components";
import { Add20Regular, Delete20Regular, Edit20Regular } from "@fluentui/react-icons";
import { useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, PageHead, Spinner, clean,
} from "@/components/ui";
import { Account, del, post, put } from "@/lib/api";
import { ACCOUNT_TYPES, CURRENCIES, money, signClass, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

const GLYPH: Record<string, string> = {
  checking: "", savings: "", cash: "", credit_card: "",
  investment: "", loan: "",
};

export default function Accounts() {
  const t = useT();
  const refs = useRefs();
  const [edit, setEdit] = useState<Account | "new" | null>(null);
  const [remove, setRemove] = useState<Account | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const base = refs.data?.settings.base_currency ?? "CHF";
  const accounts = (refs.data?.accounts ?? []).filter((a) => showArchived || !a.is_archived);
  const total = (types: string[]) => accounts.filter((a) => types.includes(a.type))
    .reduce((s, a) => s + (a.balance_base ?? 0) + a.holdings_base, 0);
  const missing = accounts.filter((a) => a.balance_base === null);

  return (
    <>
      <PageHead title={t("Accounts")} sub={t("Bank accounts, cards, cash, investments and loans")}>
        <Switch label={t("Show archived")} checked={showArchived}
          onChange={(_, d) => setShowArchived(d.checked)} />
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setEdit("new")}>
          {t("Add account")}</Button>
      </PageHead>
      {refs.error && <Banner kind="error">{refs.error}</Banner>}
      {missing.length > 0 && (
        <Banner kind="warning"
          action={<Link href="/settings/"><Button size="small">{t("Open settings")}</Button></Link>}>
          {t("{list} cannot be converted to {cur}. Add an exchange rate.", {
            list: missing.map((a) => a.currency).filter((c, i, l) => l.indexOf(c) === i).join(", "),
            cur: base })}
        </Banner>)}
      {refs.loading && !refs.data && <Spinner />}
      {refs.data && (
        <>
          <div className="kpis">
            <Kpi label={t("Liquid")} value={money(total(["checking", "savings", "cash", "credit_card"]), base)} />
            <Kpi label={t("Investments")} value={money(total(["investment"]), base)} />
            <Kpi label={t("Loans")} value={money(total(["loan"]), base)} />
            <Kpi label={t("Net worth")} value={money(total(Object.keys(ACCOUNT_TYPES)), base)} />
          </div>
          <div className="card table-wrap" style={{ padding: "4px 8px" }}>
            {accounts.length === 0 ? (
              <Empty action={<Button appearance="primary" onClick={() => setEdit("new")}>
                {t("Add account")}</Button>}>
                {t("No accounts yet. Add your first account to start.")}</Empty>) : (
              <table>
                <thead><tr><th>{t("Name")}</th><th>{t("Type")}</th><th>{t("Institution")}</th>
                  <th className="num">{t("Balance")}</th>
                  <th className="num">{t("In {cur}", { cur: base })}</th><th /></tr></thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id} style={{ opacity: a.is_archived ? 0.55 : 1 }}>
                      <td><div className="row">
                        <span className="glyph" aria-hidden>{GLYPH[a.type]}</span>
                        <Link href={`/transactions/?account=${a.id}`}>
                          <FLink as="span">{a.name}</FLink></Link>
                        {a.is_demo && <Badge appearance="tint" color="informative">{t("demo")}</Badge>}
                        {a.is_archived && <Badge appearance="tint">{t("archived")}</Badge>}
                      </div></td>
                      <td>{t(ACCOUNT_TYPES[a.type])}</td>
                      <td className="muted">{a.institution ?? ""}</td>
                      <td className={`num ${signClass(a.balance)}`}>{money(a.balance, a.currency)}
                        {a.holdings_base > 0 && <span className="cell-sub">
                          {t("+ holdings {v}", { v: money(a.holdings_base, base) })}</span>}</td>
                      <td className="num">{money((a.balance_base ?? NaN) + a.holdings_base)}</td>
                      <td className="actions">
                        <Tooltip content={t("Edit")} relationship="label">
                          <Button appearance="subtle" size="small" icon={<Edit20Regular />}
                            onClick={() => setEdit(a)} /></Tooltip>
                        <Tooltip content={t("Delete")} relationship="label">
                          <Button appearance="subtle" size="small" icon={<Delete20Regular />}
                            onClick={() => setRemove(a)} /></Tooltip>
                      </td>
                    </tr>))}
                </tbody>
              </table>)}
          </div>
        </>)}

      {edit && (() => {
        const a = edit === "new" ? null : edit;
        return (
          <FormModal title={a ? t("Edit {name}", { name: a.name }) : t("Add account")}
            onClose={() => setEdit(null)}
            initial={a ? { ...a } as never : {
              name: "", type: "checking", currency: base, institution: "",
              opening_balance: "0", opening_date: today(), is_archived: false, notes: "",
            }}
            fields={[
              { name: "name", label: t("Name"), required: true, full: true },
              { name: "type", label: t("Type"), type: "select", required: true,
                options: Object.entries(ACCOUNT_TYPES).map(([value, label]) => ({ value, label: t(label) })) },
              { name: "currency", label: t("Currency"), type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
              { name: "institution", label: t("Bank / institution") },
              { name: "opening_date", label: t("Opening date"), type: "date", required: true },
              { name: "opening_balance", label: t("Opening balance"), type: "number", step: "0.01",
                help: t("Balance on the opening date, before any transaction you enter or import.") },
              { name: "is_archived", label: t("Archived (hidden from lists and forecast)"),
                type: "switch", full: true },
              { name: "notes", label: t("Notes"), type: "textarea", full: true },
            ]}
            onSubmit={async (v) => {
              const b = clean(v);
              const body = { ...b, opening_balance: String(b.opening_balance ?? "0") };
              if (a) await put(`/api/accounts/${a.id}`, body);
              else await post("/api/accounts", body);
              refs.reload();
            }} />);
      })()}
      {remove && (
        <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
          text={t("Delete “{name}” and all its transactions? This cannot be undone. To keep the history, edit the account and switch on “Archived” instead.",
            { name: remove.name })}
          onYes={async () => { await del(`/api/accounts/${remove.id}`, { confirm: true }); refs.reload(); }} />)}
    </>
  );
}
