// App-wide state: the database, preferences and sync.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/db.dart';
import 'data/repo.dart';
import 'l10n/strings.dart';
import 'launch.dart';
import 'notify.dart';
import 'sync/cloud.dart';
import 'sync/crypto.dart';
import 'sync/engine.dart';
import 'ui/m3_tokens.dart' show pfiSeed;

const accentColors = <String, Color>{
  'Indigo': pfiSeed, // shared with the PC and the website
  'Violet': Color(0xFF8E5CF7),
  'Blue': Color(0xFF2F6FE4),
  'Teal': Color(0xFF00897B),
  'Green': Color(0xFF2E7D32),
  'Olive': Color(0xFF827717),
  'Orange': Color(0xFFE65100),
  'Red': Color(0xFFC62828),
  'Pink': Color(0xFFAD1457),
  'Brown': Color(0xFF6D4C41),
  'Slate': Color(0xFF546E7A),
};

class AppState extends ChangeNotifier with WidgetsBindingObserver {
  AppState(this.app, this.prefs)
      : repo = Repo(app),
        engine = SyncEngine(app.db, app.meta) {
    WidgetsBinding.instance.addObserver(this);
  }

  final AppDatabase app;
  final Repo repo;
  final SyncEngine engine;
  final SharedPreferences prefs;
  static const _secure = FlutterSecureStorage();

  int revision = 0;
  bool syncing = false;
  String? syncMessage;
  Timer? _debounce;

  // --- preferences ---------------------------------------------------
  String get lang => prefs.getString('lang') ?? _systemLang();
  String _systemLang() {
    final code = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    return const ['fr', 'ar'].contains(code) ? code : 'en';
  }

  Color get accent => accentColors[accentName] ?? pfiSeed;
  String get accentName {
    // 1.0.1 keeps the choice under 'accent2'. Before, the default was
    // called 'Violet' (0.x: 'Purple'); both become the shared Indigo.
    final name = prefs.getString('accent2') ??
        switch (prefs.getString('accent')) {
          null || 'Violet' || 'Purple' => 'Indigo',
          final old => old,
        };
    return accentColors.containsKey(name) ? name : 'Indigo';
  }
  ThemeMode get themeMode => switch (prefs.getString('theme')) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
  bool get onboarded => prefs.getBool('onboarded') ?? !app.isEmpty;
  bool get billReminders => prefs.getBool('bill_reminders') ?? true;
  bool get budgetAlerts => prefs.getBool('budget_alerts') ?? true;
  bool get updateCheck => prefs.getBool('update_check') ?? true;

  Future<void> setFlag(String key, bool value) async {
    await prefs.setBool(key, value);
    notifyListeners();
    Notifier.refresh(this);
  }

  Future<void> setPref(String key, String value) async {
    if (key == 'lang') Future.microtask(() => updateWidget(this));
    await prefs.setString(key, value);
    notifyListeners();
  }

  Future<void> finishOnboarding({String? currency}) async {
    if (currency != null) app.seed(currency);
    await prefs.setBool('onboarded', true);
    changed(sync: false);
  }

  String t(String text, [Map<String, Object?> args = const {}]) =>
      translate(lang, text, args);

  /// Call after any edit: screens reload, and a sync follows shortly.
  void changed({bool sync = true}) {
    revision++;
    notifyListeners();
    updateWidget(this);
    Notifier.refresh(this);
    if (sync && syncEnabled) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(seconds: 8), () => syncNow());
    }
  }

  // --- sync ----------------------------------------------------------
  CloudProvider? get provider {
    final name = prefs.getString('sync_provider');
    return CloudProvider.values.where((p) => p.name == name).firstOrNull;
  }

  bool get syncEnabled =>
      provider != null && engine.getState('enabled') == '1';

  Map<String, dynamic> get lastSync =>
      jsonDecode(engine.getState('last_result') ?? '{}') as Map<String, dynamic>;

  List<Map<String, dynamic>> get otherDevices {
    final me = engine.getState('device_id');
    return [
      for (final r in app.db.select(
          "SELECT key, value FROM sync_state WHERE key LIKE 'device:%'"))
        if ((r['key'] as String).substring(7) != me)
          jsonDecode(r['value'] as String) as Map<String, dynamic>
    ];
  }

  Future<void> setUpSync(CloudProvider p, String passphrase, String name) async {
    final auth = CloudAuth(p);
    final store = cloudStore(p, auth);
    final key = await engine.setup(store, passphrase, deviceName: name);
    await _secure.write(key: 'sync_key', value: base64.encode(key));
    await prefs.setString('sync_provider', p.name);
    await prefs.setBool('onboarded', true);
    notifyListeners();
    await syncNow(raise: true);
  }

  Future<void> stopSync() async {
    engine.setState('enabled', '0');
    await _secure.delete(key: 'sync_key');
    final p = provider;
    if (p != null) await CloudAuth(p).signOut();
    await prefs.remove('sync_provider');
    notifyListeners();
  }

  Future<SyncResult?> syncNow({bool raise = false}) async {
    final p = provider;
    if (p == null || syncing) return null;
    final key = await _secure.read(key: 'sync_key');
    if (key == null) return null;
    syncing = true;
    syncMessage = null;
    notifyListeners();
    try {
      final res = await engine.run(cloudStore(p, CloudAuth(p)), base64.decode(key));
      syncMessage = res.problems.isEmpty ? null : res.problems.first;
      if (res.received > 0) {
        revision++;
        updateWidget(this);
        Notifier.refresh(this);
      }
      return res;
    } on SyncException catch (e) {
      syncMessage = e.message;
      if (raise) rethrow;
      return null;
    } catch (e) {
      syncMessage = '$e';
      if (raise) rethrow;
      return null;
    } finally {
      syncing = false;
      notifyListeners();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && syncEnabled) syncNow();
    if (state == AppLifecycleState.paused && _debounce?.isActive == true) {
      _debounce!.cancel();
      syncNow();
    }
  }
}
