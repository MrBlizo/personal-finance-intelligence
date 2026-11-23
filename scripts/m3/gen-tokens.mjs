// Material 3 colour tokens for every Personal Finance surface, from one seed colour.
//
//   node --import ./scripts/m3/resolve-js.mjs scripts/m3/gen-tokens.mjs [#3949AB]
//
// Writes design/m3-tokens.json (the source of truth), the CSS custom
// properties for the Windows app and the website, and the colours for the
// phone app.
//
// One look in light and dark: Material 3 Expressive, SchemeVibrant from the
// Personal Finance indigo seed (#3949AB) at standard contrast. The bright tiles (lavender, lime, pink,
// cyan) keep the SAME light colours in dark mode, so the app looks like
// itself in both; only surfaces and text change. Money colours are
// harmonized toward the seed. Charts use one mid-tone palette in both modes
// (CHART below). Every text pair is checked for 4.5:1 contrast.
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

const SEED = process.argv[2] || "#3949AB";
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

// Chart series colours, the same in light and dark: mid-tones from the tile
// family (blue, pink, lime, cyan, orange, violet, amber), checked with the
// dataviz palette validator (lightness band, CVD separation). Keys are the
// Okabe-Ito names the backend figures use; Plot.tsx repaints them.
export const CHART = {
  blue: "#4C6EF5", verm: "#EC5F9E", green: "#7CB518", sky: "#1FB5D8",
  orange: "#F2994A", purple: "#9775FA", yellow: "#C99A06", grey: "#8A8F98",
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
  // Tiles: the same light containers in both modes.
  for (const [name, hex] of Object.entries(ACCENTS)) {
    const p = TonalPalette.fromInt(argbFromHex(hex));
    out[name] = hexFromArgb(p.tone(dark ? 80 : 40));
    out["on" + cap(name)] = hexFromArgb(p.tone(dark ? 20 : 100));
    out[name + "Container"] = hexFromArgb(p.tone(90));
    out["on" + cap(name) + "Container"] = hexFromArgb(p.tone(10));
  }
  const light = new SchemeVibrant(Hct.fromInt(seed), false, 0.0);
  out.lavenderContainer = hexFromArgb(
    MaterialDynamicColors.primaryContainer.getArgb(light));
  out.onLavenderContainer = hexFromArgb(
    MaterialDynamicColors.onPrimaryContainer.getArgb(light));
  // Filled buttons and the FAB: the vivid light primary in both modes.
  out.brand = hexFromArgb(MaterialDynamicColors.primary.getArgb(light));
  out.onBrand = hexFromArgb(MaterialDynamicColors.onPrimary.getArgb(light));
  for (const [name, hex] of Object.entries(CHART)) out["chart" + cap(name)] = hex;
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
  ["onLavenderContainer", "lavenderContainer"], ["onBrand", "brand"],
];
function audit(name, roles) {
  const bad = PAIRS.map(([a, b]) => [a, b, contrast(roles[a], roles[b])])
    .filter(([, , r]) => r < 4.5);
  for (const [a, b, r] of bad) console.error(`${name}: ${a} on ${b} is ${r.toFixed(2)}:1`);
  if (bad.length) {
    throw new Error(`${name} has text pairs under 4.5:1 (listed above). `
      + "Adjust the seed or the accents, then run this script again.");
  }
}

const tokens = { seed: SEED.toUpperCase(), variant: "vibrant", contrast: 0,
  light: scheme(SEED, false), dark: scheme(SEED, true) };
audit("light", tokens.light);
audit("dark", tokens.dark);
const header = (c) => `${c} Generated by scripts/m3/gen-tokens.mjs from seed ${tokens.seed}`
  + ` (SchemeVibrant, one look in light and dark). Do not edit by hand.`;
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
  .concat(["lavenderContainer", "onLavenderContainer"])
  .map((k) => `    ${k}: ${dartColor(o[k])},`).join("\n");
const dartMoney = (o) => Object.keys(MONEY).flatMap((n) => [
  n, "on" + cap(n), n + "Container", "on" + cap(n) + "Container"])
  .map((k) => `    ${k}: ${dartColor(o[k])},`).join("\n");
write("mobile/lib/ui/m3_tokens.dart", `${header("//")}
import 'package:flutter/material.dart';

/// The Personal Finance seed colour, shared with the Windows app and the website.
const pfiSeed = ${dartColor(tokens.seed)};

/// The light and dark schemes for [pfiSeed], identical to the PC's.
const pfiLightScheme = ColorScheme(
  brightness: Brightness.light,
${dartScheme(tokens.light)}
);

const pfiDarkScheme = ColorScheme(
  brightness: Brightness.dark,
${dartScheme(tokens.dark)}
);

/// Chart series colours, the same in light and dark (see CHART in
/// scripts/m3/gen-tokens.mjs).
const chartColors = <Color>[
${Object.values(CHART).slice(0, 7).map((h) => "  " + dartColor(h) + ",").join("\n")}
];

/// Expressive tile colours (lavender, lime, pink, cyan): the same light
/// containers in light and dark mode.
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
    required this.lavenderContainer,
    required this.onLavenderContainer,
  });

  final Color lavenderContainer, onLavenderContainer;
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
      lavenderContainer: l(lavenderContainer, other.lavenderContainer),
      onLavenderContainer: l(onLavenderContainer, other.onLavenderContainer),
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
