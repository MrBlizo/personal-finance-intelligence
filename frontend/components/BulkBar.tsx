"use client";
import { useState } from "react";
import { Button, Select } from "@fluentui/react-components";
import { Delete20Regular, Edit20Regular } from "@fluentui/react-icons";
import { accountOptions, categoryOptions, useRefs } from "@/components/refs";
import { Confirm, FormModal } from "@/components/ui";
import { BulkResult, post } from "@/lib/api";
import { useT } from "@/lib/i18n";

const REASONS: Record<string, string> = {
  "investment trade": "investment trades",
  transfer: "transfers",
  split: "split transactions",
  reconciled: "reconciled transactions",
  "duplicate in target account": "duplicates in the target account",
};

/** "3 changed, 2 skipped (transfers, split transactions)." */
export function bulkMessage(r: BulkResult, t: ReturnType<typeof useT>): string {
  const head = r.deleted ? t("{n} deleted.", { n: r.deleted }) : t("{n} changed.", { n: r.updated });
  if (!r.skipped) return head;
  const why = Object.keys(r.reasons).map((k) => t(REASONS[k] ?? k)).join(", ");
  return `${head} ${t("{n} skipped ({why}).", { n: r.skipped, why })}`;
}

/** Actions for the selected transactions: category, account, tags,
 *  cleared and delete. */
export function BulkBar({ ids, onDone, onClear }: {
  ids: number[]; onDone: (message: string) => void; onClear: () => void;
}) {
  const t = useT();
  const refs = useRefs();
  const cats = refs.data?.categories ?? [];
  const accounts = refs.data?.accounts ?? [];
  const [cat, setCat] = useState("");
  const [edit, setEdit] = useState(false);
  const [remove, setRemove] = useState(false);
  const send = async (body: Record<string, unknown>) =>
    onDone(bulkMessage(await post<BulkResult>("/api/transactions/bulk", { ids, ...body }), t));
  const tags = (v: unknown) => String(v ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return (
    <div className="filters card bulk-bar">
      <b>{t("{n} selected", { n: ids.length })}</b>
      <Select value={cat} onChange={(_, d) => setCat(d.value)} aria-label={t("Category")}>
        <option value="">{t("Choose category…")}</option>
        {categoryOptions(cats, undefined, t).map((o) =>
          <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
      <Button appearance="primary" disabled={!cat}
        onClick={() => send({ category_id: Number(cat) }).then(() => setCat(""))}>
        {t("Apply category")}</Button>
      <Button icon={<Edit20Regular />} onClick={() => setEdit(true)}>{t("Edit selected…")}</Button>
      <Button icon={<Delete20Regular />} onClick={() => setRemove(true)}>{t("Delete")}</Button>
      <Button appearance="subtle" onClick={onClear}>{t("Clear selection")}</Button>
      {edit && (
        <FormModal title={t("Edit {n} transactions", { n: ids.length })} onClose={() => setEdit(false)}
          submitLabel={t("Apply")}
          initial={{ category: "", account_id: "", add_tags: "", remove_tags: "", cleared: "" }}
          fields={[
            { name: "category", label: t("Category"), type: "select", options: [
              { value: "__clear", label: t("Remove the category") },
              ...categoryOptions(cats, undefined, t)], placeholder: t("Keep as it is") },
            { name: "account_id", label: t("Move to account"), type: "select",
              options: accountOptions(accounts), placeholder: t("Keep as it is") },
            { name: "add_tags", label: t("Add tags"), placeholder: t("Holiday, Kids"),
              help: t("Separate several tags with commas.") },
            { name: "remove_tags", label: t("Remove tags") },
            { name: "cleared", label: t("Seen on the bank statement"), type: "select", options: [
              { value: "yes", label: t("Yes (cleared)") }, { value: "no", label: t("No") }],
              placeholder: t("Keep as it is") },
          ]}
          onSubmit={async (v) => {
            const body: Record<string, unknown> = {
              add_tags: tags(v.add_tags), remove_tags: tags(v.remove_tags) };
            if (v.category === "__clear") body.clear_category = true;
            else if (v.category) body.category_id = Number(v.category);
            if (v.account_id) body.account_id = Number(v.account_id);
            if (v.cleared) body.cleared = v.cleared === "yes";
            await send(body);
          }} />)}
      {remove && (
        <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(false)}
          text={t("Delete {n} transactions? For transfers, both sides are deleted. Reconciled transactions and investment trades are kept.",
            { n: ids.length })}
          onYes={() => send({ action: "delete" })} />)}
    </div>
  );
}
