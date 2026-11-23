"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import {
  Link as FLink, Spinner, Toast, ToastBody, ToastFooter, ToastTitle, Toaster,
  useId, useToastController,
} from "@fluentui/react-components";
import { get, put, Settings } from "@/lib/api";
import { I18nProvider, Lang, translate, useT } from "@/lib/i18n";
import {
  inShell, notifyLanguage, notifyRoute, onShellDownload, onShellNavigate,
  openLastDownload,
} from "@/lib/shell";
import { CommandPalette, openPalette } from "./CommandPalette";
import { openQuickAdd, QuickAddHotkey } from "./QuickAdd";
import { SetupAssistant } from "./SetupAssistant";
import { UpdateBanner } from "./TrustPanels";
import { RatePrompt } from "./RatePrompt";
import { ThemePref, ThemeRoot } from "./Theme";
import { I } from "./icons";

type NavLink = { href: string; label: string; glyph: string };
type NavGroup = { id: string; label: string; glyph: string; children: NavLink[] };

/** The drawer: a few top-level destinations, related pages grouped. */
export const NAV_TREE: (NavLink | NavGroup)[] = [
  { href: "/", label: "Home", glyph: I.home },
  { href: "/months/", label: "Month by month", glyph: I.calendarViewMonth },
  { id: "money", label: "Money", glyph: I.payments, children: [
    { href: "/transactions/", label: "Transactions", glyph: I.receiptLong },
    { href: "/accounts/", label: "Accounts", glyph: I.accountBalance },
    { href: "/recurring/", label: "Bills & recurring", glyph: I.eventRepeat },
    { href: "/import/", label: "Import", glyph: I.download },
  ] },
  { id: "plan", label: "Planning", glyph: I.savings, children: [
    { href: "/budgets/", label: "Budgets", glyph: I.accountBalanceWallet },
    { href: "/goals/", label: "Goals", glyph: I.flag },
    { href: "/forecast/", label: "Forecast", glyph: I.timeline },
    { href: "/debts/", label: "Debt payoff", glyph: I.creditCard },
    { href: "/ious/", label: "Lent & borrowed", glyph: I.handshake },
  ] },
  { href: "/investments/", label: "Investments", glyph: I.trendingUp },
  { id: "analysis", label: "Reports & insights", glyph: I.summarize, children: [
    { href: "/reports/", label: "Reports", glyph: I.summarize },
    { href: "/insights/", label: "Insights", glyph: I.lightbulb },
    { href: "/calendar/", label: "Calendar", glyph: I.calendarMonth },
  ] },
  { href: "/settings/", label: "Settings", glyph: I.settings },
];
const isGroup = (n: NavLink | NavGroup): n is NavGroup => "children" in n;
/** Every destination, flat (command palette, window titles). */
export const NAV: NavLink[] = NAV_TREE.flatMap((n) => (isGroup(n) ? n.children : [n]));

type Prefs = { lang: Lang; setLang: (l: Lang) => void };
const PrefsCtx = createContext<Prefs>({ lang: "en", setLang: () => {} });
export const usePrefs = () => useContext(PrefsCtx);

const OPEN_KEY = "pfi.nav.open";
const norm = (p: string) => (p.endsWith("/") ? p : p + "/");

/** Material 3 navigation drawer; a navigation rail on narrow windows.
 *  Related pages sit in groups that open in place; the group holding the
 *  current page is always open. The extended FAB above is the app's one
 *  primary action (add a transaction), kept apart from navigation. */
function NavDrawer({ path }: { path: string }) {
  const t = useT();
  const here = norm(path);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try { setOpen(JSON.parse(localStorage.getItem(OPEN_KEY) ?? "{}")); } catch { /* fresh */ }
  }, []);
  const toggle = (id: string) => setOpen((o) => {
    const next = { ...o, [id]: !o[id] };
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(next)); } catch { /* private mode */ }
    return next;
  });
  const link = (n: NavLink, child = false) => (
    <Link key={n.href} href={n.href} title={t(n.label)}
      aria-current={here === n.href ? "page" : undefined}
      className={`nav-item${child ? " nav-child" : ""}`}>
      <span className="nav-indicator" aria-hidden><span className="icon">{n.glyph}</span></span>
      <span className="nav-label">{t(n.label)}</span>
    </Link>);
  return (
    <aside className="nav-drawer">
      <div className="nav-brand">
        <span className="nav-brand-text">Personal Finance</span>
      </div>
      <button type="button" className="fab" onClick={openQuickAdd}
        title={t("Add transaction")}>
        <span className="icon" aria-hidden>{I.add}</span>
        <span className="fab-label">{t("Add transaction")}</span>
      </button>
      <button type="button" className="nav-search" onClick={openPalette}
        title={t("Search or jump to… (Ctrl+K)")}>
        <span className="icon" aria-hidden>{I.search}</span>
        <span className="nav-label grow">{t("Search or jump to…")}</span>
        <kbd className="nav-label">Ctrl K</kbd>
      </button>
      <nav className="nav" aria-label={t("Navigation")}>
        {NAV_TREE.map((n) => {
          if (!isGroup(n)) return link(n);
          const inside = n.children.some((c) => c.href === here);
          const expanded = inside || !!open[n.id];
          return (
            <div key={n.id} className={`nav-group${expanded ? " open" : ""}${inside ? " inside" : ""}`}>
              <button type="button" className="nav-item nav-group-head" aria-expanded={expanded}
                aria-controls={`nav-${n.id}`} title={t(n.label)}
                onClick={() => (inside ? undefined : toggle(n.id))}>
                <span className="nav-indicator" aria-hidden><span className="icon">{n.glyph}</span></span>
                <span className="nav-label grow">{t(n.label)}</span>
                <span className="icon nav-chevron" aria-hidden>{I.expandMore}</span>
              </button>
              <div id={`nav-${n.id}`} className="nav-children" hidden={!expanded}>
                {n.children.map((c) => link(c, true))}
              </div>
            </div>);
        })}
      </nav>
    </aside>
  );
}

/** Confirms exports the shell saved to Downloads, like a Windows toast. */
function DownloadToasts() {
  const t = useT();
  const toasterId = useId("downloads");
  const { dispatchToast } = useToastController(toasterId);
  useEffect(() => onShellDownload((d) => dispatchToast(
    <Toast>
      <ToastTitle>{d.ok ? t("Saved to Downloads")
        : t("The file could not be saved. Check free disk space and try again.")}</ToastTitle>
      {d.name && <ToastBody>{d.name}</ToastBody>}
      {d.ok && (
        <ToastFooter>
          <FLink onClick={() => openLastDownload(false)}>{t("Open")}</FLink>
          <FLink onClick={() => openLastDownload(true)}>{t("Show in folder")}</FLink>
        </ToastFooter>)}
    </Toast>,
    { intent: d.ok ? "success" : "error", timeout: 8000 })), [dispatchToast, t]);
  return <Toaster toasterId={toasterId} position="bottom-end" />;
}

export default function AppFrame({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  const [lang, setLang] = useState<Lang | null>(null);
  const [theme, setTheme] = useState<ThemePref>("system");
  const [accent, setAccent] = useState("");
  const [setup, setSetup] = useState<{ base: string } | null>(null);
  const changeTheme = (p: ThemePref) => {
    setTheme(p);
    put("/api/settings", { theme: p }).catch(() => {});
  };
  const changeAccent = (hex: string) => {
    setAccent(hex);
    put("/api/settings", { accent_color: hex }).catch(() => {});
  };
  useEffect(() => {
    if (inShell()) document.documentElement.dataset.shell = "1";
    get<Settings>("/api/settings")
      .then((s) => {
        setTheme(s.theme || "system");
        setAccent(s.accent_color || "");
        setLang((s.language as Lang) || "en");
        if (!s.setup_done) {
          get<{ empty?: boolean }>("/api/info").then((i) => {
            if (i.empty) setSetup({ base: s.base_currency });
          }).catch(() => {});
        }
      })
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
        <ThemeRoot dir={lang === "ar" ? "rtl" : "ltr"} pref={theme} onChange={changeTheme}
          accent={accent} onAccent={changeAccent}>
          <div className="frame">
            <NavDrawer path={path} />
            <main className="main"><UpdateBanner />{children}</main>
          </div>
          {setup && <SetupAssistant base={setup.base} lang={lang}
            onLang={(l) => { setLang(l); put("/api/settings", { language: l }).catch(() => {}); }}
            onDone={() => setSetup(null)} />}
          <DownloadToasts />
          <RatePrompt />
          <QuickAddHotkey />
          <CommandPalette />
        </ThemeRoot>
      </I18nProvider>
    </PrefsCtx.Provider>
  );
}
