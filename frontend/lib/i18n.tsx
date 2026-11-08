"use client";
// Minimal gettext-style translation layer. English source strings are the
// keys; fr/ar dictionaries map them to translations. Missing keys fall back
// to English, so a new string never breaks the UI.
import { createContext, ReactNode, useCallback, useContext, useMemo } from "react";
import ar from "./locales/ar.json";
import fr from "./locales/fr.json";

export type Lang = "en" | "fr" | "ar";
export const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
  { value: "ar", label: "العربية" },
];
const DICTS: Record<Lang, Record<string, string>> = { en: {}, fr, ar };
type Vars = Record<string, string | number>;

function interpolate(s: string, vars?: Vars) {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

export function translate(lang: Lang, key: string, vars?: Vars) {
  return interpolate(DICTS[lang]?.[key] ?? key, vars);
}

type Ctx = { lang: Lang; dir: "ltr" | "rtl"; t: (k: string, v?: Vars) => string };
const I18n = createContext<Ctx>({
  lang: "en", dir: "ltr", t: (k, v) => interpolate(k, v),
});

export function I18nProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  const t = useCallback((k: string, v?: Vars) => translate(lang, k, v), [lang]);
  const value = useMemo<Ctx>(() => ({ lang, dir: lang === "ar" ? "rtl" : "ltr", t }),
    [lang, t]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
export const useT = () => useContext(I18n).t;
