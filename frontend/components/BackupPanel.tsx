"use client";
import { ReactNode, useRef, useState } from "react";
import {
  Badge, Button, Field as FField, Input, Switch, Tooltip,
} from "@fluentui/react-components";
import {
  ArrowDownload20Regular, FolderOpen20Regular, LockClosed16Regular,
  ArrowSwap20Regular,
} from "@fluentui/react-icons";
import { Banner, Confirm, Empty, Modal, SettingRow, useLoad } from "@/components/ui";
import { ApiError, Backup, BackupList, api, downloadUrl, get, post, put } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { inShell, pickFolder } from "@/lib/shell";

type Msg = { kind: "success" | "error" | "warning"; text: string };

function startDownload(name: string) {
  const a = document.createElement("a");
  a.href = downloadUrl(`/api/backups/${name}/download`);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Restore a stored backup, asking for its password when it needs one. */
export function useRestore(onDone: (safety: string) => void, onError: (m: string) => void) {
  const t = useT();
  const [ask, setAsk] = useState<{ name: string; error?: string } | null>(null);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const restore = async (name: string, password?: string) => {
    setBusy(true);
    try {
      const r = await post<{ safety_backup: string }>(`/api/backups/${name}/restore`,
        password ? { password } : {});
      setAsk(null); setPw("");
      onDone(r.safety_backup);
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) setAsk({ name, error: password ? e.message : undefined });
      else onError((e as Error).message);
    } finally { setBusy(false); }
  };
  const dialog: ReactNode = ask && (
    <Modal title={t("Backup password")} onClose={() => { setAsk(null); setPw(""); }} actions={<>
      <Button appearance="primary" disabled={busy || !pw} onClick={() => restore(ask.name, pw)}>
        {busy ? t("Restoring…") : t("Restore")}</Button>
      <Button onClick={() => { setAsk(null); setPw(""); }}>{t("Cancel")}</Button></>}>
      {ask.error && <Banner kind="error">{ask.error}</Banner>}
      <p>{t("This backup is protected with a password. Enter the password used when it was made.")}</p>
      <FField label={t("Password")}>
        <Input type="password" value={pw} autoFocus onChange={(_, d) => setPw(d.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && pw) restore(ask.name, pw); }} />
      </FField>
    </Modal>);
  return { restore, dialog };
}

type AccountCheck = {
  name: string; same: boolean; backup_count: number | null; live_count: number | null;
  backup_balance: string | null; live_balance: string | null;
};
export type BackupCheck = {
  name: string; created: string; matches: boolean;
  transactions_backup: number; transactions_live: number;
  sampled: number; sample_mismatches: number;
  receipts_backup: number; receipts_live: number; accounts: AccountCheck[];
};

/** Test a stored backup (unpack and compare, nothing restored), asking
 *  for its password when it needs one. */
export function useBackupTest(onError: (m: string) => void) {
  const t = useT();
  const [ask, setAsk] = useState<{ name: string; error?: string } | null>(null);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<BackupCheck | null>(null);
  const test = async (name: string, password?: string) => {
    setBusy(name);
    try {
      const r = await post<BackupCheck>(`/api/backups/${name}/test`, password ? { password } : {});
      setAsk(null); setPw(""); setResult(r);
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) setAsk({ name, error: password ? e.message : undefined });
      else onError((e as Error).message);
    } finally { setBusy(null); }
  };
  const when = (iso: string) => new Date(iso).toLocaleString("de-CH");
  const differing = result?.accounts.filter((a) => !a.same) ?? [];
  const dialog: ReactNode = (<>
    {ask && <Modal title={t("Backup password")} onClose={() => { setAsk(null); setPw(""); }} actions={<>
      <Button appearance="primary" disabled={!!busy || !pw} onClick={() => test(ask.name, pw)}>
        {busy ? t("Testing…") : t("Test")}</Button>
      <Button onClick={() => { setAsk(null); setPw(""); }}>{t("Cancel")}</Button></>}>
      {ask.error && <Banner kind="error">{ask.error}</Banner>}
      <p>{t("This backup is protected with a password. Enter the password used when it was made.")}</p>
      <FField label={t("Password")}>
        <Input type="password" value={pw} autoFocus onChange={(_, d) => setPw(d.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && pw) test(ask.name, pw); }} />
      </FField>
    </Modal>}
    {result && <Modal title={t("Backup test")} onClose={() => setResult(null)}
      actions={<Button appearance="primary" onClick={() => setResult(null)}>{t("Done")}</Button>}>
      {result.matches
        ? <Banner kind="success">{t("This backup works and matches your current data exactly: {n} transactions in {a} accounts, every balance the same.",
            { n: result.transactions_live, a: result.accounts.length })}</Banner>
        : <Banner kind="warning">{t("This backup works: it opens and passes the integrity check. Your data has changed since it was made ({d}), so the differences below are expected if you added or edited something since then.",
            { d: when(result.created) })}</Banner>}
      <ul className="caption" style={{ paddingInlineStart: 18 }}>
        <li>{t("Transactions: {b} in the backup, {l} now.", { b: result.transactions_backup, l: result.transactions_live })}</li>
        <li>{t("{s} transactions picked at random were compared field by field: {m} differ.", { s: result.sampled, m: result.sample_mismatches })}</li>
        <li>{t("Receipts: {b} in the backup, {l} now.", { b: result.receipts_backup, l: result.receipts_live })}</li>
      </ul>
      {differing.length > 0 && <div className="table-wrap" style={{ maxHeight: 220 }}>
        <table><thead><tr><th>{t("Account")}</th><th className="num">{t("In the backup")}</th><th className="num">{t("Now")}</th></tr></thead>
          <tbody>{differing.map((a) => (<tr key={a.name}><td>{a.name}</td>
            <td className="num">{a.backup_balance === null ? t("not in the backup")
              : t("{b} ({n} transactions)", { b: a.backup_balance, n: a.backup_count ?? 0 })}</td>
            <td className="num">{a.live_balance === null ? t("deleted since")
              : t("{b} ({n} transactions)", { b: a.live_balance, n: a.live_count ?? 0 })}</td></tr>))}
          </tbody></table></div>}
    </Modal>}
  </>);
  return { test, busy, dialog };
}

/** Upload a .pfibak file, then confirm and restore it. */
export function RestoreFromFile({ label, appearance, onDone, onError }: {
  label?: string; appearance?: "primary" | "secondary";
  onDone: (safety: string) => void; onError: (m: string) => void;
}) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<{ name: string; file: string } | null>(null);
  const { restore, dialog } = useRestore(onDone, onError);
  return (<>
    <input ref={input} type="file" accept=".pfibak" hidden onChange={async (e) => {
      const f = e.target.files?.[0]; e.target.value = "";
      if (!f) return;
      const d = new FormData(); d.append("file", f);
      try {
        const up = await api<Backup>("/api/backups/upload", { method: "POST", body: d });
        setPending({ name: up.name, file: f.name });
      } catch (err) { onError((err as Error).message); }
    }} />
    <Button appearance={appearance} onClick={() => input.current?.click()}>
      {label ?? t("Restore from file…")}</Button>
    {pending && <Confirm danger text={t("Restore “{f}”? Your current data is backed up first, then replaced.", { f: pending.file })}
      onYes={() => restore(pending.name)} onClose={() => setPending(null)} />}
    {dialog}
  </>);
}

export function BackupPanel({ onMessage, onRestored }: {
  onMessage: (m: Msg) => void; onRestored: () => void;
}) {
  const t = useT();
  const list = useLoad(() => get<BackupList>("/api/backups"));
  const data = list.data;
  const [busy, setBusy] = useState<string | null>(null);
  const [folder, setFolder] = useState<string | null>(null);
  const [pwModal, setPwModal] = useState(false);
  const [pw1, setPw1] = useState(""); const [pw2, setPw2] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [move, setMove] = useState<Backup | null>(null);
  const [confirm, setConfirm] = useState<Backup | null>(null);
  const done = (safety: string) => {
    list.reload(); onRestored();
    onMessage({ kind: "success", text: t("Restored. Previous data saved as {n}.", { n: safety }) });
  };
  const fail = (m: string) => onMessage({ kind: "error", text: m });
  const { restore, dialog } = useRestore(done, fail);
  const tester = useBackupTest(fail);
  const shell = typeof window !== "undefined" && inShell();
  const chosen = folder ?? data?.chosen_folder ?? "";

  const saveSettings = async (body: Record<string, unknown>, ok: string) => {
    try {
      await put<BackupList>("/api/backups/settings", {
        folder: data?.chosen_folder ?? null, encrypt: data?.encrypt ?? false, ...body });
      list.reload(); setFolder(null);
      onMessage({ kind: "success", text: ok });
      return true;
    } catch (e) { fail((e as Error).message); return false; }
  };
  const create = async (kind: "manual" | "move") => {
    setBusy(kind);
    try {
      const b = await post<Backup>("/api/backups", { kind });
      list.reload();
      if (kind === "move") { startDownload(b.name); setMove(b); }
      else onMessage({ kind: b.warning ? "warning" : "success",
        text: b.warning ?? t("Backup {n} created.", { n: b.name }) });
    } catch (e) { fail((e as Error).message); }
    finally { setBusy(null); }
  };
  const savePassword = async () => {
    if (pw1.length < 8) { setPwError(t("Use at least 8 characters.")); return; }
    if (pw1 !== pw2) { setPwError(t("The two passwords are not the same.")); return; }
    if (await saveSettings({ encrypt: true, password: pw1 },
      t("New backups are protected with your password."))) {
      setPwModal(false); setPw1(""); setPw2(""); setPwError(null);
    }
  };

  return (<>
    <SettingRow icon={""} title={t("Backups")}
      description={t("A weekly automatic backup is made when the app starts (the newest 8 are kept). A safety backup is always made before a restore.")}>
      <RestoreFromFile onDone={done} onError={fail} />
      <Button appearance="primary" disabled={busy === "manual"} onClick={() => create("manual")}>
        {busy === "manual" ? t("Backing up…") : t("Back up now")}</Button>
    </SettingRow>
    {data?.folder_warning && <div className="setting-body"><Banner kind="warning">{data.folder_warning}</Banner></div>}
    <SettingRow icon={""} title={t("Backup folder")}
      description={t("Choose a OneDrive folder or an external drive to keep a copy outside this PC. Empty = the app's own folder.")}>
      <Input style={{ minWidth: 260 }} value={chosen} placeholder={data?.default_folder}
        onChange={(_, d) => setFolder(d.value)} />
      {shell && <Button icon={<FolderOpen20Regular />} onClick={async () => {
        const p = await pickFolder(chosen || data?.default_folder || "");
        if (p) setFolder(p);
      }}>{t("Browse…")}</Button>}
      {folder !== null && folder !== (data?.chosen_folder ?? "") &&
        <Button appearance="primary" onClick={() => saveSettings({ folder: folder || null },
          folder ? t("Backups now go to {f}.", { f: folder }) : t("Backups now go to the app's own folder."))}>
          {t("Save")}</Button>}
      {data?.chosen_folder && folder === null && <Button appearance="subtle" onClick={() =>
        saveSettings({ folder: null }, t("Backups now go to the app's own folder."))}>{t("Use default")}</Button>}
    </SettingRow>
    <SettingRow icon={""} title={t("Protect backups with a password")}
      description={t("Backup files are encrypted, so a copy in OneDrive or on a USB drive cannot be read without the password. If you forget it, encrypted backups cannot be restored.")}>
      <Switch checked={Boolean(data?.encrypt)} onChange={(_, d) => {
        if (d.checked && !data?.has_password) { setPwModal(true); return; }
        saveSettings({ encrypt: d.checked }, d.checked ? t("New backups are protected with your password.")
          : t("New backups are no longer encrypted."));
      }} />
      {data?.has_password && <Button appearance="subtle" onClick={() => setPwModal(true)}>{t("Change password")}</Button>}
      {data?.has_password && <Button appearance="subtle" onClick={() =>
        saveSettings({ encrypt: false, clear_password: true }, t("Backup password removed."))}>{t("Remove")}</Button>}
    </SettingRow>
    <SettingRow icon={""} title={t("Move to another PC")}
      description={t("Saves one file with all your data and receipts to the Downloads folder. Open it in PFI on the new PC.")}>
      <Button icon={<ArrowSwap20Regular />} disabled={busy === "move"} onClick={() => create("move")}>
        {busy === "move" ? t("Preparing…") : t("Create move file")}</Button>
    </SettingRow>
    <div className="setting-body table-wrap" style={{ maxHeight: 280 }}>
      <div className="caption" style={{ marginBottom: 8 }}>{t("Folder:")} <code>{data?.folder}</code></div>
      {data?.backups.length === 0 && <Empty>{t("No backups yet.")}</Empty>}
      {!!data?.backups.length && (
        <table><thead><tr><th>{t("Created")}</th><th>{t("Kind")}</th><th className="num">{t("Size")}</th><th /></tr></thead>
          <tbody>{data.backups.map((b) => (
            <tr key={`${b.folder}/${b.name}`}><td>{new Date(b.created).toLocaleString("de-CH")}</td>
              <td><Badge appearance="tint">{t(b.kind)}</Badge>
                {b.encrypted && <Tooltip content={t("Protected with a password")} relationship="label">
                  <LockClosed16Regular style={{ marginInlineStart: 6, verticalAlign: "middle" }} /></Tooltip>}
                {b.legacy && <Badge appearance="outline" size="small" style={{ marginInlineStart: 6 }}>0.3</Badge>}</td>
              <td className="num">{bytes(b.size)}</td>
              <td className="actions">
                <Tooltip content={t("Download")} relationship="label">
                  <Button appearance="subtle" size="small" icon={<ArrowDownload20Regular />} as="a"
                    href={downloadUrl(`/api/backups/${b.name}/download`)} /></Tooltip>
                {!b.legacy && <Tooltip content={t("Open this backup in a temporary folder and compare it with your current data. Nothing is restored.")} relationship="description">
                  <Button appearance="subtle" size="small" disabled={tester.busy === b.name}
                    onClick={() => tester.test(b.name)}>{tester.busy === b.name ? t("Testing…") : t("Test")}</Button></Tooltip>}
                {!b.legacy && <Button appearance="subtle" size="small" onClick={() => setConfirm(b)}>{t("Restore")}</Button>}
                {b.legacy && <Tooltip content={t("Backups from PFI 0.3 can only be restored with PFI 0.4.0.")} relationship="label">
                  <Button appearance="subtle" size="small" disabledFocusable>{t("Restore")}</Button></Tooltip>}</td></tr>))}
          </tbody></table>)}
    </div>
    {confirm && <Confirm danger text={t("Restore the backup from {d}? Your current data is backed up first, then replaced.",
      { d: new Date(confirm.created).toLocaleString("de-CH") })}
      onYes={() => restore(confirm.name)} onClose={() => setConfirm(null)} />}
    {dialog}
    {tester.dialog}
    {pwModal && <Modal title={t("Backup password")} onClose={() => { setPwModal(false); setPwError(null); }} actions={<>
      <Button appearance="primary" onClick={savePassword}>{t("Save")}</Button>
      <Button onClick={() => { setPwModal(false); setPwError(null); }}>{t("Cancel")}</Button></>}>
      {pwError && <Banner kind="error">{pwError}</Banner>}
      <Banner kind="warning">{t("Write the password down somewhere safe. Without it, encrypted backups cannot be restored, not even by the developer.")}</Banner>
      <FField label={t("Password")} hint={t("At least 8 characters; a few words are easier to remember.")}>
        <Input type="password" value={pw1} onChange={(_, d) => setPw1(d.value)} /></FField>
      <FField label={t("Repeat password")}>
        <Input type="password" value={pw2} onChange={(_, d) => setPw2(d.value)} /></FField>
    </Modal>}
    {move && <Modal title={t("Move to another PC")} onClose={() => setMove(null)}
      actions={<Button appearance="primary" onClick={() => setMove(null)}>{t("Done")}</Button>}>
      <ol className="steps">
        <li>{t("The file {n} is being saved to your Downloads folder.", { n: move.name })}</li>
        <li>{t("Copy it to the new PC, for example with a USB stick or OneDrive.")}</li>
        <li>{t("On the new PC, install PFI and choose “Restore from a backup” on the first screen (or Settings → Backups → Restore from file).")}</li>
        {move.encrypted && <li>{t("You will need your backup password.")}</li>}
      </ol>
    </Modal>}
  </>);
}
