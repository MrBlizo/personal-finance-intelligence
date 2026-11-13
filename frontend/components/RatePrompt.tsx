"use client";
import { useEffect, useState } from "react";
import { Button } from "@fluentui/react-components";
import { Star20Regular } from "@fluentui/react-icons";
import { Modal } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { requestRating } from "@/lib/shell";

type RatingStatus = { due: boolean };

/** Asks once for a Microsoft Store rating, after 14 days of use and 20
 *  real transactions. "Rate" and "No thanks" are final; "Not now" asks
 *  again after 30 days, once. */
export function RatePrompt() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => {
      get<RatingStatus>("/api/rating").then((s) => setOpen(s.due)).catch(() => {});
    }, 4000);
    return () => clearTimeout(timer);
  }, []);
  if (!open) return null;
  const answer = (outcome: "rated" | "declined" | "later") => {
    setOpen(false);
    post("/api/rating", { outcome }).catch(() => {});
  };
  const rate = async () => {
    setBusy(true);
    await requestRating().catch(() => "error");
    setBusy(false);
    answer("rated");
  };
  return (
    <Modal title={t("Enjoying PFI?")} onClose={() => answer("later")} actions={<>
      <Button appearance="primary" icon={<Star20Regular />} disabled={busy} onClick={rate}>
        {t("Rate PFI")}</Button>
      <Button onClick={() => answer("later")}>{t("Not now")}</Button>
      <Button appearance="subtle" onClick={() => answer("declined")}>{t("No thanks")}</Button></>}>
      <p>{t("PFI is free and made by one developer. A rating in the Microsoft Store helps other people find it, and it takes a few seconds.")}</p>
      <p className="caption">{t("“No thanks” and “Rate PFI” are final. With “Not now”, PFI asks once more in a month.")}</p>
    </Modal>
  );
}
