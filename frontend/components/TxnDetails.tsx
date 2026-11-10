"use client";
import { useRef, useState } from "react";
import { Button, Field as FField, Input, Select } from "@fluentui/react-components";
import {
  Add20Regular, Attach20Regular, Delete20Regular, Dismiss12Regular,
} from "@fluentui/react-icons";
import { categoryOptions, useRefs } from "@/components/refs";
import { Banner, Modal, Spinner, useLoad } from "@/components/ui";
import { Attachment, TagInfo, Txn, api, del, downloadUrl, get, put } from "@/lib/api";
import { money, num } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Part = { category_id: string; amount: string; note: string };

const toCents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100);

/** Tags, split and receipts of one transaction. */
export function TxnDetails({ txn, onClose, onChanged }: {
  txn: Txn; onClose: () => void; onChanged: () => void;
}) {
  const t = useT();
  const refs = useRefs();
  const cats = refs.data?.categories ?? [];
  const allTags = useLoad(() => get<TagInfo[]>("/api/tags"));
  const files = useLoad(() => get<Attachment[]>(`/api/transactions/${txn.id}/attachments`));
  const upload = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>(txn.tags);
  const [tagInput, setTagInput] = useState("");
  const sign = txn.amount < 0 ? -1 : 1;
  const [parts, setParts] = useState<Part[]>(txn.splits.length
    ? txn.splits.map((p) => ({ category_id: p.category_id ? String(p.category_id) : "",
      amount: String(Math.abs(p.amount)), note: p.note ?? "" }))
    : [{ category_id: txn.category_id ? String(txn.category_id) : "", amount: String(Math.abs(txn.amount)), note: "" },
      { category_id: "", amount: "0", note: "" }]);
  const splittable = txn.kind !== "transfer" && !txn.trade_id;
  const kind = txn.kind === "income" ? "income" : "expense";
  const target = Math.round(Math.abs(txn.amount) * 100);
  const total = parts.reduce((s, p) => s + (toCents(p.amount) || 0), 0);
  const rest = target - total;

  const wrap = async (f: () => Promise<string>) => {
    setError(null); setNote(null);
    try { setNote(await f()); onChanged(); }
    catch (e) { setError((e as Error).message); }
  };
  const saveTags = (next: string[]) => wrap(async () => {
    const saved = await put<string[]>(`/api/transactions/${txn.id}/tags`, { tags: next });
    setTags(saved); allTags.reload();
    return t("Tags saved.");
  });
  const addTag = () => {
    const names = tagInput.split(",").map((s) => s.trim()).filter(Boolean);
    if (!names.length) return;
    setTagInput("");
    saveTags([...tags, ...names]);
  };
  const setPart = (i: number, key: keyof Part, v: string) =>
    setParts(parts.map((p, j) => (j === i ? { ...p, [key]: v } : p)));

  return (
    <Modal wide title={t("Details: {d}", { d: txn.description || money(txn.amount, txn.currency) })}
      onClose={onClose} actions={<Button appearance="primary" onClick={onClose}>{t("Done")}</Button>}>
      {error && <Banner kind="error" onClose={() => setError(null)}>{error}</Banner>}
      {note && <Banner kind="success" onClose={() => setNote(null)}>{note}</Banner>}

      <h3 className="detail-head">{t("Tags")}</h3>
      <div className="caption">{t("Labels across categories, e.g. “Holiday 2026”. Filter by them on this page and see totals in Reports.")}</div>
      <div style={{ margin: "8px 0" }}>
        {tags.map((tag) => (
          <span key={tag} className="tag-chip">{tag}
            <Button appearance="transparent" size="small" icon={<Dismiss12Regular />} aria-label={t("Remove")}
              onClick={() => saveTags(tags.filter((x) => x !== tag))} /></span>))}
        {tags.length === 0 && <span className="caption">{t("No tags yet.")}</span>}
      </div>
      <div className="row">
        <Input list="pfi-tags" value={tagInput} placeholder={t("New tag")} style={{ width: 240 }}
          onChange={(_, d) => setTagInput(d.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addTag(); }} />
        <datalist id="pfi-tags">{allTags.data?.map((x) => <option key={x.id} value={x.name} />)}</datalist>
        <Button icon={<Add20Regular />} disabled={!tagInput.trim()} onClick={addTag}>{t("Add tag")}</Button>
      </div>

      {splittable && <>
        <h3 className="detail-head" style={{ marginTop: 20 }}>{t("Split across categories")}</h3>
        <div className="caption">{t("For one payment that covers several things, e.g. a supermarket receipt with groceries and household items. Budgets and reports count each part in its category.")}</div>
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          {parts.map((p, i) => (
            <div key={i} className="split-grid">
              <FField label={i === 0 ? t("Category") : undefined}>
                <Select value={p.category_id} onChange={(_, d) => setPart(i, "category_id", d.value)}>
                  <option value="">{t("Uncategorised")}</option>
                  {categoryOptions(cats, kind, t).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select></FField>
              <FField label={i === 0 ? t("Amount ({c})", { c: txn.currency }) : undefined}>
                <Input type="number" step="0.01" min="0" value={p.amount}
                  onChange={(_, d) => setPart(i, "amount", d.value)} /></FField>
              <FField label={i === 0 ? t("Note") : undefined}>
                <Input value={p.note} onChange={(_, d) => setPart(i, "note", d.value)} /></FField>
              <Button appearance="subtle" icon={<Delete20Regular />} aria-label={t("Remove")}
                disabled={parts.length <= 2} onClick={() => setParts(parts.filter((_, j) => j !== i))} />
            </div>))}
        </div>
        <div className="split-total">
          <Button size="small" icon={<Add20Regular />} onClick={() => setParts([...parts,
            { category_id: "", amount: rest > 0 ? (rest / 100).toFixed(2) : "0", note: "" }])}>
            {t("Add part")}</Button>
          <span className={rest === 0 ? "caption" : "caption neg"}>
            {rest === 0 ? t("Parts add up to {a}.", { a: money(sign * target / 100, txn.currency) })
              : t("{a} left to assign.", { a: num(rest / 100, 2) })}</span>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <Button appearance="primary" disabled={rest !== 0} onClick={() => wrap(async () => {
            await put(`/api/transactions/${txn.id}/splits`, { parts: parts.map((p) => ({
              category_id: p.category_id ? Number(p.category_id) : null,
              amount: ((sign * toCents(p.amount)) / 100).toFixed(2), note: p.note || null })) });
            return t("Split saved.");
          })}>{t("Save split")}</Button>
          {txn.splits.length > 0 && <Button onClick={() => wrap(async () => {
            await put(`/api/transactions/${txn.id}/splits`, { parts: [] });
            return t("Split removed. Choose a category for the transaction again.");
          })}>{t("Remove split")}</Button>}
        </div>
      </>}

      <h3 className="detail-head" style={{ marginTop: 20 }}>{t("Receipts")}</h3>
      <div className="caption">{t("Photos or PDFs, stored on this PC and included in backups (max 20 MB each).")}</div>
      <input ref={upload} type="file" hidden accept="image/*,application/pdf" onChange={async (e) => {
        const f = e.target.files?.[0]; e.target.value = "";
        if (!f) return;
        const d = new FormData(); d.append("file", f);
        await wrap(async () => {
          await api(`/api/transactions/${txn.id}/attachments`, { method: "POST", body: d });
          files.reload();
          return t("Receipt attached.");
        });
      }} />
      {files.loading && !files.data && <Spinner />}
      <div className="attach-list">
        {files.data?.map((a) => (
          <div key={a.id} className="list-row">
            <a className="grow" href={downloadUrl(`/api/attachments/${a.id}`)}>{a.filename}</a>
            <span className="caption">{a.size < 1048576 ? `${num(a.size / 1024, 0)} KB` : `${num(a.size / 1048576, 1)} MB`}</span>
            <Button appearance="subtle" size="small" icon={<Delete20Regular />} aria-label={t("Delete")}
              onClick={() => wrap(async () => { await del(`/api/attachments/${a.id}`); files.reload(); return t("Receipt removed."); })} />
          </div>))}
      </div>
      <div style={{ marginTop: 8 }}>
        <Button icon={<Attach20Regular />} onClick={() => upload.current?.click()}>
          {t("Attach receipt…")}</Button></div>
    </Modal>);
}
