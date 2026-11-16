import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/l10n/strings.dart';

String _unescape(String s) => s.replaceAll(r"\'", "'");

void main() {
  test('every text shown is translated into French and Arabic', () {
    final keys = <String>{};
    final direct = RegExp(r"\bt\(\s*'((?:[^'\\]|\\.)*)'");
    final call = RegExp(r'app\.t\(([^;]*?)\)');
    final ternary = RegExp(r"[?:]\s*'((?:[^'\\]|\\.)*)'");
    for (final f in Directory('lib').listSync(recursive: true)) {
      if (f is! File || !f.path.endsWith('.dart') || f.path.contains('l10n')) {
        continue;
      }
      final src = f.readAsStringSync();
      for (final m in direct.allMatches(src)) {
        keys.add(_unescape(m[1]!));
      }
      for (final c in call.allMatches(src)) {
        for (final m in ternary.allMatches(c[1]!)) {
          keys.add(_unescape(m[1]!));
        }
      }
    }
    expect(keys, isNotEmpty);
    final fr = frenchKeys.toSet(), ar = arabicKeys.toSet();
    expect(keys.where((k) => !fr.contains(k)), isEmpty, reason: 'missing in French');
    expect(keys.where((k) => !ar.contains(k)), isEmpty, reason: 'missing in Arabic');
  });
}
