"use client";
import { useState } from "react";
import { Button, Checkbox } from "@fluentui/react-components";
import { Delete20Regular } from "@fluentui/react-icons";
import { Confirm, SettingRow, useLoad } from "@/components/ui";
import { LegacyData, get, post } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useT } from "@/lib/i18n";

/** Settings row that removes what PFI 0.4 left from the 0.3 database.
 *  Hidden when there is nothing to remove. */
export function OldDataRow({ onMessage }: {
  onMessage: (m: { kind: "success" | "error"; text: string }) => void;
}) {
  const t = useT();
  const data = useLoad(() => get<LegacyData>("/api/legacy-data"));
  const [dumps, setDumps] = useState(false);
  const [asking, setAsking] = useState(false);
  const d = data.data;
  if (!d || (d.size === 0 && d.dumps === 0)) return null;
  const total = d.size + (dumps ? d.dump_size : 0);
  return (
    <>
      <SettingRow icon={""} title={t("Old data from PFI 0.3")}
        description={<>
          {t("Your data was moved to the new format in 0.4. The old copy is no longer used and takes {size}.",
            { size: bytes(d.size) })}
          {d.dumps > 0 && (
            <div style={{ marginTop: 6 }}>
              <Checkbox checked={dumps} onChange={(_, v) => setDumps(!!v.checked)}
                label={t("Also delete {n} old backups from 0.3 (.dump, {size}); PFI 0.5 can no longer restore them",
                  { n: d.dumps, size: bytes(d.dump_size) })} />
            </div>)}
        </>}>
        <Button icon={<Delete20Regular />} disabled={total === 0} onClick={() => setAsking(true)}>
          {t("Delete")}</Button>
      </SettingRow>
      {asking && (
        <Confirm danger yesLabel={t("Delete")} onClose={() => setAsking(false)}
          text={t("Delete the old PFI 0.3 data ({size})? Your current data and your .pfibak backups are not touched. This cannot be undone.",
            { size: bytes(total) })}
          onYes={async () => {
            const r = await post<LegacyData & { freed: number }>("/api/legacy-data/delete", { dumps });
            data.reload(); setDumps(false);
            onMessage({ kind: "success", text: t("Old data deleted ({size} freed).", { size: bytes(r.freed) }) });
          }} />)}
    </>
  );
}
