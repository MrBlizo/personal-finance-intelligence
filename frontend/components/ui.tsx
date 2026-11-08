"use client";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

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

export function Banner({ kind = "info", children, onClose }: {
  kind?: "info" | "warning" | "error" | "success"; children: ReactNode;
  onClose?: () => void;
}) {
  return (
    <div className={`banner ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div className="grow">{children}</div>
      {onClose && <button className="link" onClick={onClose}>✕</button>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <span className="spinner" />{label && <span className="muted">{label}</span>}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Kpi({ label, value, sub, cls }: {
  label: string; value: ReactNode; sub?: ReactNode; cls?: string;
}) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className={`value ${cls ?? ""}`}>{value}</div>
      {sub !== undefined && <div className="sub">{sub}</div>}
    </div>
  );
}

export function PageHead({ title, sub, children }: {
  title: string; sub?: ReactNode; children?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>
      <div className="toolbar">{children}</div>
    </div>
  );
}

export function Modal({ title, children, onClose, actions, wide }: {
  title: string; children: ReactNode; onClose: () => void;
  actions?: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className="modal" role="dialog" aria-label={title}
        style={wide ? { width: 860 } : undefined}>
        <h2>{title}</h2>
        {children}
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  );
}

export type Field = {
  name: string; label: string;
  type?: "text" | "number" | "date" | "select" | "checkbox" | "textarea"
    | "month";
  options?: { value: string | number; label: string }[];
  required?: boolean; full?: boolean; step?: string; placeholder?: string;
  help?: string; hidden?: boolean;
};
export type Values = Record<string, string | number | boolean | null>;

export function FormModal({ title, fields: fieldsProp, initial, onSubmit, onClose,
  submitLabel = "Save", onChange }: {
  title: string; fields: Field[] | ((v: Values) => Field[]); initial: Values;
  onSubmit: (v: Values) => Promise<void>; onClose: () => void;
  submitLabel?: string; onChange?: (v: Values) => Values;
}) {
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
        setError(`“${f.label}” is required.`);
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
    <Modal title={title} onClose={onClose} actions={<>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy} onClick={submit}>
        {busy ? "Saving…" : submitLabel}</button>
    </>}>
      {error && <Banner kind="error">{error}</Banner>}
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {fields.filter((f) => !f.hidden).map((f) => {
          const v = values[f.name];
          const common = { id: f.name, name: f.name };
          let input: ReactNode;
          if (f.type === "select") {
            input = (
              <select {...common} value={v === null ? "" : String(v ?? "")}
                onChange={(e) => set(f.name, e.target.value)}>
                {!f.required && <option value="">—</option>}
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>))}
              </select>);
          } else if (f.type === "checkbox") {
            return (
              <label key={f.name} className={`check ${f.full ? "full" : ""}`}>
                <input type="checkbox" {...common} checked={Boolean(v)}
                  onChange={(e) => set(f.name, e.target.checked)} />
                {f.label}
              </label>);
          } else if (f.type === "textarea") {
            input = <textarea {...common} rows={3} value={String(v ?? "")}
              onChange={(e) => set(f.name, e.target.value)} />;
          } else {
            input = <input {...common} type={f.type ?? "text"} step={f.step}
              placeholder={f.placeholder} value={String(v ?? "")}
              onChange={(e) => set(f.name, e.target.value)} />;
          }
          return (
            <label key={f.name} className={`field ${f.full ? "full" : ""}`}>
              {f.label}{f.required ? " *" : ""}{input}
              {f.help && <span className="small">{f.help}</span>}
            </label>);
        })}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

export function Confirm({ text, onYes, onClose }: {
  text: ReactNode; onYes: () => Promise<void>; onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal title="Please confirm" onClose={onClose} actions={<>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" onClick={async () => {
        try { await onYes(); onClose(); }
        catch (e) { setError((e as Error).message); }
      }}>Confirm</button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <div>{text}</div>
    </Modal>
  );
}

export function Progress({ value, status }: {
  value: number; status?: string;
}) {
  const cls = status === "over" ? "over" : status === "at_risk" ? "risk" : "";
  return (
    <div className={`progress ${cls}`}>
      <div style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
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
