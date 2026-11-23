"use client";
// Settings rows that keep data trustworthy: Check my data, updates, and
// the edits made on two devices before they synced.
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Switch } from "@fluentui/react-components";
import { Modal, SettingRow, Spinner, useLoad } from "./ui";
import { I } from "./icons";
import { get, post, put } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Msg = (m: { kind: "success" | "error" | "warning"; text: string }) => void;

interface Issue {
  code: string; level: "error" | "warning"; title: string; detail: string;
  fix: string; transaction_ids: number[]; count: number; fixable: boolean;
}
interface CheckResult { ok: boolean; issues: Issue[]; checked: number }

export function DataCheckRow({ onMessage }: { onMessage: Msg }) {
  const t = useT();
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { setResult(await get<CheckResult>("/api/system/check")); }
    catch (e) { onMessage({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  };
  const fix = async (code: string) => {
    const r = await post<CheckResult & { changed: number }>("/api/system/check/fix", { code });
    setResult(r);
    onMessage({ kind: "success", text: t("{n} transactions fixed.", { n: r.changed }) });
  };
  return (
    <>
      <SettingRow icon={I.factCheck} title={t("Check my data")}
        description={t("Looks for transfers with a missing side, splits that don't add up and other problems that would make totals wrong.")}>
        <Button onClick={run} disabled={busy}>{busy ? t("Checking…") : t("Check now")}</Button>
      </SettingRow>
      {result && (
        <Modal title={t("Check my data")} onClose={() => setResult(null)} wide
          actions={<Button appearance="primary" onClick={() => setResult(null)}>{t("Close")}</Button>}>
          {result.ok ? (
            <div className="check-ok">
              <span className="icon" aria-hidden>{I.checkCircle}</span>
              <div>
                <div className="setting-title">{t("Everything adds up")}</div>
                <div className="caption">{t("{n} transactions checked, no problems found.", { n: result.checked })}</div>
              </div>
            </div>
          ) : (
            <ul className="list">
              {result.issues.map((i) => (
                <li key={i.code} className="check-issue">
                  <div className="check-head">
                    <Badge appearance="tint" color={i.level === "error" ? "danger" : "warning"}>
                      {i.level === "error" ? t("Problem") : t("Worth a look")}</Badge>
                    <b>{t(i.title)}</b>
                    {i.count > 0 && <span className="caption">{t("{n} transactions", { n: i.count })}</span>}
                  </div>
                  <div className="caption">{t(i.detail)}</div>
                  <div className="caption"><b>{t("How to fix:")}</b> {t(i.fix)}</div>
                  <div className="row">
                    {i.transaction_ids.length > 0 && (
                      <Link href={`/transactions/?ids=${i.transaction_ids.join(",")}`}>
                        <Button size="small">{t("Show them")}</Button></Link>)}
                    {i.fixable && <Button size="small" appearance="primary"
                      onClick={() => fix(i.code)}>{t("Fix")}</Button>}
                  </div>
                </li>))}
            </ul>)}
        </Modal>)}
    </>
  );
}

interface UpdateStatus {
  current: string; latest: string | null; newer: boolean; url: string;
  notes: string; store: boolean; enabled: boolean; checked_at: string | null;
  error: string | null;
}

/** Banner shown at the top of every page when a newer version is out. */
export function UpdateBanner() {
  const t = useT();
  const st = useLoad(() => get<UpdateStatus>("/api/system/update"));
  const [hidden, setHidden] = useState(false);
  const s = st.data;
  if (!s || !s.newer || s.store || hidden) return null;
  const key = `pfi-update-dismissed-${s.latest}`;
  try { if (localStorage.getItem(key)) return null; } catch { /* storage off */ }
  return (
    <div className="update-banner" role="status">
      <span className="icon" aria-hidden>{I.systemUpdate}</span>
      <div className="update-text">
        <b>{t("Personal Finance {v} is available", { v: s.latest ?? "" })}</b>
        <span className="caption">{t("You have {v}. Your data stays as it is when you update.", { v: s.current })}</span>
      </div>
      <Button as="a" appearance="primary" size="small" href={s.url} target="_blank"
        rel="noreferrer">{t("Get the update")}</Button>
      <Button appearance="subtle" size="small" onClick={() => {
        try { localStorage.setItem(key, "1"); } catch { /* storage off */ }
        setHidden(true);
      }}>{t("Later")}</Button>
    </div>
  );
}

export function UpdateRow({ onMessage }: { onMessage: Msg }) {
  const t = useT();
  const st = useLoad(() => get<UpdateStatus>("/api/system/update"));
  const [busy, setBusy] = useState(false);
  const s = st.data;
  if (!s) return null;
  if (s.store) {
    return (
      <SettingRow icon={I.systemUpdate} title={t("Updates")}
        description={t("Installed from the Microsoft Store, which keeps Personal Finance up to date.")} />);
  }
  const checkNow = async () => {
    setBusy(true);
    try {
      const r = await get<UpdateStatus>("/api/system/update", { force: true });
      st.reload();
      onMessage(r.error ? { kind: "warning", text: r.error } : {
        kind: "success", text: r.newer ? t("Personal Finance {v} is available.", { v: r.latest ?? "" })
          : t("You have the latest version.") });
    } finally { setBusy(false); }
  };
  return (
    <SettingRow icon={I.systemUpdate} title={t("Check for updates")}
      description={`${t("Once a day, asks GitHub whether a newer version is out. Nothing about you or your data is sent.")}${s.checked_at ? " " + t("Last checked {d}.", { d: dateTime(s.checked_at) }) : ""}`}>
      <Button onClick={checkNow} disabled={busy}>{busy ? t("Checking…") : t("Check now")}</Button>
      <Switch checked={s.enabled} aria-label={t("Check for updates")}
        onChange={async (_, d) => { await put("/api/settings", { update_check: d.checked }); st.reload(); }} />
    </SettingRow>
  );
}

interface Conflict {
  id: number; table: string; replaced: "here" | "there";
  kept: Record<string, unknown>; other: Record<string, unknown>; created_at: string;
}
const TABLE_LABEL: Record<string, string> = {
  transactions: "Transaction", accounts: "Account", categories: "Category",
  recurring_items: "Bill", goals: "Goal",
};

function Fields({ values, other }: { values: Record<string, unknown>; other: Record<string, unknown> }) {
  const t = useT();
  return (
    <dl className="conflict-fields">
      {Object.entries(values).map(([k, v]) => (
        <div key={k} className={String(v) !== String(other[k]) ? "changed" : undefined}>
          <dt>{t(k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()))}</dt>
          <dd>{v === null || v === "" ? "—" : String(v)}</dd>
        </div>))}
    </dl>
  );
}

export function ConflictsRow() {
  const t = useT();
  const list = useLoad(() => get<{ conflicts: Conflict[] }>("/api/sync/conflicts"));
  const [open, setOpen] = useState(false);
  const items = list.data?.conflicts ?? [];
  const settle = async (id: number, use: "kept" | "other") => {
    const r = await post<{ conflicts: Conflict[] }>(`/api/sync/conflicts/${id}`, { use });
    list.reload();
    if (r.conflicts.length === 0) setOpen(false);
  };
  if (items.length === 0) return null;
  return (
    <>
      <SettingRow icon={I.syncProblem} title={t("Changed on two devices")}
        description={t("{n} items were edited on this PC and another device before they synced. Personal Finance kept the newer edit; you can switch to the other one.", { n: items.length })}>
        <Button appearance="primary" onClick={() => setOpen(true)}>{t("Review")}</Button>
      </SettingRow>
      {open && (
        <Modal title={t("Changed on two devices")} wide onClose={() => setOpen(false)}
          actions={<Button onClick={() => setOpen(false)}>{t("Close")}</Button>}>
          {list.loading && <Spinner />}
          <ul className="list">
            {items.map((c) => (
              <li key={c.id} className="conflict">
                <div className="caption">{t(TABLE_LABEL[c.table] ?? c.table)} · {dateTime(c.created_at)}</div>
                <div className="conflict-pair">
                  <div className="conflict-side kept">
                    <div className="conflict-label">{t("Kept (newer)")}{c.replaced === "there" ? ` · ${t("this PC")}` : ` · ${t("other device")}`}</div>
                    <Fields values={c.kept} other={c.other} />
                    <Button size="small" appearance="primary" onClick={() => settle(c.id, "kept")}>{t("Keep this")}</Button>
                  </div>
                  <div className="conflict-side">
                    <div className="conflict-label">{t("Other edit")}{c.replaced === "there" ? ` · ${t("other device")}` : ` · ${t("this PC")}`}</div>
                    <Fields values={c.other} other={c.kept} />
                    <Button size="small" onClick={() => settle(c.id, "other")}>{t("Use this instead")}</Button>
                  </div>
                </div>
              </li>))}
          </ul>
        </Modal>)}
    </>
  );
}
