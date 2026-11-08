"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { inShell, notifyRoute, onShellNavigate } from "@/lib/shell";

export const NAV = [
  { href: "/", label: "Dashboard", glyph: "" },
  { href: "/transactions/", label: "Transactions", glyph: "" },
  { href: "/accounts/", label: "Accounts", glyph: "" },
  { href: "/import/", label: "Import", glyph: "" },
  { href: "/budgets/", label: "Budgets", glyph: "" },
  { href: "/goals/", label: "Goals", glyph: "" },
  { href: "/investments/", label: "Investments", glyph: "" },
  { href: "/forecast/", label: "Forecast", glyph: "" },
  { href: "/insights/", label: "Insights", glyph: "" },
  { href: "/settings/", label: "Settings", glyph: "" },
];

export default function AppFrame({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  useEffect(() => {
    if (inShell()) document.documentElement.dataset.shell = "1";
    return onShellNavigate((p) => router.push(p));
  }, [router]);
  useEffect(() => { notifyRoute(path); }, [path]);
  const norm = (p: string) => (p.endsWith("/") ? p : p + "/");
  return (
    <>
      <aside className="sidebar">
        <div className="brand">Personal Finance Intelligence</div>
        <nav className="nav">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
              className={norm(path) === n.href ? "active" : ""}>
              <span style={{ fontFamily: "Segoe Fluent Icons, Segoe MDL2 Assets" }}
                aria-hidden>{n.glyph}</span>
              {n.label}
            </Link>))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </>
  );
}
