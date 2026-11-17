"use client";
import { useState } from "react";
import {
  Badge, Button, Combobox, Field as FField, Input, Option, Select, Textarea,
} from "@fluentui/react-components";
import { ArrowSync20Regular, BuildingBank20Regular } from "@fluentui/react-icons";
import { Banner, Confirm, Modal, SettingRow, useLoad } from "@/components/ui";
import { Account, del, get, post, put } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Msg = { kind: "success" | "error" | "warning"; text: string };
type Link = {
  id: number; provider: "simplefin" | "enablebanking"; name: string;
  institution: string; currency: string; balance: number | null;
  account_id: number | null; start_date: string | null;
  last_synced_on: string | null; last_error: string | null;
};
type Status = {
  simplefin: boolean; enablebanking: boolean;
  enablebanking_app_id: string | null;
  enablebanking_sessions: { valid_until: string | null }[];
  redirect_url: string; links: Link[]; warnings?: string[];
  result?: { imported: number; duplicates: number; accounts: number; errors: string[] };
};

// Countries Enable Banking covers (EEA and UK).
const COUNTRIES = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
  "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT",
  "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK"];

/** Settings: import new transactions from the bank automatically. */
export function BankSyncPanel({ onMessage }: { onMessage: (m: Msg) => void }) {
  const t = useT();
  const st = useLoad(() => get<Status>("/api/banksync"));
  const accounts = useLoad(() => get<Account[]>("/api/accounts"));
  const [dialog, setDialog] = useState<null | "simplefin" | "enablebanking">(null);
  const [token, setToken] = useState("");
  const [appId, setAppId] = useState("");
  const [pem, setPem] = useState("");
  const [country, setCountry] = useState("FR");
  const [banks, setBanks] = useState<string[]>([]);
  const [bank, setBank] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [off, setOff] = useState<null | "simplefin" | "enablebanking">(null);
  const s = st.data;

  const go = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const loadBanks = (c: string) => go(async () => {
    setCountry(c); setBank("");
    setBanks((await get<{ banks: string[] }>("/api/banksync/enablebanking/banks",
      { country: c })).banks);
  });
  const connectSimplefin = () => go(async () => {
    const r = await post<Status>("/api/banksync/simplefin", { token });
    setToken(""); setDialog(null); st.reload();
    onMessage({ kind: r.warnings?.length ? "warning" : "success",
      text: t("SimpleFIN is connected: {n} accounts found. Choose which PFI account each one fills.",
        { n: r.links.filter((l) => l.provider === "simplefin").length })
        + (r.warnings?.length ? " " + r.warnings.join(" ") : "") });
  });
  const saveEb = () => go(async () => {
    await post<Status>("/api/banksync/enablebanking", { app_id: appId, private_key: pem });
    setPem(""); st.reload(); await loadBanks(country);
  });
  const openBank = () => go(async () => {
    const { url } = await post<{ url: string }>("/api/banksync/enablebanking/connect",
      { bank, country });
    window.open(url, "_blank", "noopener");
    const before = s?.links.length ?? 0;
    for (let i = 0; i < 150; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const now = await get<Status>("/api/banksync");
      if (now.links.length > before) { await st.reload(); setDialog(null); break; }
    }
  });
  const pasteCode = () => go(async () => {
    await post<Status>("/api/banksync/enablebanking/code", { code });
    setCode(""); setDialog(null); st.reload();
  });
  const link = async (l: Link, account: string) => {
    await put<Status>(`/api/banksync/links/${l.id}`,
      { account_id: account ? Number(account) : null, start_date: l.start_date });
    st.reload();
  };
  const runNow = () => go(async () => {
    const r = await post<Status>("/api/banksync/run");
    st.reload();
    const res = r.result!;
    onMessage({ kind: res.errors.length ? "warning" : "success",
      text: t("Bank sync: {n} new transactions, {d} already in PFI.",
        { n: res.imported, d: res.duplicates })
        + (res.errors.length ? " " + res.errors.join(" ") : "") });
  });

  const linked = s?.links.filter((l) => l.account_id) ?? [];
  const accountName = (id: number | null) =>
    accounts.data?.find((a) => a.id === id)?.name ?? "";

  return (<>
    <SettingRow icon={""} title={t("Bank sync")}
      description={linked.length
        ? t("{n} bank accounts update automatically every 6 hours while PFI is open.", { n: linked.length })
        : t("Let PFI fetch new transactions from your bank, like YNAB, through access you set up yourself. US and Canada: SimpleFIN Bridge ($15 a year, paid to SimpleFIN). Europe: Enable Banking (free for your own accounts).")}>
      {linked.length > 0 && <Button icon={<ArrowSync20Regular />} disabled={busy} onClick={runNow}>
        {busy ? t("Fetching…") : t("Fetch now")}</Button>}
      <Button appearance={linked.length ? "secondary" : "primary"} icon={<BuildingBank20Regular />}
        onClick={() => { setError(null); setDialog("simplefin"); }}>{t("US / Canada")}</Button>
      <Button appearance={linked.length ? "secondary" : "primary"} icon={<BuildingBank20Regular />}
        onClick={() => {
          setError(null); setAppId(s?.enablebanking_app_id ?? ""); setDialog("enablebanking");
          if (s?.enablebanking && !banks.length) loadBanks(country);
        }}>{t("Europe")}</Button>
    </SettingRow>
    {error && !dialog && <div style={{ padding: "0 16px 8px" }}><Banner kind="error">{error}</Banner></div>}
    {(s?.links ?? []).map((l) => (
      <SettingRow key={l.id}
        title={<>{l.name}{l.institution ? ` · ${l.institution}` : ""}{" "}
          <Badge appearance="outline" size="small">{l.provider === "simplefin" ? "SimpleFIN" : "Enable Banking"}</Badge></>}
        description={l.last_error
          ? <span className="neg">{l.last_error}</span>
          : [l.balance != null ? t("Bank balance {b}", { b: money(l.balance, l.currency) }) : "",
            l.last_synced_on ? t("Last fetched {d}", { d: date(l.last_synced_on) })
              : l.account_id ? t("Not fetched yet") : t("Not used: choose a PFI account to fill")]
            .filter(Boolean).join(" · ")}>
        <Select value={l.account_id ? String(l.account_id) : ""} aria-label={t("PFI account")}
          onChange={(_, d) => link(l, d.value)}>
          <option value="">{t("Do not import")}</option>
          {(accounts.data ?? []).filter((a) => !a.is_archived || a.id === l.account_id).map((a) => (
            <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>))}
        </Select>
        {l.account_id && <span className="caption">{t("into {a}", { a: accountName(l.account_id) })}</span>}
      </SettingRow>))}
    {(s?.simplefin || s?.enablebanking) && (
      <SettingRow title={t("Connected services")}
        description={[s.simplefin ? "SimpleFIN" : "", s.enablebanking ? "Enable Banking" : ""]
          .filter(Boolean).join(" · ")}>
        <Button appearance="subtle" onClick={() => go(async () => { await post("/api/banksync/refresh"); st.reload(); })}>
          {t("Refresh account list")}</Button>
        {s.simplefin && <Button appearance="subtle" onClick={() => setOff("simplefin")}>{t("Disconnect SimpleFIN")}</Button>}
        {s.enablebanking && <Button appearance="subtle" onClick={() => setOff("enablebanking")}>{t("Disconnect Enable Banking")}</Button>}
      </SettingRow>)}

    {dialog === "simplefin" && (
      <Modal title={t("Connect US and Canadian banks (SimpleFIN)")} onClose={() => setDialog(null)} actions={<>
        <Button appearance="primary" disabled={busy || token.trim().length < 10} onClick={connectSimplefin}>
          {busy ? t("Connecting…") : t("Connect")}</Button>
        <Button onClick={() => setDialog(null)}>{t("Cancel")}</Button></>}>
        {error && <Banner kind="error">{error}</Banner>}
        <ol className="steps-list">
          <li>{t("Open bridge.simplefin.org, create an account and subscribe ($15 a year, paid to SimpleFIN).")}</li>
          <li>{t("Connect your banks there (My account › Connect institution).")}</li>
          <li>{t("Under Apps, click New connection and copy the setup token.")}</li>
          <li>{t("Paste the token below. It can be used only once.")}</li>
        </ol>
        <Button appearance="subtle" onClick={() => window.open("https://bridge.simplefin.org/", "_blank", "noopener")}>
          {t("Open SimpleFIN Bridge")}</Button>
        <FField label={t("Setup token")}>
          <Textarea value={token} rows={3} onChange={(_, d) => setToken(d.value)} />
        </FField>
        <p className="caption">{t("PFI keeps the access encrypted on this PC and talks to SimpleFIN directly; your bank password never reaches PFI.")}</p>
      </Modal>)}

    {dialog === "enablebanking" && (
      <Modal wide title={t("Connect European banks (Enable Banking)")} onClose={() => setDialog(null)} actions={
        <Button onClick={() => setDialog(null)}>{t("Close")}</Button>}>
        {error && <Banner kind="error">{error}</Banner>}
        {!s?.enablebanking ? (<>
          <ol className="steps-list">
            <li>{t("Open enablebanking.com, sign up and open the Control Panel.")}</li>
            <li>{t("Register a new application: environment Production, and add this redirect URL:")}{" "}
              <code>{s?.redirect_url}</code></li>
            <li>{t("Download the private key (.pem) it creates and copy the application ID.")}</li>
            <li>{t("Click “Activate by linking accounts” and link your own bank accounts. In this free mode only these accounts can be read.")}</li>
          </ol>
          <Button appearance="subtle" onClick={() => window.open("https://enablebanking.com/cp/applications", "_blank", "noopener")}>
            {t("Open Enable Banking")}</Button>
          <FField label={t("Application ID")}>
            <Input value={appId} onChange={(_, d) => setAppId(d.value)} />
          </FField>
          <FField label={t("Private key")} hint={t("Open the .pem file in Notepad and paste all of it, including the BEGIN and END lines.")}>
            <Textarea value={pem} rows={6} style={{ fontFamily: "monospace" }} onChange={(_, d) => setPem(d.value)} />
          </FField>
          <Button appearance="primary" disabled={busy || !appId.trim() || pem.length < 100} onClick={saveEb}>
            {busy ? t("Checking…") : t("Save")}</Button>
        </>) : (<>
          <p>{t("Choose your bank. Its sign-in page opens in the browser; after you approve, PFI lists the accounts here.")}</p>
          <div className="row" style={{ gap: 8, alignItems: "end" }}>
            <FField label={t("Country")}>
              <Select value={country} onChange={(_, d) => loadBanks(d.value)}>
                {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </FField>
            <FField label={t("Bank")} style={{ flex: 1 }}>
              <Combobox value={bank} placeholder={busy ? t("Loading…") : t("Type to search")}
                onChange={(e) => setBank((e.target as HTMLInputElement).value)}
                onOptionSelect={(_, d) => setBank(d.optionValue ?? "")}>
                {banks.filter((b) => b.toLowerCase().includes(bank.toLowerCase())).slice(0, 80).map((b) => (
                  <Option key={b} value={b}>{b}</Option>))}
              </Combobox>
            </FField>
            <Button appearance="primary" disabled={busy || !banks.includes(bank)} onClick={openBank}>
              {busy ? t("Waiting for the bank…") : t("Connect bank")}</Button>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary>{t("The browser showed a code instead of returning to PFI?")}</summary>
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              <Input value={code} placeholder={t("Paste the code")} onChange={(_, d) => setCode(d.value)} style={{ flex: 1 }} />
              <Button disabled={busy || code.length < 4} onClick={pasteCode}>{t("Finish")}</Button>
            </div>
          </details>
          <p className="caption">{t("Bank consents last up to 180 days; PFI tells you when one has to be renewed.")}</p>
        </>)}
      </Modal>)}
    {off && (
      <Confirm text={t("PFI forgets this access and stops fetching from these banks. Transactions already imported stay.")}
        yesLabel={t("Disconnect")} onYes={async () => { await del(`/api/banksync/${off}`); setOff(null); st.reload(); }}
        onClose={() => setOff(null)} />)}
  </>);
}
