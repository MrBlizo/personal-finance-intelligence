// Material 3, shared with the Windows app and the website: the scheme comes
// from the chosen seed with the fidelity variant (PFI blue by default), the
// shape scale matches the PC screens, and money colours come from
// m3_tokens.dart, which scripts/m3/gen-tokens.mjs writes.
import 'package:flutter/material.dart';

import 'm3_tokens.dart';

export 'm3_tokens.dart' show MoneyColors, pfiSeed;

// Shape scale (same values as --md-sys-shape-corner-* on the PC).
const _extraSmall = 4.0;
const _medium = 12.0;
const _large = 16.0;
const _extraLarge = 28.0;

ThemeData buildTheme(Color seed, Brightness brightness) {
  final scheme = ColorScheme.fromSeed(
    seedColor: seed,
    brightness: brightness,
    dynamicSchemeVariant: DynamicSchemeVariant.fidelity,
  );
  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final text = base.textTheme;
  return base.copyWith(
    scaffoldBackgroundColor: scheme.surface,
    extensions: [
      brightness == Brightness.dark ? MoneyColors.dark : MoneyColors.light,
    ],
    // Default M3 type scale; headlines a step heavier for hierarchy.
    textTheme: text.copyWith(
      headlineLarge: text.headlineLarge?.copyWith(fontWeight: FontWeight.w500),
      headlineMedium:
          text.headlineMedium?.copyWith(fontWeight: FontWeight.w500),
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
          borderRadius: BorderRadius.circular(_medium)),
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
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
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
}
