"use client";
import { useEffect, useState } from "react";
import { Button } from "@fluentui/react-components";
import { Modal } from "@/components/ui";
import { Settings, get, put } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** The values sent once a week when the user agrees, shown word for word. */
export function UsageExplainer() {
  const t = useT();
  return (
    <ul className="caption" style={{ margin: "8px 0", paddingInlineStart: 18 }}>
      <li>{t("a random number made on this PC (not linked to you, the computer or your data)")}</li>
      <li>{t("the app version")}</li>
      <li>{t("the app language")}</li>
    </ul>
  );
}

/** Asks once whether PFI may count this install anonymously. Shown only
 *  when the counter is configured and the user has not decided yet. */
export function UsagePrompt() {
  const t = useT();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    get<Settings>("/api/settings").then((s) => {
      if (s.usage_available && s.usage_ping === "ask") setOpen(true);
    }).catch(() => {});
  }, []);
  if (!open) return null;
  const choose = (on: boolean) => {
    setOpen(false);
    put("/api/settings", { usage_ping: on ? "on" : "off" }).catch(() => {});
  };
  return (
    <Modal title={t("Help count PFI users?")} onClose={() => setOpen(false)} actions={<>
      <Button appearance="primary" onClick={() => choose(true)}>{t("Yes, count me")}</Button>
      <Button onClick={() => choose(false)}>{t("No thanks")}</Button></>}>
      <p style={{ marginTop: 0 }}>{t("PFI is free and has no accounts, so I have no idea how many people use it. If you agree, the app sends three values once a week:")}</p>
      <UsageExplainer />
      <p className="caption">{t("Never amounts, accounts, transactions or file names. You can change your mind any time in Settings › Privacy & security.")}</p>
    </Modal>
  );
}
