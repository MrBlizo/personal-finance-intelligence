// The Android home-screen widget and app shortcuts ("pfi/launch" channel,
// see android/app/src/main/kotlin/.../MainActivity.kt).
import 'dart:io' show Platform;

import 'package:flutter/services.dart';
import 'package:intl/intl.dart' show NumberFormat;

import 'state.dart';

const _channel = MethodChannel('pfi/launch');

/// Calls [onAction] with "expense", "income" or "open" when the app is
/// started or brought back from the widget or a shortcut.
void listenForLaunches(void Function(String action) onAction) {
  if (!Platform.isAndroid) return;
  _channel.setMethodCallHandler((call) async {
    final a = call.arguments;
    if (call.method == 'action' && a is String) onAction(a);
  });
  _channel.invokeMethod<String>('takeAction').then((a) {
    if (a != null) onAction(a);
  }).catchError((Object _) {});
}

/// Shows the current cash on hand on the home-screen widget.
Future<void> updateWidget(AppState app) async {
  if (!Platform.isAndroid) return;
  try {
    final minor = app.repo.cash();
    final f = NumberFormat('#,##0.00', app.lang == 'en' ? 'en_US' : app.lang);
    await _channel.invokeMethod<void>('updateWidget', {
      'title': app.t('Cash on hand'),
      'value': '${app.repo.baseCurrency} ${minor < 0 ? '−' : ''}'
          '${f.format(minor.abs() / 100)}',
      'add': app.t('Expense'),
      'income': app.t('Income'),
    });
  } catch (_) {
    // No widget support (tests, other platforms): nothing to update.
  }
}
