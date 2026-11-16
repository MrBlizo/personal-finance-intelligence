import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/l10n/strings.dart';

void main() {
  test('every text shown is translated into French and Arabic', () {
    final keys = <String>{};
    final pattern = RegExp(r"""\bt\(\s*(?:[^()']*\?\s*)?'((?:[^'\\]|\\.)*)'""");
    final ternary = RegExp(r"""[?:]\s*'((?:[^'\\]|\\.)*)'""");
    for (final f in Directory('lib').listSync(recursive: true)) {
      if (f is! File || !f.path.endsWith('.dart') || f.path.contains('l10n')) continue;
      final src = f.readAsStringSync();
      for (final m in pattern.allMatches(src)) {
        keys.add(m[1]!.replaceAll(r"\'", "'"));
      }
      for (final call in RegExp(r"app\.t\(([^;]*?)\)").allMatches(src)) {
        for (final m in ternary.allMatches(call[1]!)) {
          keys.add(m[1]!.replaceAll(r"\'", "'"));
        }
      }
    }
    final fr = frenchKeys.toSet(), ar = arabicKeys.toSet();
    expect(keys.where((k) => !fr.contains(k)), isEmpty, reason: 'missing in French');
    expect(keys.where((k) => !ar.contains(k)), isEmpty, reason: 'missing in Arabic');
  });
}
