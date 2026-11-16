"use client";
import { useState } from "react";
import {
  Badge, Button, Combobox, Field as FField, Input, Option, Radio, RadioGroup,
} from "@fluentui/react-components";
import {
  ArrowSync20Regular, FolderOpen20Regular, Phone20Regular,
} from "@fluentui/react-icons";
import { Banner, Confirm, Modal, SettingRow, useLoad } from "@/components/ui";
import { SyncStatus, get, post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { inShell, pickFolder } from "@/lib/shell";

type Msg = { kind: "success" | "error" | "warning"; text: string };

/** "2026-11-16 14:00:00.123" (UTC) as a local date and time. */
function when(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v.replace(" ", "T") + "Z");
  return isNaN(d.getTime()) ? v : d.toLocaleString();
}

/** Settings: sync with the phone app through a cloud-drive folder. */
export function SyncPanel({ onMessage, onSynced }: {
  onMessage: (m: Msg) => void; onSynced?: () => void;
}) {
  const t = useT();
  const st = useLoad(() => get<SyncStatus>("/api/sync"));
  const [setup, setSetup] = useState(false);
  const [folder, setFolder] = useState("");
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);
  const [place, setPlace] = useState<"folder" | "google">("folder");
  const [waiting, setWaiting] = useState(false);
  const s = st.data;
  const GOOGLE = "gdrive:appdata";

  const googleSignIn = async () => {
    setError(null);
    try {
      const { url } = await post<{ url: string }>("/api/sync/google/start");
      window.open(url, "_blank", "noopener");
      setWaiting(true);
      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const now = await get<SyncStatus>("/api/sync");
        if (now.google_signed_in) { await st.reload(); break; }
      }
    } catch (e) { setError((e as Error).message); }
    finally { setWaiting(false); }
  };

  const open = () => {
    setPlace(s?.folder === GOOGLE ? "google" : "folder");
    setFolder(s?.folder && s.folder !== GOOGLE ? s.folder
      : s?.suggestions[0]?.path || "");
    setName(s?.device_name || "");
    setPass(""); setPass2(""); setError(null); setSetup(true);
  };
  const start = async () => {
    if (pass !== pass2) { setError(t("The two passphrases are different.")); return; }
    setBusy(true); setError(null);
    try {
      await post<SyncStatus>("/api/sync/setup", {
        folder: place === "google" ? GOOGLE : folder.trim(), passphrase: pass, device_name: name.trim() || null });
      setSetup(false); st.reload(); onSynced?.();
      onMessage({ kind: "success", text: t("Sync is on. Use the same folder and passphrase in the PFI phone app.") });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const now = async () => {
    setBusy(true);
    try {
      const r = await post<SyncStatus & { result: { sent: number; received: number } }>("/api/sync/run");
      st.reload(); onSynced?.();
      onMessage({ kind: "success", text: t("Synced: {s} sent, {r} received.", {
        s: r.result.sent, r: r.result.received }) });
    } catch (e) { onMessage({ kind: "error", text: (e as Error).message }); st.reload(); }
    finally { setBusy(false); }
  };
  const off = async () => {
    setConfirmOff(false);
    await post("/api/sync/disable"); st.reload();
  };

  return (<>
    <SettingRow icon={""} title={t("Sync with your phone")}
      description={s?.enabled
        ? t("Through {folder}. Last sync: {when}.", {
          folder: s.folder_label ?? s.folder ?? "", when: when(s.last_sync) || t("not yet") })
        : t("Keep PFI on this PC and the PFI phone app in step through your OneDrive, Dropbox or Google Drive. Everything is encrypted with your passphrase; there is no PFI server.")}>
      {s?.enabled ? (<>
        <Button icon={<ArrowSync20Regular />} disabled={busy} onClick={now}>
          {busy ? t("Syncing…") : t("Sync now")}</Button>
        <Button appearance="subtle" onClick={() => setConfirmOff(true)}>{t("Stop syncing")}</Button>
      </>) : (
        <Button appearance="primary" icon={<Phone20Regular />} onClick={open}>{t("Set up sync")}</Button>)}
    </SettingRow>
    {s?.enabled && !s.phone_ready && (
      <div style={{ padding: "0 16px 8px" }}><Banner kind="warning">
        {t("The phone app looks for the folder Apps › PFI Sync at the top of your OneDrive. Choose OneDrive\\Apps\\PFI Sync here (Stop syncing, then Set up sync) so your phone can find it.")}
      </Banner></div>)}
    {s?.enabled && s.last_error && (
      <div style={{ padding: "0 16px 8px" }}><Banner kind="warning">{s.last_error}</Banner></div>)}
    {s?.enabled && (
      <SettingRow title={t("Devices")}
        description={s.devices.length
          ? s.devices.map((d) => `${d.name} (${when(d.seen)})`).join(" · ")
          : t("No phone has synced yet. On the phone: PFI › Settings (gear) › Set up sync › OneDrive, sign in with the same Microsoft account as this PC's OneDrive, then enter the same passphrase.")}>
        {s.pending > 0 && <Badge appearance="tint" color="warning">
          {t("{n} changes waiting", { n: s.pending })}</Badge>}
      </SettingRow>)}

    {setup && (
      <Modal title={t("Set up sync")} onClose={() => setSetup(false)} actions={<>
        <Button appearance="primary" disabled={busy || pass.length < 8
          || (place === "google" ? !s?.google_signed_in : !folder.trim())}
          onClick={start}>{busy ? t("Setting up…") : t("Start syncing")}</Button>
        <Button onClick={() => setSetup(false)}>{t("Cancel")}</Button></>}>
        {error && <Banner kind="error">{error}</Banner>}
        {s?.google_available && (
          <FField label={t("Where to keep the sync files")}>
            <RadioGroup layout="horizontal" value={place}
              onChange={(_, d) => setPlace(d.value as "folder" | "google")}>
              <Radio value="folder" label={t("OneDrive or Dropbox folder")} />
              <Radio value="google" label="Google Drive" />
            </RadioGroup>
          </FField>)}
        {place === "google" ? (<>
          <p>{t("PFI keeps its encrypted sync files in a hidden app folder of your Google Drive and cannot see your other files. Sign in here, then choose Google Drive in the phone app with the same Google account.")}</p>
          <FField label="Google Drive">
            {s?.google_signed_in
              ? <div className="row"><Badge appearance="tint" color="success">{t("Signed in")}</Badge>
                <Button size="small" appearance="subtle" onClick={async () => {
                  await post("/api/sync/google/signout"); st.reload();
                }}>{t("Sign out")}</Button></div>
              : <div><Button appearance="primary" onClick={googleSignIn} disabled={waiting}>
                {waiting ? t("Waiting for Google…") : t("Sign in with Google")}</Button></div>}
          </FField>
        </>) : (<>
        <p>{t("Choose a folder inside the folder your cloud drive keeps in sync. If you already use sync on another device, choose the same folder and enter the same passphrase.")}</p>
        <FField label={t("Sync folder")}>
          <div style={{ display: "flex", gap: 8 }}>
            <Combobox freeform value={folder} style={{ flex: 1, minWidth: 360 }}
              onChange={(e) => setFolder((e.target as HTMLInputElement).value)}
              onOptionSelect={(_, d) => setFolder(d.optionValue ?? "")}>
              {(s?.suggestions ?? []).filter((x) => x.provider !== "Google Drive").map((x) => (
                <Option key={x.path} value={x.path} text={x.path}>
                  {`${x.provider}: ${x.path}`}</Option>))}
            </Combobox>
            {inShell() && <Button icon={<FolderOpen20Regular />} onClick={async () => {
              const p = await pickFolder(folder); if (p) setFolder(p);
            }}>{t("Browse…")}</Button>}
          </div>
        </FField>
        </>)}
        <FField label={t("Sync passphrase")} hint={t("At least 8 characters. PFI cannot recover it; without it the synced data cannot be read.")}>
          <Input type="password" value={pass} onChange={(_, d) => setPass(d.value)} />
        </FField>
        <FField label={t("Repeat the passphrase")}>
          <Input type="password" value={pass2} onChange={(_, d) => setPass2(d.value)} />
        </FField>
        <FField label={t("Name of this PC on your other devices")}>
          <Input value={name} placeholder={t("e.g. Home PC")} onChange={(_, d) => setName(d.value)} />
        </FField>
      </Modal>)}
    {confirmOff && (
      <Confirm text={t("This PC stops sending and receiving changes. Your data and the sync folder stay as they are; you can set up sync again later.")}
        yesLabel={t("Stop syncing")} onYes={off} onClose={() => setConfirmOff(false)} />)}
  </>);
}
