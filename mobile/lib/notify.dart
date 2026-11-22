// Phone notifications: a reminder the day before each bill is due, and an
// alert when a budget category is overspent. Everything is computed on the
// phone from its own data; nothing is sent anywhere.
import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:intl/intl.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'state.dart';

class Notifier {
  Notifier._();
  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;

  // Notification ids: bills 1000–1999, overspent categories 2000+.
  static const _billBase = 1000;
  static const _overBase = 2000;

  static const _bills = AndroidNotificationDetails(
    'bills', 'Bill reminders',
    channelDescription: 'The day before a bill or recurring payment is due',
    importance: Importance.defaultImportance,
  );
  static const _budget = AndroidNotificationDetails(
    'budget', 'Over budget',
    channelDescription: 'When a budget category is overspent',
    importance: Importance.high,
  );

  static Future<bool> _init() async {
    if (_ready) return true;
    if (!Platform.isAndroid) return false;
    tzdata.initializeTimeZones();
    await _plugin.initialize(const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher')));
    _ready = true;
    return true;
  }

  /// Asks Android 13+ for permission to show notifications.
  static Future<bool> requestPermission() async {
    if (!await _init()) return false;
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    return await android?.requestNotificationsPermission() ?? false;
  }

  /// Reschedules bill reminders and checks for overspent categories.
  static Future<void> refresh(AppState app) async {
    try {
      if (!await _init()) return;
      await _scheduleBills(app);
      await _checkBudget(app);
    } catch (_) {
      // Notifications are a convenience: never break the app for them.
    }
  }

  static String _money(AppState app, int minor, String currency) {
    final f = NumberFormat('#,##0.00', app.lang == 'en' ? 'en_US' : app.lang);
    return '$currency ${f.format(minor.abs() / 100)}';
  }

  static Future<void> _scheduleBills(AppState app) async {
    for (var i = 0; i < 64; i++) {
      await _plugin.cancel(_billBase + i);
    }
    if (!app.billReminders) return;
    final currency = {for (final a in app.repo.accounts(includeArchived: true)) a.id: a.currency};
    final now = DateTime.now();
    var n = 0;
    for (final (bill, due) in app.repo.upcoming(days: 30)) {
      if (n >= 64) break;
      var at = DateTime(due.year, due.month, due.day - 1, 9);
      var title = app.t('{b} is due tomorrow', {'b': bill.name});
      if (!at.isAfter(now)) {
        at = DateTime(due.year, due.month, due.day, 9);
        title = app.t('{b} is due today', {'b': bill.name});
        if (!at.isAfter(now)) continue;
      }
      final body = _money(app, bill.amount, currency[bill.accountId] ?? app.repo.baseCurrency);
      await _plugin.zonedSchedule(
        _billBase + n,
        title,
        body,
        tz.TZDateTime.from(at, tz.UTC),
        const NotificationDetails(android: _bills),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
      n++;
    }
  }

  static Future<void> _checkBudget(AppState app) async {
    if (!app.budgetAlerts) return;
    final month = DateTime.now();
    final key = DateFormat('yyyy-MM').format(month);
    final told = (app.prefs.getStringList('overspent_told') ?? [])
        .where((k) => k.startsWith('$key:'))
        .toSet();
    final env = app.repo.envelopeMonth(month);
    for (final r in env.rows) {
      final c = r.category;
      // Only categories with money assigned: without a budget there is
      // nothing to overspend.
      if (c == null || r.assigned <= 0 || r.available >= 0) continue;
      final tag = '$key:${c.id}';
      if (told.contains(tag)) continue;
      told.add(tag);
      await _plugin.show(
        _overBase + c.id % 1000,
        app.t('{c} is over budget', {'c': c.name}),
        app.t('Over by {v} this month. Move money from another category to cover it.',
            {'v': _money(app, r.available, env.currency)}),
        const NotificationDetails(android: _budget),
      );
    }
    await app.prefs.setStringList('overspent_told', told.toList());
  }
}
