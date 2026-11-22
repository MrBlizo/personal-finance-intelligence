// Material 3 Expressive, shared with the Windows app and the website: the
// light scheme comes from the chosen seed with the vibrant variant (PFI violet
// by default); with PFI violet, dark mode is the hand-tuned Neon scheme. Loud
// accents (lime, pink, cyan) and money colours come from m3_tokens.dart,
// which scripts/m3/gen-tokens.mjs writes.
import 'package:flutter/material.dart';

import 'm3_tokens.dart';

export 'm3_tokens.dart' show AccentColors, MoneyColors, pfiSeed;

// Shape scale (same values as --md-sys-shape-corner-* on the PC).
const _extraSmall = 4.0;
const _large = 20.0;
const _extraLarge = 28.0;

/// True when dark mode uses the Neon scheme (PFI violet accent).
bool isNeon(Color seed, Brightness brightness) =>
    brightness == Brightness.dark && seed.toARGB32() == pfiSeed.toARGB32();

ThemeData buildTheme(Color seed, Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = isNeon(seed, brightness)
      ? neonDarkScheme
      : ColorScheme.fromSeed(
          seedColor: seed,
          brightness: brightness,
          dynamicSchemeVariant: DynamicSchemeVariant.vibrant,
        );
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
      backgroundColor: scheme.primaryContainer,
      foregroundColor: scheme.onPrimaryContainer,
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
          minimumSize: const Size(64, 48), shape: const StadiumBorder()),
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

  /// True in the Neon dark look (glows instead of flat tones).
  bool get neon {
    final s = Theme.of(this).colorScheme;
    return s.brightness == Brightness.dark &&
        s.primary.toARGB32() == neonDarkScheme.primary.toARGB32();
  }
}
