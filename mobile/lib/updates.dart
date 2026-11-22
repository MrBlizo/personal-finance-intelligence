// Once a day the phone asks GitHub whether a newer PFI is out (only the
// version number is fetched; nothing about you or your data is sent).
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';
import 'state.dart';

const releasesPage = 'https://github.com/MrBlizo/personal-finance-intelligence/releases/latest';
const _latestApi = 'https://api.github.com/repos/MrBlizo/personal-finance-intelligence/releases/latest';

/// "1.0.2" -> [1, 0, 2]; anything that is not a number counts as 0.
List<int> parseVersion(String v) => [
      for (final p in v.replaceFirst(RegExp('^v'), '').split('-').first.split('.'))
        int.tryParse(p) ?? 0
    ];

/// True when [latest] is newer than [current].
bool isNewer(String latest, String current) {
  final a = parseVersion(latest), b = parseVersion(current);
  for (var i = 0; i < 3; i++) {
    final x = i < a.length ? a[i] : 0, y = i < b.length ? b[i] : 0;
    if (x != y) return x > y;
  }
  return false;
}

/// The newer version available, or null. Checks at most once a day.
Future<String?> newerVersion(AppState app, {bool force = false}) async {
  if (!app.updateCheck && !force) return null;
  final prefs = app.prefs;
  final last = DateTime.tryParse(prefs.getString('update_checked_at') ?? '');
  var latest = prefs.getString('update_latest');
  if (force || last == null || DateTime.now().difference(last).inHours >= 24) {
    try {
      final res = await http.get(Uri.parse(_latestApi),
          headers: {'Accept': 'application/vnd.github+json'}).timeout(const Duration(seconds: 10));
      if (res.statusCode == 200) {
        latest = (jsonDecode(res.body) as Map<String, dynamic>)['tag_name'] as String?;
        if (latest != null) await prefs.setString('update_latest', latest);
      }
      await prefs.setString('update_checked_at', DateTime.now().toIso8601String());
    } catch (_) {
      // Offline: try again next time.
    }
  }
  return latest != null && isNewer(latest, appVersion)
      ? latest.replaceFirst(RegExp('^v'), '')
      : null;
}
