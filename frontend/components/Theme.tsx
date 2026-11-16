"use client";
// Fluent UI v9 themes built from one accent colour: Windows 11 blue by
// default or the colour chosen in Settings. Every brand shade is derived
// from it, with rounder corners and the lighter accent WinUI uses in dark
// mode.
import {
  BrandVariants, FluentProvider, Theme, createDarkTheme, createLightTheme,
  Button, Menu, MenuItemRadio, MenuList, MenuPopover, MenuTrigger, Tooltip,
} from "@fluentui/react-components";
import {
  DarkTheme20Regular, WeatherMoon20Regular, WeatherSunny20Regular,
} from "@fluentui/react-icons";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useT } from "@/lib/i18n";
import { notifyTheme } from "@/lib/shell";

/** The Windows 11 default accent, used when no colour is chosen. */
export const DEFAULT_ACCENT = "#005FB8";
/** Accent colours offered in Settings (Material-style tones). */
export const ACCENTS = [
  { id: "", label: "Windows blue", hex: DEFAULT_ACCENT },
  { id: "#6750A4", label: "Violet", hex: "#6750A4" },
  { id: "#3949AB", label: "Indigo", hex: "#3949AB" },
  { id: "#00796B", label: "Teal", hex: "#00796B" },
  { id: "#2E7D32", label: "Green", hex: "#2E7D32" },
  { id: "#827717", label: "Olive", hex: "#827717" },
  { id: "#E65100", label: "Orange", hex: "#E65100" },
  { id: "#C62828", label: "Red", hex: "#C62828" },
  { id: "#AD1457", label: "Pink", hex: "#AD1457" },
  { id: "#5D4037", label: "Brown", hex: "#5D4037" },
  { id: "#455A64", label: "Slate", hex: "#455A64" },
];

type Rgb = [number, number, number];
const toRgb = (hex: string): Rgb => {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb;
};
const toHex = (c: Rgb) => "#" + c.map((v) =>
  Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
const mix = (a: Rgb, b: Rgb, w: number): Rgb =>
  [0, 1, 2].map((i) => a[i] * (1 - w) + b[i] * w) as Rgb;

/** Sixteen Fluent brand shades with ``accent`` at step 80. */
export function brandFrom(accent: string): BrandVariants {
  const base = toRgb(accent);
  const out: Record<number, string> = {};
  for (let step = 10; step <= 160; step += 10) {
    const k = (step - 80) / 80;
    out[step] = toHex(k < 0 ? mix(base, [0, 0, 0], -k * 0.85)
      : mix(base, [255, 255, 255], k * 0.9));
  }
  return out as unknown as BrandVariants;
}

/** The lighter accent used on dark backgrounds (like WinUI's dark mode). */
export const darkAccent = (accent: string) =>
  toHex(mix(toRgb(accent), [255, 255, 255], 0.45));

const font = "'Segoe UI Variable Text', 'Segoe UI', system-ui, -apple-system, "
  + "'Noto Sans Arabic', sans-serif";
const shared: Partial<Theme> = {
  fontFamilyBase: font,
  fontFamilyNumeric: font,
  borderRadiusMedium: "8px",
  borderRadiusLarge: "12px",
  borderRadiusXLarge: "20px",
};

export function makeLight(accent: string): Theme {
  const brand = brandFrom(accent);
  return {
    ...createLightTheme(brand), ...shared,
    colorNeutralForeground1: "rgba(0,0,0,0.896)",
    colorNeutralForeground2: "rgba(0,0,0,0.606)",
    colorNeutralForeground3: "rgba(0,0,0,0.45)",
    colorBrandForeground1: brand[60],
    colorBrandForegroundLink: brand[60],
    colorNeutralBackground1: "#FFFFFF",
    colorNeutralBackground2: "#F9F9F9",
    colorNeutralBackground3: "#F3F3F3",
    colorNeutralStroke1: "rgba(0,0,0,0.0803)",
    colorNeutralStroke2: "rgba(0,0,0,0.0578)",
    colorNeutralStrokeAccessible: "rgba(0,0,0,0.4458)",
  };
}

export function makeDark(accent: string): Theme {
  const brand = brandFrom(accent);
  const light = darkAccent(accent);
  const lighter = toHex(mix(toRgb(light), [255, 255, 255], 0.4));
  return {
    ...createDarkTheme(brand), ...shared,
    colorBrandBackground: light,
    colorBrandBackgroundHover: toHex(mix(toRgb(light), [0, 0, 0], 0.08)),
    colorBrandBackgroundPressed: toHex(mix(toRgb(light), [0, 0, 0], 0.15)),
    colorBrandBackgroundSelected: light,
    colorNeutralForegroundOnBrand: "#000000",
    colorBrandForeground1: lighter,
    colorBrandForeground2: lighter,
    colorBrandForegroundLink: lighter,
    colorBrandForegroundLinkHover: lighter,
    colorCompoundBrandStroke: light,
    colorCompoundBrandBackground: light,
    colorNeutralForeground1: "#FFFFFF",
    colorNeutralForeground2: "rgba(255,255,255,0.786)",
    colorNeutralForeground3: "rgba(255,255,255,0.544)",
    colorNeutralBackground1: "#2C2C2C",
    colorNeutralBackground2: "#272727",
    colorNeutralBackground3: "#202020",
    colorNeutralStroke1: "rgba(255,255,255,0.0837)",
    colorNeutralStroke2: "rgba(255,255,255,0.0605)",
  };
}

export const lightTheme: Theme = makeLight(DEFAULT_ACCENT);
export const darkTheme: Theme = makeDark(DEFAULT_ACCENT);

export type ThemePref = "system" | "light" | "dark";
type ThemeState = {
  pref: ThemePref; dark: boolean; setPref: (p: ThemePref) => void;
  accent: string; setAccent: (hex: string) => void;
};
const ThemeCtx = createContext<ThemeState>({
  pref: "system", dark: false, setPref: () => {}, accent: "", setAccent: () => {},
});
/** The chosen theme ("system", "light" or "dark") and whether dark is shown. */
export const useTheme = () => useContext(ThemeCtx);

function useSystemDark() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setDark(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return dark;
}

export function ThemeRoot({ dir, pref, onChange, accent, onAccent, children }: {
  dir: "ltr" | "rtl"; pref: ThemePref; onChange: (p: ThemePref) => void;
  accent: string; onAccent: (hex: string) => void; children: ReactNode;
}) {
  const system = useSystemDark();
  const dark = pref === "system" ? system : pref === "dark";
  const hex = accent || DEFAULT_ACCENT;
  const theme = useMemo(() => (dark ? makeDark(hex) : makeLight(hex)), [dark, hex]);
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = dark ? "dark" : "light";
    root.style.setProperty("--accent", dark ? darkAccent(hex) : hex);
    root.style.setProperty("--accent-text", String(theme.colorBrandForeground1));
  }, [dark, hex, theme]);
  useEffect(() => { notifyTheme(pref); }, [pref]);
  return (
    <ThemeCtx.Provider value={{ pref, dark, setPref: onChange, accent, setAccent: onAccent }}>
      <FluentProvider theme={theme} dir={dir} className="fluent-root">
        {children}
      </FluentProvider>
    </ThemeCtx.Provider>
  );
}

/** Light / dark / follow Windows, shown in every page header. */
export function ThemeMenu() {
  const t = useT();
  const { pref, dark, setPref } = useTheme();
  const icon = pref === "system" ? <DarkTheme20Regular />
    : dark ? <WeatherMoon20Regular /> : <WeatherSunny20Regular />;
  const label = t("Theme: {name}", { name: t(pref === "system" ? "Same as Windows"
    : pref === "dark" ? "Dark" : "Light") });
  return (
    <Menu checkedValues={{ theme: [pref] }}
      onCheckedValueChange={(_, d) => setPref(d.checkedItems[0] as ThemePref)}>
      <MenuTrigger disableButtonEnhancement>
        <Tooltip content={label} relationship="label">
          <Button appearance="subtle" icon={icon} className="theme-btn" />
        </Tooltip>
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          <MenuItemRadio name="theme" value="light" icon={<WeatherSunny20Regular />}>{t("Light")}</MenuItemRadio>
          <MenuItemRadio name="theme" value="dark" icon={<WeatherMoon20Regular />}>{t("Dark")}</MenuItemRadio>
          <MenuItemRadio name="theme" value="system" icon={<DarkTheme20Regular />}>{t("Same as Windows")}</MenuItemRadio>
        </MenuList>
      </MenuPopover>
    </Menu>
  );
}
