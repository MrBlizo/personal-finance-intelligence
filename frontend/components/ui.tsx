"use client";
// Shared building blocks on top of Fluent UI v9, laid out like WinUI 3
// pages: a title, a command row, and content in cards and "setting rows".
import {
  Badge, Button, Checkbox, Dialog, DialogActions, DialogBody, DialogContent,
  DialogSurface, DialogTitle, Field as FField, Input, MessageBar,
  MessageBarActions, MessageBarBody, MessageBarTitle, ProgressBar, Select,
  Spinner as FSpinner, Switch, Textarea,
} from "@fluentui/react-components";
import { Dismiss20Regular } from "@fluentui/react-icons";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import { ThemeMenu } from "./Theme";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const d = await fn();
      if (my === seq.current) { setData(d); setError(null); }
    } catch (e) {
      if (my === seq.current) setError((e as Error).message);
    } finally {
      if (my === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

const INTENT = { info: "info", warning: "warning", error: "error",
  success: "success" } as const;

/** WinUI InfoBar look-alike. */
export function Banner({ kind = "info", title, children, onClose, action }: {
  kind?: keyof typeof INTENT; title?: string; children?: ReactNode;
  onClose?: () => void; action?: ReactNode;
}) {
  const t = useT();
  return (
    <MessageBar intent={INTENT[kind]} className="banner" layout="multiline">
      <MessageBarBody>
        {title && <MessageBarTitle>{title}</MessageBarTitle>}
        {children}
      </MessageBarBody>
      {(onClose || action) && (
        <MessageBarActions containerAction={onClose && (
          <Button appearance="transparent" aria-label={t("Close")}
            icon={<Dismiss20Regular />} onClick={onClose} />)}>
          {action}
        </MessageBarActions>)}
    </MessageBar>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <FSpinner size="tiny" label={label} labelPosition="after" />;
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div>{children}</div>
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export function Kpi({ label, value, sub, cls }: {
  label: string; value: ReactNode; sub?: ReactNode; cls?: string;
}) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${cls ?? ""}`}>{value}</div>
      {sub !== undefined && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

/** WinUI page header: large title, optional subtitle, command bar. */
export function PageHead({ title, sub, children }: {
  title: string; sub?: ReactNode; children?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="titles">
        <h1>{title}</h1>
        {sub && <div className="subtitle">{sub}</div>}
      </div>
      <div className="commands">{children}<ThemeMenu /></div>
    </header>
  );
}

/** A card section with an optional header and command area. */
export function Section({ title, sub, actions, children, className }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode;
  children?: ReactNode; className?: string;
}) {
  return (
    <section className={`card section ${className ?? ""}`}>
      {(title || actions) && (
        <div className="section-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <div className="caption">{sub}</div>}
          </div>
          {actions && <div className="commands">{actions}</div>}
        </div>)}
      {children}
    </section>
  );
}

/** WinUI "settings card": icon, header + description, control on the right. */
export function SettingRow({ icon, title, description, children }: {
  icon?: string; title: ReactNode; description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="setting-row">
      <span className="glyph setting-icon" aria-hidden>{icon ?? ""}</span>
      <div className="setting-text">
        <div className="setting-title">{title}</div>
        {description && <div className="caption">{description}</div>}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const t = useT();
  const map: Record<string, ["success" | "warning" | "danger" | "informative", string]> = {
    ok: ["success", "On track"], at_risk: ["warning", "At risk"],
    over: ["danger", "Over budget"], achieved: ["success", "Achieved"],
    behind: ["warning", "Behind"], on_track: ["success", "On track"],
    no_deadline: ["informative", "No deadline"], completed: ["success", "Completed"],
    overdue: ["danger", "Overdue"], manual: ["informative", "Manual tracking"],
  };
  const [color, label] = map[status] ?? ["informative", status];
  return <Badge appearance="tint" color={color}>{t(label)}</Badge>;
}

export function Modal({ title, children, onClose, actions, wide }: {
  title: string; children: ReactNode; onClose: () => void;
  actions?: ReactNode; wide?: boolean;
}) {
  return (
    <Dialog open onOpenChange={(_, d) => { if (!d.open) onClose(); }}>
      <DialogSurface style={{ maxWidth: `min(${wide ? 900 : 560}px, calc(100vw - 32px))` }}>
        <DialogBody>
          <DialogTitle>{title}</DialogTitle>
          <DialogContent className="dialog-content">{children}</DialogContent>
          {actions && <DialogActions>{actions}</DialogActions>}
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

export type Field = {
  name: string; label: string;
  type?: "text" | "number" | "date" | "select" | "checkbox" | "switch"
    | "textarea" | "month";
  options?: { value: string | number; label: string }[];
  required?: boolean; full?: boolean; step?: string; placeholder?: string;
  help?: string; hidden?: boolean;
};
export type Values = Record<string, string | number | boolean | null>;

/** Dialog with a two-column form, validation and async submit. */
export function FormModal({ title, fields: fieldsProp, initial, onSubmit, onClose,
  submitLabel, onChange, wide }: {
  title: string; fields: Field[] | ((v: Values) => Field[]); initial: Values;
  onSubmit: (v: Values) => Promise<void>; onClose: () => void;
  submitLabel?: string; onChange?: (v: Values) => Values; wide?: boolean;
}) {
  const t = useT();
  const [values, setValues] = useState<Values>(initial);
  const fields = typeof fieldsProp === "function" ? fieldsProp(values) : fieldsProp;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (name: string, v: string | boolean) => {
    const next = { ...values, [name]: v };
    setValues(onChange ? onChange(next) : next);
  };
  const submit = async () => {
    for (const f of fields) {
      const v = values[f.name];
      if (f.required && !f.hidden && (v === "" || v === null || v === undefined)) {
        setError(t("“{field}” is required.", { field: f.label }));
        return;
      }
    }
    setBusy(true);
    setError(null);
    try { await onSubmit(values); onClose(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onClose} wide={wide} actions={<>
      <Button appearance="primary" disabled={busy} onClick={submit}>
        {busy ? t("Saving…") : (submitLabel ?? t("Save"))}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button>
    </>}>
      {error && <Banner kind="error">{error}</Banner>}
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {fields.filter((f) => !f.hidden).map((f) => {
          const v = values[f.name];
          const cls = f.full ? "full" : "";
          if (f.type === "checkbox") {
            return <Checkbox key={f.name} className={cls} label={f.label}
              checked={Boolean(v)} onChange={(_, d) => set(f.name, Boolean(d.checked))} />;
          }
          if (f.type === "switch") {
            return (
              <FField key={f.name} className={cls} hint={f.help}>
                <Switch label={f.label} checked={Boolean(v)}
                  onChange={(_, d) => set(f.name, d.checked)} />
              </FField>);
          }
          let input: ReactNode;
          if (f.type === "select") {
            input = (
              <Select value={v === null ? "" : String(v ?? "")}
                onChange={(_, d) => set(f.name, d.value)}>
                {!f.required && <option value="">—</option>}
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>))}
              </Select>);
          } else if (f.type === "textarea") {
            input = <Textarea resize="vertical" value={String(v ?? "")}
              onChange={(_, d) => set(f.name, d.value)} />;
          } else {
            input = <Input type={f.type ?? "text"} step={f.step}
              placeholder={f.placeholder} value={String(v ?? "")}
              onChange={(_, d) => set(f.name, d.value)} />;
          }
          return (
            <FField key={f.name} className={cls} label={f.label}
              required={f.required} hint={f.help}>{input}</FField>);
        })}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

export function Confirm({ text, onYes, onClose, danger, yesLabel }: {
  text: ReactNode; onYes: () => Promise<void>; onClose: () => void;
  danger?: boolean; yesLabel?: string;
}) {
  const t = useT();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={t("Are you sure?")} onClose={onClose} actions={<>
      <Button appearance="primary" disabled={busy}
        className={danger ? "danger-btn" : undefined} onClick={async () => {
          setBusy(true);
          try { await onYes(); onClose(); }
          catch (e) { setError((e as Error).message); setBusy(false); }
        }}>{yesLabel ?? t("Confirm")}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <div>{text}</div>
    </Modal>
  );
}

export function Progress({ value, status }: { value: number; status?: string }) {
  const color = status === "over" ? "error" : status === "at_risk" ? "warning"
    : status === "achieved" ? "success" : "brand";
  return <ProgressBar thickness="large" value={Math.max(0, Math.min(1, value))}
    color={color} />;
}

/** Strip empty strings to null and convert numeric fields. */
export function clean(v: Values, numeric: string[] = []): Values {
  const out: Values = {};
  for (const [k, x] of Object.entries(v)) {
    if (x === "") out[k] = null;
    else if (numeric.includes(k) && x !== null) out[k] = Number(x);
    else out[k] = x;
  }
  return out;
}
