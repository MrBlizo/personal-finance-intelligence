// Material 3 colour tokens for every PFI surface, from one seed colour.
//
//   node --import ./scripts/m3/resolve-js.mjs scripts/m3/gen-tokens.mjs [#2F6FE4]
//
// Writes design/m3-tokens.json (the source of truth), the CSS custom
// properties for the Windows app and the website, and the colours for the
// phone app.
//
// Light: Material 3 Expressive, SchemeVibrant from the PFI violet seed at
// standard contrast, plus two loud accents (lime and pink) that are NOT
// harmonized, so they pop against the violet like the M3 Expressive
// showcase. Money colours are harmonized toward the seed.
// Dark: "Neon" - a hand-tuned synthwave palette (deep indigo surfaces, neon
// pink primary, electric violet, cyan, mint and sun-gold). Every text pair is
// checked for 4.5:1 contrast when this script runs.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(path.join(root, "frontend/package.json"));
const mcu = await import(
  pathToFileURL(require.resolve("@material/material-color-utilities")).href);
const { argbFromHex, hexFromArgb, Hct, SchemeVibrant, MaterialDynamicColors,
  Blend, TonalPalette } = mcu;

const SEED = process.argv[2] || "#8E5CF7";
const ROLES = [
  "primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
  "secondary", "onSecondary", "secondaryContainer", "onSecondaryContainer",
  "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer",
  "error", "onError", "errorContainer", "onErrorContainer",
  "surface", "onSurface", "onSurfaceVariant", "surfaceDim", "surfaceBright",
  "surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer",
  "surfaceContainerHigh", "surfaceContainerHighest", "outline",
  "outlineVariant", "inverseSurface", "inverseOnSurface", "inversePrimary",
  "scrim", "shadow", "surfaceTint",
];
export const MONEY = { positive: "#1E8E3E", negative: "#D93025", warning: "#E8A33D" };
// Loud accents for the Expressive look; deliberately not harmonized.
export const ACCENTS = { lime: "#C6F432", pink: "#FF5AB4", cyan: "#24D3F2" };

// Neon synthwave dark palette, hand-tuned.
export const NEON = {
  primary: "#FF5AD9", onPrimary: "#3B0030",
  primaryContainer: "#7A1FA2", onPrimaryContainer: "#FFD8F6",
  secondary: "#B69CFF", onSecondary: "#2A0E6B",
  secondaryContainer: "#3D2A7A", onSecondaryContainer: "#E6DCFF",
  tertiary: "#4DE8FF", onTertiary: "#00363F",
  tertiaryContainer: "#005A68", onTertiaryContainer: "#B8F3FF",
  error: "#FF7A9A", onError: "#4A0018",
  errorContainer: "#6E1030", onErrorContainer: "#FFD9E0",
  surface: "#120B24", onSurface: "#F4ECFF", onSurfaceVariant: "#C3B3E6",
  surfaceDim: "#0D081A", surfaceBright: "#2A1F45",
  surfaceContainerLowest: "#0B0717", surfaceContainerLow: "#17102E",
  surfaceContainer: "#1C1436", surfaceContainerHigh: "#241A44",
  surfaceContainerHighest: "#2D2152", outline: "#9A88C4",
  outlineVariant: "#3E3163", inverseSurface: "#F4ECFF",
  inverseOnSurface: "#241A44", inversePrimary: "#A0158A",
  scrim: "#000000", shadow: "#000000", surfaceTint: "#FF5AD9",
  positive: "#5CFFB0", onPositive: "#003822",
  positiveContainer: "#0B5A3A", onPositiveContainer: "#B6FFD9",
  negative: "#FF7A9A", onNegative: "#4A0018",
  negativeContainer: "#6E1030", onNegativeContainer: "#FFD9E0",
  warning: "#FFC857", onWarning: "#3F2A00",
  warningContainer: "#6A4500", onWarningContainer: "#FFE2A8",
  lime: "#D4FF4F", onLime: "#283300",
  limeContainer: "#3E5200", onLimeContainer: "#E9FFB0",
  pink: "#FF5AD9", onPink: "#3B0030",
  pinkContainer: "#7A1FA2", onPinkContainer: "#FFD8F6",
  cyan: "#4DE8FF", onCyan: "#00363F",
  cyanContainer: "#005A68", onCyanContainer: "#B8F3FF",
};

const cap = (s) => s[0].toUpperCase() + s.slice(1);
const kebab = (s) => s.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());

function scheme(seedHex, dark) {
  const seed = argbFromHex(seedHex);
  const s = new SchemeVibrant(Hct.fromInt(seed), dark, 0.0);
  const out = {};
  for (const r of ROLES) out[r] = hexFromArgb(MaterialDynamicColors[r].getArgb(s));
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

function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const contrast = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};
// Text/background pairs that must reach 4.5:1 in every scheme.
const PAIRS = [
  ["onSurface", "surface"], ["onSurfaceVariant", "surface"],
  ["onSurfaceVariant", "surfaceContainerHigh"], ["primary", "surface"],
  ["primary", "surfaceContainerLow"], ["onPrimary", "primary"],
  ["onPrimaryContainer", "primaryContainer"],
  ["onSecondaryContainer", "secondaryContainer"],
  ["onTertiaryContainer", "tertiaryContainer"],
  ["positive", "surfaceContainerLow"], ["negative", "surfaceContainerLow"],
  ["warning", "surfaceContainerLow"],
  ["onPositiveContainer", "positiveContainer"],
  ["onNegativeContainer", "negativeContainer"],
  ["onWarningContainer", "warningContainer"],
  ["onLimeContainer", "limeContainer"], ["onPinkContainer", "pinkContainer"],
  ["onCyanContainer", "cyanContainer"],
];
function audit(name, roles) {
  const bad = PAIRS.map(([a, b]) => [a, b, contrast(roles[a], roles[b])])
    .filter(([, , r]) => r < 4.5);
  for (const [a, b, r] of bad) console.error(`${name}: ${a} on ${b} is ${r.toFixed(2)}:1`);
  if (bad.length) {
    throw new Error(`${name} has text pairs under 4.5:1 (listed above). `
      + "Adjust the seed or the NEON palette, then run this script again.");
  }
}

const tokens = { seed: SEED.toUpperCase(), variant: "vibrant", contrast: 0,
  light: scheme(SEED, false), dark: { ...scheme(SEED, true), ...NEON } };
audit("light", tokens.light);
audit("dark (neon)", tokens.dark);
const header = (c) => `${c} Generated by scripts/m3/gen-tokens.mjs from seed ${tokens.seed}`
  + ` (SchemeVibrant light, Neon dark). Do not edit by hand.`;
const vars = (o) => Object.entries(o)
  .map(([k, v]) => `  --md-sys-color-${kebab(k)}: ${v};`).join("\n");
const write = (rel, text) => {
  fs.writeFileSync(path.join(root, rel), text);
  console.log("wrote", rel);
};

write("design/m3-tokens.json", JSON.stringify(tokens, null, 2) + "\n");
// The Windows screens import the same JSON for run-time accents.
write("frontend/lib/m3-tokens.json", JSON.stringify(tokens, null, 2) + "\n");
write("frontend/app/m3-tokens.css", `/* ${header("").trim()} */
:root {
${vars(tokens.light)}
}
:root[data-theme="dark"] {
${vars(tokens.dark)}
}
`);
write("docs/m3-tokens.css", `/* ${header("").trim()} */
:root {
${vars(tokens.light)}
}
@media (prefers-color-scheme: dark) {
  :root {
${vars(tokens.dark).replace(/^/gm, "  ")}
  }
}
`);
const dartColor = (hex) => `Color(0xFF${hex.slice(1).toUpperCase()})`;
const FLUTTER_ROLES = [
  "primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
  "secondary", "onSecondary", "secondaryContainer", "onSecondaryContainer",
  "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer",
  "error", "onError", "errorContainer", "onErrorContainer",
  "surface", "onSurface", "surfaceDim", "surfaceBright",
  "surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer",
  "surfaceContainerHigh", "surfaceContainerHighest", "onSurfaceVariant",
  "outline", "outlineVariant", "shadow", "scrim", "inverseSurface",
  "inversePrimary", "surfaceTint",
];
const dartScheme = (o) => FLUTTER_ROLES
  .map((k) => `  ${k}: ${dartColor(o[k])},`).join("\n")
  + `\n  onInverseSurface: ${dartColor(o.inverseOnSurface)},`;
const dartAccents = (o) => Object.keys(ACCENTS).flatMap((n) => [
  n, "on" + cap(n), n + "Container", "on" + cap(n) + "Container"])
  .map((k) => `    ${k}: ${dartColor(o[k])},`).join("\n");
const dartMoney = (o) => Object.keys(MONEY).flatMap((n) => [
  n, "on" + cap(n), n + "Container", "on" + cap(n) + "Container"])
  .map((k) => `    ${k}: ${dartColor(o[k])},`).join("\n");
write("mobile/lib/ui/m3_tokens.dart", `${header("//")}
import 'package:flutter/material.dart';

/// The PFI seed colour, shared with the Windows app and the website.
const pfiSeed = ${dartColor(tokens.seed)};

/// The "Neon" dark scheme used with [pfiSeed] (synthwave, hand-tuned).
const neonDarkScheme = ColorScheme(
  brightness: Brightness.dark,
${dartScheme(tokens.dark)}
);

/// Loud Expressive accents (lime, pink), not harmonized on purpose.
class AccentColors extends ThemeExtension<AccentColors> {
  const AccentColors({
    required this.lime,
    required this.onLime,
    required this.limeContainer,
    required this.onLimeContainer,
    required this.pink,
    required this.onPink,
    required this.pinkContainer,
    required this.onPinkContainer,
    required this.cyan,
    required this.onCyan,
    required this.cyanContainer,
    required this.onCyanContainer,
  });

  final Color lime, onLime, limeContainer, onLimeContainer;
  final Color pink, onPink, pinkContainer, onPinkContainer;
  final Color cyan, onCyan, cyanContainer, onCyanContainer;

  static const light = AccentColors(
${dartAccents(tokens.light)}
  );

  static const dark = AccentColors(
${dartAccents(tokens.dark)}
  );

  @override
  AccentColors copyWith() => this;

  @override
  AccentColors lerp(AccentColors? other, double t) {
    if (other == null) return this;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return AccentColors(
      lime: l(lime, other.lime),
      onLime: l(onLime, other.onLime),
      limeContainer: l(limeContainer, other.limeContainer),
      onLimeContainer: l(onLimeContainer, other.onLimeContainer),
      pink: l(pink, other.pink),
      onPink: l(onPink, other.onPink),
      pinkContainer: l(pinkContainer, other.pinkContainer),
      onPinkContainer: l(onPinkContainer, other.onPinkContainer),
      cyan: l(cyan, other.cyan),
      onCyan: l(onCyan, other.onCyan),
      cyanContainer: l(cyanContainer, other.cyanContainer),
      onCyanContainer: l(onCyanContainer, other.onCyanContainer),
    );
  }
}

/// Money colours (in, out, warning) harmonized toward [pfiSeed].
class MoneyColors extends ThemeExtension<MoneyColors> {
  const MoneyColors({
    required this.positive,
    required this.onPositive,
    required this.positiveContainer,
    required this.onPositiveContainer,
    required this.negative,
    required this.onNegative,
    required this.negativeContainer,
    required this.onNegativeContainer,
    required this.warning,
    required this.onWarning,
    required this.warningContainer,
    required this.onWarningContainer,
  });

  final Color positive, onPositive, positiveContainer, onPositiveContainer;
  final Color negative, onNegative, negativeContainer, onNegativeContainer;
  final Color warning, onWarning, warningContainer, onWarningContainer;

  static const light = MoneyColors(
${dartMoney(tokens.light)}
  );

  static const dark = MoneyColors(
${dartMoney(tokens.dark)}
  );

  @override
  MoneyColors copyWith() => this;

  @override
  MoneyColors lerp(MoneyColors? other, double t) {
    if (other == null) return this;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return MoneyColors(
      positive: l(positive, other.positive),
      onPositive: l(onPositive, other.onPositive),
      positiveContainer: l(positiveContainer, other.positiveContainer),
      onPositiveContainer: l(onPositiveContainer, other.onPositiveContainer),
      negative: l(negative, other.negative),
      onNegative: l(onNegative, other.onNegative),
      negativeContainer: l(negativeContainer, other.negativeContainer),
      onNegativeContainer: l(onNegativeContainer, other.onNegativeContainer),
      warning: l(warning, other.warning),
      onWarning: l(onWarning, other.onWarning),
      warningContainer: l(warningContainer, other.warningContainer),
      onWarningContainer: l(onWarningContainer, other.onWarningContainer),
    );
  }
}
`);
