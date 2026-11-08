"use client";
import { useState } from "react";
import { Button, Menu, MenuItem, MenuList, MenuPopover, MenuTrigger } from "@fluentui/react-components";
import { Add20Regular, MoreHorizontal20Regular } from "@fluentui/react-icons";
import { accountOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, PageHead, Progress, Spinner, StatusBadge,
  clean, useLoad,
} from "@/components/ui";
import { Goal, del, get, post, put } from "@/lib/api";
import { CURRENCIES, date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function Goals() {
  const t = useT();
  const refs = useRefs();
  const goals = useLoad(() => get<Goal[]>("/api/goals"));
  const [edit, setEdit] = useState<Goal | "new" | null>(null);
  const [remove, setRemove] = useState<Goal | null>(null);
  const accounts = refs.data?.accounts ?? [];

  return (
    <>
      <PageHead title={t("Savings goals")}
        sub={t("Link a goal to a savings account to track it automatically")}>
        <Button appearance="primary" icon={<Add20Regular />} onClick={() => setEdit("new")}>
          {t("Add goal")}</Button>
      </PageHead>
      {goals.error && <Banner kind="error">{goals.error}</Banner>}
      {goals.loading && !goals.data && <Spinner />}
      {goals.data?.length === 0 && (
        <div className="card"><Empty action={<Button appearance="primary" onClick={() => setEdit("new")}>
          {t("Add goal")}</Button>}>
          {t("No goals yet, for example an emergency fund of 3–6 months of expenses.")}</Empty></div>)}
      <div className="grid g3">
        {goals.data?.map((g) => {
          const acc = accounts.find((a) => a.id === g.account_id);
          return (
            <section className="card section" key={g.id}>
              <div className="section-head" style={{ marginBottom: 8 }}>
                <div><h2>{g.name}</h2>
                  <div className="caption">{acc ? t("Tracked from {a}", { a: acc.name }) : t("Manual amount")}</div></div>
                <div className="row">
                  <StatusBadge status={g.status} />
                  <Menu>
                    <MenuTrigger disableButtonEnhancement>
                      <Button appearance="subtle" size="small" icon={<MoreHorizontal20Regular />}
                        aria-label={t("More")} /></MenuTrigger>
                    <MenuPopover><MenuList>
                      <MenuItem onClick={() => setEdit(g)}>{t("Edit")}</MenuItem>
                      <MenuItem onClick={() => setRemove(g)}>{t("Delete")}</MenuItem>
                    </MenuList></MenuPopover>
                  </Menu>
                </div>
              </div>
              <div className="kpi-value">{money(g.saved_amount, g.currency, 0)}</div>
              <div className="caption" style={{ marginBottom: 8 }}>
                {t("of {v}", { v: money(g.target_amount, undefined, 0) })} · {pct(g.progress, 0)}</div>
              <Progress value={g.progress} status={g.status === "completed" ? "achieved" : undefined} />
              <table style={{ marginTop: 12, fontSize: 12 }}><tbody>
                <tr><td>{t("Target date")}</td><td className="num">{date(g.target_date)}</td></tr>
                <tr><td>{t("Needed per month")}</td><td className="num">{money(g.required_monthly, g.currency, 0)}</td></tr>
                <tr><td>{t("Saved per month (last 90 days)")}</td><td className="num">{money(g.recent_monthly_saving, g.currency, 0)}</td></tr>
                <tr><td>{t("Projected completion")}</td><td className="num">{date(g.projected_completion)}</td></tr>
              </tbody></table>
              {g.note && <div className="caption" style={{ marginTop: 8 }}>{g.note}</div>}
            </section>);
        })}
      </div>
      {edit && (() => {
        const g = edit === "new" ? null : edit;
        return (
          <FormModal title={g ? t("Edit {name}", { name: g.name }) : t("Add savings goal")}
            onClose={() => setEdit(null)}
            initial={g ? { name: g.name, target_amount: g.target_amount, currency: g.currency,
              target_date: g.target_date, account_id: g.account_id, saved_amount: g.manual_saved_amount,
              priority: g.priority, notes: g.notes }
              : { name: "", target_amount: "", currency: refs.data?.settings.base_currency ?? "CHF",
                target_date: "", account_id: "", saved_amount: "0", priority: 0, notes: "" }}
            fields={[
              { name: "name", label: t("Name"), required: true, full: true },
              { name: "target_amount", label: t("Target amount"), type: "number", step: "0.01", required: true },
              { name: "currency", label: t("Currency"), type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
              { name: "target_date", label: t("Target date"), type: "date" },
              { name: "account_id", label: t("Linked account"), type: "select", options: accountOptions(accounts),
                help: t("Balance of this account counts as saved.") },
              { name: "saved_amount", label: t("Saved so far (if no account)"), type: "number", step: "0.01" },
              { name: "priority", label: t("Priority (higher first)"), type: "number" },
              { name: "notes", label: t("Notes"), type: "textarea", full: true },
            ]}
            onSubmit={async (v) => {
              const b = clean(v, ["account_id", "priority"]);
              const body = { ...b, target_amount: String(b.target_amount),
                saved_amount: String(b.saved_amount ?? 0), priority: b.priority ?? 0 };
              if (g) await put(`/api/goals/${g.id}`, body); else await post("/api/goals", body);
              goals.reload();
            }} />);
      })()}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete the goal “{name}”?", { name: remove.name })}
        onYes={async () => { await del(`/api/goals/${remove.id}`); goals.reload(); }} />}
    </>
  );
}
