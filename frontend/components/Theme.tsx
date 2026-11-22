"use client";
// Material 3 everywhere: the Fluent UI v9 components are themed from a
// Material 3 colour scheme (PFI violet by default, or the seed chosen in
// Settings), and the same roles are exposed to CSS as --md-sys-color-*.
import {
  BrandVariants, FluentProvider, Theme, createDarkTheme, createLightTheme,
  Button, Menu, MenuItemRadio, MenuList, MenuPopover, MenuTrigger, Tooltip,
} from "@fluentui/react-components";
import {
  DarkTheme20Regular, WeatherMoon20Regular, WeatherSunny20Regular,
} from "@fluentui/react-icons";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useT } from "@/lib/i18n";
import { cssVars, isNeon, primaryRamp, schemeFor, SEED } from "@/lib/m3";
import { notifyTheme } from "@/lib/shell";

/** The PFI seed colour, used when no accent is chosen. */
export const DEFAULT_ACCENT = SEED;
/** Seed colours offered in Settings; each yields a full Material 3 scheme. */
export const ACCENTS = [
  { id: "", label: "PFI violet", hex: DEFAULT_ACCENT },
  { id: "#2F6FE4", label: "Blue", hex: "#2F6FE4" },
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

/** ``a`` with an M3 state layer of ``b`` at ``pct`` percent on top. */
const layer = (a: string, b: string, pct: number) =>
  `color-mix(in srgb, ${b} ${pct}%, ${a})`;
const font = "'Roboto Flex Variable', 'Noto Sans Arabic Variable', "
  + "system-ui, sans-serif";

/** Fluent UI v9 theme whose every token comes from a Material 3 scheme. */
export function makeTheme(seed: string, dark: boolean): Theme {
  const r = schemeFor(seed, dark);
  const ramp = primaryRamp(seed);
  const brand = Object.fromEntries(ramp.map((hex, i) => [(i + 1) * 10, hex]));
  const base = (dark ? createDarkTheme : createLightTheme)(
    brand as unknown as BrandVariants);
  return {
    ...base,
    fontFamilyBase: font,
    fontFamilyNumeric: font,
    fontWeightSemibold: 600,
    // Shape scale: extra-small for fields, medium for menus, extra-large
    // for dialogs. Buttons are fully rounded in globals.css.
    borderRadiusSmall: "4px",
    borderRadiusMedium: "4px",
    borderRadiusLarge: "12px",
    borderRadiusXLarge: "28px",
    colorBrandBackground: r.primary,
    colorBrandBackgroundHover: layer(r.primary, r.onPrimary, 8),
    colorBrandBackgroundPressed: layer(r.primary, r.onPrimary, 10),
    colorBrandBackgroundSelected: r.primary,
    colorBrandBackground2: r.primaryContainer,
    colorNeutralForegroundOnBrand: r.onPrimary,
    colorBrandForeground1: r.primary,
    colorBrandForeground2: r.primary,
    colorBrandForegroundLink: r.primary,
    colorBrandForegroundLinkHover: r.primary,
    colorBrandForegroundLinkPressed: r.primary,
    colorBrandStroke1: r.primary,
    colorCompoundBrandStroke: r.primary,
    colorCompoundBrandStrokeHover: r.primary,
    colorCompoundBrandStrokePressed: r.primary,
    colorCompoundBrandBackground: r.primary,
    colorCompoundBrandBackgroundHover: layer(r.primary, r.onPrimary, 8),
    colorCompoundBrandBackgroundPressed: layer(r.primary, r.onPrimary, 10),
    colorCompoundBrandForeground1: r.primary,
    colorNeutralForeground1: r.onSurface,
    colorNeutralForeground1Hover: r.onSurface,
    colorNeutralForeground1Pressed: r.onSurface,
    colorNeutralForeground2: r.onSurfaceVariant,
    colorNeutralForeground2Hover: r.onSurface,
    colorNeutralForeground2Pressed: r.onSurface,
    colorNeutralForeground3: r.onSurfaceVariant,
    colorNeutralForeground4: r.outline,
    colorNeutralBackground1: r.surfaceContainerLow,
    colorNeutralBackground1Hover: layer(r.surfaceContainerLow, r.onSurface, 8),
    colorNeutralBackground1Pressed: layer(r.surfaceContainerLow, r.onSurface, 10),
    colorNeutralBackground1Selected: r.secondaryContainer,
    colorNeutralBackground2: r.surfaceContainer,
    colorNeutralBackground3: r.surface,
    colorNeutralBackground4: r.surfaceContainerHigh,
    colorNeutralBackground5: r.surfaceContainerHighest,
    colorNeutralCardBackground: r.surfaceContainerLow,
    colorSubtleBackgroundHover: layer("transparent", r.onSurface, 8),
    colorSubtleBackgroundPressed: layer("transparent", r.onSurface, 10),
    colorSubtleBackgroundSelected: r.secondaryContainer,
    colorTransparentBackgroundHover: layer("transparent", r.onSurface, 8),
    colorTransparentBackgroundPressed: layer("transparent", r.onSurface, 10),
    colorNeutralStroke1: r.outlineVariant,
    colorNeutralStroke1Hover: r.outline,
    colorNeutralStroke1Pressed: r.outline,
    colorNeutralStroke2: r.outlineVariant,
    colorNeutralStroke3: r.outlineVariant,
    colorNeutralStrokeAccessible: r.outline,
    colorNeutralStrokeAccessibleHover: r.onSurfaceVariant,
    colorNeutralStrokeAccessiblePressed: r.onSurface,
    colorStrokeFocus2: r.secondary,
    colorStatusDangerBackground3: r.error,
    colorStatusDangerForeground1: r.error,
    colorStatusSuccessForeground1: r.positive,
    colorStatusWarningForeground1: r.warning,
    colorPaletteRedBackground3: r.error,
    colorPaletteRedForeground1: r.error,
    colorPaletteGreenForeground1: r.positive,
    colorNeutralShadowAmbient: "rgba(0,0,0,0.12)",
    colorNeutralShadowKey: "rgba(0,0,0,0.14)",
  };
}

/** Writes the scheme as ``--md-sys-color-*`` on the document root. */
function applyScheme(seed: string, dark: boolean) {
  const style = document.documentElement.style;
  for (const [name, value] of cssVars(schemeFor(seed, dark))) {
    style.setProperty(name, value);
  }
}

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
  const theme = useMemo(() => makeTheme(hex, dark), [dark, hex]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.dataset.neon = isNeon(hex, dark) ? "1" : "0";
    applyScheme(hex, dark);
  }, [dark, hex]);
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
