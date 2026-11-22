// Material 3 colour roles at run time, for accents other than the PFI seed.
// Same algorithm as scripts/m3/gen-tokens.mjs (SchemeVibrant, standard
// contrast, money colours harmonized toward the seed, lime and pink accents
// left loud), so a chosen accent gets a complete, accessible scheme. The
// hand-tuned Neon dark palette belongs to the PFI seed only.
import {
  Blend, Hct, MaterialDynamicColors, SchemeVibrant, TonalPalette,
  argbFromHex, hexFromArgb,
} from "@material/material-color-utilities";
import tokens from "./m3-tokens.json";

export type Roles = Record<string, string>;

/** The PFI seed colour the static tokens were generated from. */
export const SEED = tokens.seed;

const ROLES = Object.keys(tokens.light).filter((k) =>
  k in MaterialDynamicColors);
const MONEY: Record<string, string> = {
  positive: "#1E8E3E", negative: "#D93025", warning: "#E8A33D",
};
const ACCENTS: Record<string, string> = { lime: "#C6F432", pink: "#FF5AB4", cyan: "#24D3F2" };
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** All colour roles for ``seedHex`` in light or dark. */
export function schemeFor(seedHex: string, dark: boolean): Roles {
  if (seedHex.toUpperCase() === SEED) return dark ? tokens.dark : tokens.light;
  const seed = argbFromHex(seedHex);
  const s = new SchemeVibrant(Hct.fromInt(seed), dark, 0);
  const dyn = MaterialDynamicColors as unknown as Record<
    string, { getArgb: (x: SchemeVibrant) => number }>;
  const out: Roles = {};
  for (const r of ROLES) out[r] = hexFromArgb(dyn[r].getArgb(s));
  for (const [name, hex] of Object.entries(MONEY)) {
    const p = TonalPalette.fromInt(Blend.harmonize(argbFromHex(hex), seed));
    out[name] = hexFromArgb(p.tone(dark ? 80 : 40));
    out["on" + cap(name)] = hexFromArgb(p.tone(dark ? 20 : 100));
    out[name + "Container"] = hexFromArgb(p.tone(dark ? 30 : 90));
    out["on" + cap(name) + "Container"] = hexFromArgb(p.tone(dark ? 90 : 10));
  }
  for (const [name, hex] of Object.entries(ACCENTS)) {
    const p = TonalPalette.fromInt(argbFromHex(hex));
    out[name] = hexFromArgb(p.tone(dark ? 80 : 40));
    out["on" + cap(name)] = hexFromArgb(p.tone(dark ? 20 : 100));
    out[name + "Container"] = hexFromArgb(p.tone(dark ? 30 : 90));
    out["on" + cap(name) + "Container"] = hexFromArgb(p.tone(dark ? 90 : 10));
  }
  return out;
}

/** True when the hand-tuned Neon dark palette is in use. */
export const isNeon = (seedHex: string, dark: boolean) =>
  dark && seedHex.toUpperCase() === SEED;

/** Tones 5..98 of the primary palette, for Fluent's 16 brand shades. */
export function primaryRamp(seedHex: string): string[] {
  const s = new SchemeVibrant(Hct.fromInt(argbFromHex(seedHex)), false, 0);
  const tones = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 95, 98];
  return tones.map((t) => hexFromArgb(s.primaryPalette.tone(t)));
}

/** ``--md-sys-color-*`` custom properties for a set of roles. */
export const cssVars = (roles: Roles): [string, string][] =>
  Object.entries(roles).map(([k, v]) =>
    ["--md-sys-color-" + k.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase()), v]);
