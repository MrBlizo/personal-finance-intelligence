"use client";
// Ctrl+K: jump to any page or run an action by typing a few letters.
// Typing anything else offers a transaction search for those words.
import { useRouter } from "next/navigation";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { NAV } from "./AppFrame";
import { I } from "./icons";
import { openQuickAdd } from "./QuickAdd";
import { useTheme } from "./Theme";
import { useT } from "@/lib/i18n";

export const GUIDE_URL = "https://mrblizo.github.io/personal-finance-intelligence/guide.html";

interface Command { id: string; label: string; glyph: string; hint?: string; keywords?: string; run: () => void }

export function CommandPalette() {
  const t = useT();
  const router = useRouter();
  const { dark, setPref } = useTheme();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const back = useRef<Element | null>(null);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        back.current = document.activeElement;
        setOpen((o) => !o);
        setQuery(""); setActive(0);
      }
    };
    const onEvent = () => { back.current = document.activeElement; setOpen(true); setQuery(""); setActive(0); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pfi:palette", onEvent);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("pfi:palette", onEvent); };
  }, []);
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 0); }, [open]);

  const close = () => {
    setOpen(false);
    (back.current as HTMLElement | null)?.focus?.();
  };
  const go = (href: string) => () => router.push(href);

  const commands: Command[] = useMemo(() => [
    { id: "add", label: t("Add transaction"), glyph: I.add, hint: "Ctrl+N", keywords: "new expense income", run: openQuickAdd },
    { id: "scan", label: t("Scan a receipt"), glyph: I.documentScanner, keywords: "photo ocr ticket", run: openQuickAdd },
    { id: "import", label: t("Import a bank statement"), glyph: I.uploadFile, keywords: "csv ofx camt qif", run: go("/import/") },
    { id: "year", label: t("Year in review"), glyph: I.celebration, keywords: "annual tax report pdf", run: go("/reports/?tab=year") },
    { id: "whatif", label: t("What if…?"), glyph: I.autoGraph, keywords: "scenario plan afford", run: go("/forecast/#what-if") },
    { id: "fi", label: t("Financial independence"), glyph: I.beachAccess, keywords: "fire retire", run: go("/forecast/#independence") },
    { id: "review", label: t("Review new transactions"), glyph: I.checklist, keywords: "uncategorised", run: go("/transactions/?review=1") },
    { id: "check", label: t("Check my data"), glyph: I.factCheck, keywords: "integrity problems", run: go("/settings/#data") },
    ...NAV.map((n) => ({ id: n.href, label: t(n.label), glyph: n.glyph, keywords: n.href.replaceAll("/", " "), run: go(n.href) })),
    { id: "theme", label: t(dark ? "Switch to light mode" : "Switch to dark mode"), glyph: I.contrast, keywords: "theme neon",
      run: () => setPref(dark ? "light" : "dark") },
    { id: "help", label: t("User guide"), glyph: I.help, keywords: "help how faq", run: () => { window.open(GUIDE_URL, "_blank", "noopener"); } },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t, dark]);

  const q = query.trim().toLowerCase();
  const shown = q ? commands.filter((c) => `${c.label} ${c.keywords ?? ""}`.toLowerCase().includes(q)) : commands;
  const items: Command[] = q
    ? [...shown, { id: "search", label: t("Search transactions for “{q}”", { q: query.trim() }), glyph: I.search,
        run: go(`/transactions/?q=${encodeURIComponent(query.trim())}`) }]
    : shown;
  const pick = (c: Command) => { close(); c.run(); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (items[active]) pick(items[active]); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  };
  if (!open) return null;
  return (
    <div className="palette-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label={t("Command palette")}>
        <div className="palette-input">
          <span className="icon" aria-hidden>{I.search}</span>
          <input ref={input} value={query} role="combobox" aria-expanded="true" aria-controls="palette-list"
            aria-activedescendant={items[active] ? `cmd-${items[active].id}` : undefined}
            aria-autocomplete="list" placeholder={t("Type a page, an action or words to search…")}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }} onKeyDown={onKey} />
          <kbd>Esc</kbd>
        </div>
        <ul id="palette-list" role="listbox" className="palette-list">
          {items.map((c, i) => (
            <li key={c.id} id={`cmd-${c.id}`} role="option" aria-selected={i === active}
              className={i === active ? "active" : ""} onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => { e.preventDefault(); pick(c); }}>
              <span className="icon" aria-hidden>{c.glyph}</span>
              <span className="grow">{c.label}</span>
              {c.hint && <kbd>{c.hint}</kbd>}
            </li>))}
        </ul>
        <div className="palette-foot caption">
          <span><kbd>↑</kbd><kbd>↓</kbd> {t("to move")}</span>
          <span><kbd>Enter</kbd> {t("to open")}</span>
          <span><kbd>Ctrl</kbd><kbd>K</kbd> {t("anywhere")}</span>
        </div>
      </div>
    </div>
  );
}

export const openPalette = () => window.dispatchEvent(new Event("pfi:palette"));
