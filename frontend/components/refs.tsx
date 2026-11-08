"use client";
import { Account, Category, Settings, get } from "@/lib/api";
import { useLoad } from "./ui";

/** Settings, accounts and categories used by most forms. */
export function useRefs() {
  return useLoad(async () => {
    const [settings, accounts, categories] = await Promise.all([
      get<Settings>("/api/settings"),
      get<Account[]>("/api/accounts"),
      get<Category[]>("/api/categories"),
    ]);
    return { settings, accounts, categories };
  });
}

type T = (k: string) => string;
const same: T = (k) => k;

/** Translate a (possibly nested "Parent › Child") category name. Default
 *  category names are in the dictionaries; user-made names pass through. */
export const catLabel = (name: string | null | undefined, t: T = same) =>
  name ? name.split(" › ").map((p) => t(p)).join(" › ") : "";

export const accountOptions = (accs: Account[], filter?: (a: Account) => boolean) =>
  accs.filter((a) => !a.is_archived && (!filter || filter(a)))
    .map((a) => ({ value: a.id, label: `${a.name} (${a.currency})` }));

export const categoryOptions = (cats: Category[], kind?: string, t: T = same) =>
  cats.filter((c) => !kind || c.kind === kind).map((c) => ({
    value: c.id,
    label: `${catLabel(c.full_name, t)}${kind ? "" : c.kind === "income"
      ? ` (${t("income")})` : ""}`,
  }));
