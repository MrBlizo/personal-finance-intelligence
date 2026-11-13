"use client";
// Fluent UI v9 themes tuned to the Windows 11 (WinUI 3) palette: the
// system accent blue, Segoe UI Variable, WinUI corner radii, and the
// light-on-dark accent buttons WinUI uses in dark mode.
import {
  BrandVariants, FluentProvider, Theme, createDarkTheme, createLightTheme,
  Button, Menu, MenuItemRadio, MenuList, MenuPopover, MenuTrigger, Tooltip,
} from "@fluentui/react-components";
import {
  DarkTheme20Regular, WeatherMoon20Regular, WeatherSunny20Regular,
} from "@fluentui/react-icons";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { notifyTheme } from "@/lib/shell";

const brand: BrandVariants = {
  10: "#001126", 20: "#001B3D", 30: "#002654", 40: "#00306A",
  50: "#003A80", 60: "#004596", 70: "#0050A7", 80: "#005FB8",
  90: "#0A6CC5", 100: "#2B7DD0", 110: "#4A8FD9", 120: "#66A2E1",
  130: "#82B5E9", 140: "#9EC8F0", 150: "#BBDBF6", 160: "#D9EDFB",
};
const font = "'Segoe UI Variable Text', 'Segoe UI', system-ui, -apple-system, "
  + "'Noto Sans Arabic', sans-serif";
const shared: Partial<Theme> = {
  fontFamilyBase: font,
  fontFamilyNumeric: font,
  borderRadiusMedium: "4px",
  borderRadiusLarge: "8px",
  borderRadiusXLarge: "8px",
};

export const lightTheme: Theme = {
  ...createLightTheme(brand), ...shared,
  colorNeutralForeground1: "rgba(0,0,0,0.896)",
  colorNeutralForeground2: "rgba(0,0,0,0.606)",
  colorNeutralForeground3: "rgba(0,0,0,0.45)",
  colorBrandForeground1: "#003E92",
  colorBrandForegroundLink: "#003E92",
  colorNeutralBackground1: "#FFFFFF",
  colorNeutralBackground2: "#F9F9F9",
  colorNeutralBackground3: "#F3F3F3",
  colorNeutralStroke1: "rgba(0,0,0,0.0803)",
  colorNeutralStroke2: "rgba(0,0,0,0.0578)",
  colorNeutralStrokeAccessible: "rgba(0,0,0,0.4458)",
};

export const darkTheme: Theme = {
  ...createDarkTheme(brand), ...shared,
  colorBrandBackground: "#60CDFF",
  colorBrandBackgroundHover: "#5AB8E6",
  colorBrandBackgroundPressed: "#52A5CF",
  colorBrandBackgroundSelected: "#60CDFF",
  colorNeutralForegroundOnBrand: "#000000",
  colorBrandForeground1: "#99EBFF",
  colorBrandForeground2: "#99EBFF",
  colorBrandForegroundLink: "#99EBFF",
  colorBrandForegroundLinkHover: "#B5F0FF",
  colorCompoundBrandStroke: "#60CDFF",
  colorCompoundBrandBackground: "#60CDFF",
  colorNeutralForeground1: "#FFFFFF",
  colorNeutralForeground2: "rgba(255,255,255,0.786)",
  colorNeutralForeground3: "rgba(255,255,255,0.544)",
  colorNeutralBackground1: "#2C2C2C",
  colorNeutralBackground2: "#272727",
  colorNeutralBackground3: "#202020",
  colorNeutralStroke1: "rgba(255,255,255,0.0837)",
  colorNeutralStroke2: "rgba(255,255,255,0.0605)",
};

export type ThemePref = "system" | "light" | "dark";
type ThemeState = { pref: ThemePref; dark: boolean; setPref: (p: ThemePref) => void };
const ThemeCtx = createContext<ThemeState>({ pref: "system", dark: false, setPref: () => {} });
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

export function ThemeRoot({ dir, pref, onChange, children }: {
  dir: "ltr" | "rtl"; pref: ThemePref; onChange: (p: ThemePref) => void;
  children: ReactNode;
}) {
  const system = useSystemDark();
  const dark = pref === "system" ? system : pref === "dark";
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  useEffect(() => { notifyTheme(pref); }, [pref]);
  return (
    <ThemeCtx.Provider value={{ pref, dark, setPref: onChange }}>
      <FluentProvider theme={dark ? darkTheme : lightTheme} dir={dir}
        className="fluent-root">
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
