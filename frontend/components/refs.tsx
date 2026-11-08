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

export const accountOptions = (accs: Account[], filter?: (a: Account) => boolean) =>
  accs.filter((a) => !a.is_archived && (!filter || filter(a)))
    .map((a) => ({ value: a.id, label: `${a.name} (${a.currency})` }));

export const categoryOptions = (cats: Category[], kind?: string) =>
  cats.filter((c) => !kind || c.kind === kind).map((c) => ({
    value: c.id,
    label: `${c.full_name}${kind ? "" : c.kind === "income" ? " (income)" : ""}`,
  }));
