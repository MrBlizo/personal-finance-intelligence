"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { Spinner } from "@fluentui/react-components";
import { get, Settings } from "@/lib/api";
import { I18nProvider, Lang, translate, useT } from "@/lib/i18n";
import { inShell, notifyLanguage, notifyRoute, onShellNavigate } from "@/lib/shell";
import { ThemeRoot } from "./Theme";

export const NAV = [
  { href: "/", label: "Home", glyph: "" },
  { href: "/transactions/", label: "Transactions", glyph: "" },
  { href: "/accounts/", label: "Accounts", glyph: "" },
  { href: "/import/", label: "Import", glyph: "" },
  { href: "/budgets/", label: "Budgets", glyph: "" },
  { href: "/goals/", label: "Goals", glyph: "" },
  { href: "/recurring/", label: "Bills & recurring", glyph: "" },
  { href: "/investments/", label: "Investments", glyph: "" },
  { href: "/forecast/", label: "Forecast", glyph: "" },
  { href: "/insights/", label: "Insights", glyph: "" },
  { href: "/reports/", label: "Reports", glyph: "" },
  { href: "/settings/", label: "Settings", glyph: "" },
];

type Prefs = { lang: Lang; setLang: (l: Lang) => void };
const PrefsCtx = createContext<Prefs>({ lang: "en", setLang: () => {} });
export const usePrefs = () => useContext(PrefsCtx);

function Sidebar({ path }: { path: string }) {
  const t = useT();
  const norm = (p: string) => (p.endsWith("/") ? p : p + "/");
  return (
    <aside className="sidebar">
      <div className="brand">Personal Finance Intelligence</div>
      <nav className="nav">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
            className={norm(path) === n.href ? "active" : ""}>
            <span className="glyph" aria-hidden>{n.glyph}</span>
            {t(n.label)}
          </Link>))}
      </nav>
    </aside>
  );
}

export default function AppFrame({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  const [lang, setLang] = useState<Lang | null>(null);
  useEffect(() => {
    if (inShell()) document.documentElement.dataset.shell = "1";
    get<Settings>("/api/settings")
      .then((s) => setLang((s.language as Lang) || "en"))
      .catch(() => setLang("en"));
    return onShellNavigate((p) => router.push(p));
  }, [router]);
  useEffect(() => { notifyRoute(path); }, [path]);
  useEffect(() => {
    if (!lang) return;
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    notifyLanguage(lang, Object.fromEntries(
      NAV.map((n) => [n.href, translate(lang, n.label)])));
  }, [lang]);
  if (!lang) {
    return <div className="boot"><Spinner size="medium" /></div>;
  }
  return (
    <PrefsCtx.Provider value={{ lang, setLang }}>
      <I18nProvider lang={lang}>
        <ThemeRoot dir={lang === "ar" ? "rtl" : "ltr"}>
          <div className="frame">
            <Sidebar path={path} />
            <main className="main">{children}</main>
          </div>
        </ThemeRoot>
      </I18nProvider>
    </PrefsCtx.Provider>
  );
}
