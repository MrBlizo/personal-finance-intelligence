// Animated figures: the number inside a formatted amount ("1 234,50 €",
// "-$12.00", "42 %") counts up from zero when it first appears or changes,
// like the CountUp component in the Windows app.
import 'package:flutter/material.dart';

class CountUpText extends StatelessWidget {
  const CountUpText(this.value, {super.key, this.style, this.ms = 900});

  /// The formatted value shown when the animation ends.
  final String value;

  /// The text style.
  final TextStyle? style;

  /// The duration in milliseconds.
  final int ms;

  static final _number = RegExp(r'\d[\d\s  .,٫٬]*');

  @override
  Widget build(BuildContext context) {
    final match = _number.firstMatch(value);
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (match == null || reduce) return Text(value, style: style);
    final raw = match.group(0)!.trimRight();
    final parsed = _parse(raw);
    if (parsed == null) return Text(value, style: style);
    final (target, decimals, group, point) = parsed;
    final head = value.substring(0, match.start);
    final tail = value.substring(match.start + raw.length);
    return Semantics(
      label: value,
      excludeSemantics: true,
      child: TweenAnimationBuilder<double>(
        key: ValueKey(value),
        tween: Tween(begin: 0, end: target),
        duration: Duration(milliseconds: ms),
        curve: Curves.easeOutCubic,
        builder: (_, v, __) => Text(
            v == target ? value : '$head${_format(v, decimals, group, point)}$tail',
            style: style),
      ),
    );
  }

  /// Splits a formatted number into its value, decimals and separators.
  static (double, int, String, String)? _parse(String raw) {
    final seps = RegExp(r'[^\d]').allMatches(raw).map((m) => m.group(0)!).toList();
    var point = '';
    var decimals = 0;
    if (seps.isNotEmpty) {
      final last = seps.last;
      final after = raw.length - raw.lastIndexOf(last) - 1;
      // A lone separator followed by 3 digits is a thousands mark.
      final isPoint = (last == ',' || last == '.' || last == '٫') &&
          (seps.where((s) => s == last).length == 1) &&
          (after != 3 || seps.length > 1);
      if (isPoint) {
        point = last;
        decimals = after;
      }
    }
    final group = seps.firstWhere((s) => s != point, orElse: () => '');
    final digits = point.isEmpty
        ? raw.replaceAll(RegExp(r'[^\d]'), '')
        : '${raw.substring(0, raw.lastIndexOf(point)).replaceAll(RegExp(r'[^\d]'), '')}'
            '.${raw.substring(raw.lastIndexOf(point) + 1)}';
    final n = double.tryParse(digits);
    return n == null ? null : (n, decimals, group, point);
  }

  static String _format(double v, int decimals, String group, String point) {
    final fixed = v.toStringAsFixed(decimals);
    final parts = fixed.split('.');
    final whole = parts[0];
    final buf = StringBuffer();
    for (var i = 0; i < whole.length; i++) {
      if (i > 0 && (whole.length - i) % 3 == 0 && group.isNotEmpty) buf.write(group);
      buf.write(whole[i]);
    }
    if (decimals > 0) buf.write('$point${parts[1]}');
    return buf.toString();
  }
}
