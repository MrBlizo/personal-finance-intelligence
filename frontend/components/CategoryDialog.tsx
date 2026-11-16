"use client";
// Add or edit a category: name, kind, parent, colour and icon.
import { useState } from "react";
import { Button, Field, Input, Select } from "@fluentui/react-components";
import { CategoryIcon, IconPicker, guessIcon } from "./CategoryIcon";
import { catLabel } from "./refs";
import { Banner, Modal } from "./ui";
import { Category, post, put } from "@/lib/api";
import { useT } from "@/lib/i18n";

const COLOURS = ["#0072B2", "#56B4E9", "#009E73", "#2E7D32", "#827717", "#E69F00",
  "#E65100", "#D55E00", "#C62828", "#AD1457", "#CC79A7", "#6750A4", "#3949AB",
  "#00796B", "#5D4037", "#455A64"];

export function CategoryDialog({ category, all, onClose, onSaved }: {
  category: Category | null; all: Category[]; onClose: () => void; onSaved: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(category?.name ?? "");
  const [kind, setKind] = useState<"income" | "expense">(category?.kind ?? "expense");
  const [parent, setParent] = useState(category?.parent_id ? String(category.parent_id) : "");
  const [color, setColor] = useState(category?.color ?? "");
  const [icon, setIcon] = useState<string | null>(category?.icon ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!name.trim()) { setError(t("“{field}” is required.", { field: t("Name") })); return; }
    setBusy(true);
    const body = { name: name.trim(), kind, parent_id: parent ? Number(parent) : null,
      color: color || null, icon };
    try {
      if (category) await put(`/api/categories/${category.id}`, body);
      else await post("/api/categories", body);
      onSaved(); onClose();
    } catch (e) { setError((e as Error).message); setBusy(false); }
  };
  return (
    <Modal title={category ? t("Edit {name}", { name: catLabel(category.name, t) }) : t("Add category")}
      onClose={onClose} actions={<>
        <Button appearance="primary" disabled={busy} onClick={save}>{t("Save")}</Button>
        <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <div className="row" style={{ gap: 16 }}>
        <CategoryIcon name={name || "?"} icon={icon ?? guessIcon(name)} color={color} size={56} />
        <Field label={t("Name")} required className="grow">
          <Input value={name} onChange={(_, d) => setName(d.value)} />
        </Field>
      </div>
      <div className="form-grid">
        <Field label={t("Kind")}>
          <Select value={kind} onChange={(_, d) => setKind(d.value as "income" | "expense")}>
            <option value="expense">{t("Expense")}</option>
            <option value="income">{t("Income")}</option>
          </Select>
        </Field>
        <Field label={t("Parent (optional)")}>
          <Select value={parent} onChange={(_, d) => setParent(d.value)}>
            <option value="">—</option>
            {all.filter((x) => !x.parent_id && x.id !== category?.id && x.kind === kind)
              .map((x) => <option key={x.id} value={x.id}>{t(x.name)}</option>)}
          </Select>
        </Field>
      </div>
      <Field label={t("Colour")}>
        <div className="swatches">
          {COLOURS.map((c) => (
            <button key={c} type="button" aria-label={c} className={`swatch ${color === c ? "selected" : ""}`}
              style={{ background: c }} onClick={() => setColor(c)} />))}
          <button type="button" className={`swatch ${!color ? "selected" : ""}`} aria-label={t("Automatic")}
            title={t("Automatic")} onClick={() => setColor("")}
            style={{ background: "conic-gradient(#0072B2, #E69F00, #009E73, #CC79A7, #0072B2)" }} />
        </div>
      </Field>
      <Field label={t("Icon")} hint={icon ? undefined : t("None chosen: PFI picks one from the name.")}>
        <IconPicker value={icon} color={color} onChange={setIcon} />
      </Field>
    </Modal>
  );
}
