// Material 3 Expressive, shared with the Windows app and the website. The
// default Indigo seed uses the generated schemes from m3_tokens.dart; other
// seeds use the vibrant variant. Tiles (lavender, lime, pink, cyan), filled
// buttons and chart colours stay the same in light and dark mode.
import 'package:flutter/material.dart';

import 'm3_tokens.dart';

export 'm3_tokens.dart' show AccentColors, MoneyColors, chartColors, pfiSeed;

// Shape scale (same values as --md-sys-shape-corner-* on the PC).
const _extraSmall = 4.0;
const _large = 20.0;
const _extraLarge = 28.0;

ColorScheme _scheme(Color seed, Brightness brightness) {
  if (seed.toARGB32() == pfiSeed.toARGB32()) {
    return brightness == Brightness.dark ? pfiDarkScheme : pfiLightScheme;
  }
  return ColorScheme.fromSeed(
    seedColor: seed,
    brightness: brightness,
    dynamicSchemeVariant: DynamicSchemeVariant.vibrant,
  );
}

ThemeData buildTheme(Color seed, Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = _scheme(seed, brightness);
  // Filled buttons and the FAB keep the light primary in both modes.
  final brand = _scheme(seed, Brightness.light);
  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final text = base.textTheme;
  return base.copyWith(
    scaffoldBackgroundColor: scheme.surface,
    extensions: [
      dark ? MoneyColors.dark : MoneyColors.light,
      dark ? AccentColors.dark : AccentColors.light,
    ],
    // Expressive type: display and headline figures heavy and tight.
    textTheme: text.copyWith(
      displayLarge: text.displayLarge
          ?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -1.5),
      displayMedium: text.displayMedium
          ?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -1),
      displaySmall: text.displaySmall
          ?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.5),
      headlineLarge: text.headlineLarge?.copyWith(fontWeight: FontWeight.w700),
      headlineMedium:
          text.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
      headlineSmall: text.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleLarge?.copyWith(color: scheme.onSurface),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: scheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(_extraLarge)),
      margin: EdgeInsets.zero,
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: brand.primary,
      foregroundColor: brand.onPrimary,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(_large)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainer,
      indicatorColor: scheme.secondaryContainer,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: const UnderlineInputBorder(
          borderRadius: BorderRadius.vertical(
              top: Radius.circular(_extraSmall))),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
          backgroundColor: brand.primary,
          foregroundColor: brand.onPrimary,
          minimumSize: const Size(64, 48),
          shape: const StadiumBorder()),
    ),
    chipTheme: const ChipThemeData(shape: StadiumBorder()),
    bottomSheetTheme: const BottomSheetThemeData(
      showDragHandle: true,
      shape: RoundedRectangleBorder(
          borderRadius:
              BorderRadius.vertical(top: Radius.circular(_extraLarge))),
    ),
    dialogTheme: DialogThemeData(
        backgroundColor: scheme.surfaceContainerHigh,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(_extraLarge))),
  );
}

/// Money colours (in, out, warning) for the current theme.
extension MoneyTheme on BuildContext {
  MoneyColors get moneyColors =>
      Theme.of(this).extension<MoneyColors>() ?? MoneyColors.light;

  /// Loud Expressive accents (lime, pink, cyan) for headline tiles.
  AccentColors get accents =>
      Theme.of(this).extension<AccentColors>() ?? AccentColors.light;

}
