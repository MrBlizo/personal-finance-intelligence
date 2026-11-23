// Month by month: what came in, what was spent, paid and saved each month,
// the same view as "Month by month" on the PC, plus the year so far.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/repo.dart';
import 'count_up.dart';
import 'theme.dart';
import 'widgets.dart';

class MonthsPage extends StatefulWidget {
  const MonthsPage({super.key});
  @override
  State<MonthsPage> createState() => _MonthsPageState();
}

class _MonthsPageState extends State<MonthsPage> {
  DateTime month = monthStart(DateTime.now());

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final repo = app.repo;
    final base = repo.baseCurrency;
    final now = monthStart(DateTime.now());
    final first = repo.firstMonth();
    final months = <DateTime>[
      for (var m = now;
          !m.isBefore(first) && now.difference(m).inDays < 24 * 31;
          m = addMonths(m, -1))
        m
    ];
    if (months.isEmpty) months.add(now);
    final summaries = {for (final m in months) m: repo.monthSummary(m)};
    final s = summaries[month] ?? repo.monthSummary(month);
    final prev = summaries[addMonths(month, -1)] ?? repo.monthSummary(addMonths(month, -1));
    final scale = summaries.values
        .fold<int>(1, (a, x) => math.max(a, math.max(x.income, x.spent)));
    final name = DateFormat.yMMMM(app.lang).format(month);
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final acc = context.accents;

    return Scaffold(
      appBar: AppBar(title: Text(app.t('Month by month'))),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 40),
        children: [
          SizedBox(
            height: 92,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              reverse: true,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: months.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final m = months[i];
                final x = summaries[m]!;
                return _MonthPill(
                  label: DateFormat.MMM(app.lang).format(m),
                  year: m.month == 1 || i == months.length - 1 ? '${m.year}' : '',
                  income: x.income / scale,
                  spent: x.spent / scale,
                  selected: m == month,
                  onTap: () => setState(() => month = m),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              if (s.missingFx.isNotEmpty)
                Card(
                  color: scheme.errorContainer,
                  child: ListTile(
                    leading: Icon(Icons.currency_exchange, color: scheme.onErrorContainer),
                    title: Text(app.t('Some amounts have no exchange rate and are left out: {c}.',
                        {'c': s.missingFx.join(', ')})),
                  ),
                ),
              const SizedBox(height: 8),
              _HeroTile(
                label: app.t('Spent in {m}', {'m': name}),
                value: money(context, s.spent, base),
                sub: prev.spent > 0
                    ? app.t(s.spent <= prev.spent ? '{v} less than the month before' : '{v} more than the month before',
                        {'v': money(context, (s.spent - prev.spent).abs(), base)})
                    : null,
              ),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 1.55,
                children: [
                  _Tile(app.t('Earned'), money(context, s.income, base), acc.limeContainer, acc.onLimeContainer,
                      Icons.south_west_rounded),
                  _Tile(app.t('Paid'), money(context, s.paid, base), acc.lavenderContainer,
                      acc.onLavenderContainer, Icons.receipt_long_rounded,
                      sub: app.t('Bills {b} · debts {d}', {
                        'b': money(context, s.bills, base),
                        'd': money(context, s.debtPayments, base)
                      })),
                  _Tile(app.t('Saved'), money(context, s.saved, base), acc.cyanContainer, acc.onCyanContainer,
                      Icons.savings_rounded),
                  _Tile(
                      app.t('Savings rate'),
                      s.savingsRate == null ? '—' : '${(s.savingsRate! * 100).round()} %',
                      acc.pinkContainer,
                      acc.onPinkContainer,
                      Icons.percent_rounded,
                      sub: app.t('Net {v}', {'v': money(context, s.net, base)})),
                ],
              ),
              SectionTitle(app.t('Where it went')),
              if (s.categories.isEmpty)
                Card(child: ListTile(title: Text(app.t('No spending this month.'))))
              else
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: [
                      for (final (i, e) in (s.categories.entries.toList()
                            ..sort((a, b) => b.value.compareTo(a.value)))
                          .take(8)
                          .indexed)
                        _CategoryBar(
                          color: chartColors[i % chartColors.length],
                          name: e.key.isEmpty ? app.t('Uncategorised') : e.key,
                          amount: money(context, e.value, base),
                          share: e.value / s.spent,
                          change: prev.categories[e.key] == null
                              ? null
                              : e.value - prev.categories[e.key]!,
                          currency: base,
                        ),
                    ]),
                  ),
                ),
              SectionTitle(app.t('Spending pace')),
              Card(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    SizedBox(
                      height: 140,
                      child: CustomPaint(
                        size: Size.infinite,
                        painter: _PacePainter(
                          s.daily,
                          prev.daily,
                          upTo: month == now ? DateTime.now().day : s.daily.length,
                          line: chartColors[0],
                          ghost: scheme.outline,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 16, children: [
                      _Legend(chartColors[0], name),
                      _Legend(scheme.outline, app.t('Month before'), dashed: true),
                    ]),
                  ]),
                ),
              ),
              if (s.billsPaid.isNotEmpty) ...[
                SectionTitle(app.t('Paid this month')),
                Card(
                  child: Column(children: [
                    for (final b in s.billsPaid)
                      ListTile(
                        leading: const Icon(Icons.event_available_rounded),
                        title: Text(b.$1),
                        subtitle: Text(DateFormat.MMMd(app.lang).format(b.$3)),
                        trailing: Text(money(context, b.$2, base),
                            style: const TextStyle(fontWeight: FontWeight.w700)),
                      ),
                  ]),
                ),
              ],
              if (s.biggest.isNotEmpty) ...[
                SectionTitle(app.t('Biggest expenses')),
                Card(
                  child: Column(children: [
                    for (final b in s.biggest)
                      ListTile(
                        title: Text(b.$1, maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: Text(DateFormat.MMMd(app.lang).format(b.$3)),
                        trailing: Text(money(context, b.$2, base),
                            style: const TextStyle(fontWeight: FontWeight.w700)),
                      ),
                  ]),
                ),
              ],
              SectionTitle(app.t('{y} so far', {'y': month.year})),
              _YearCard(year: month.year, currency: base),
              const SizedBox(height: 8),
              Text(app.t('Transfers into savings and investment accounts count as saved; transfers into cards and loans count as paid.'),
                  style: text.bodySmall),
            ]),
          ),
        ],
      ),
    );
  }
}

class _MonthPill extends StatelessWidget {
  const _MonthPill({
    required this.label,
    required this.year,
    required this.income,
    required this.spent,
    required this.selected,
    required this.onTap,
  });
  final String label;
  final String year;
  final double income;
  final double spent;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = context.moneyColors;
    Widget bar(double v, Color c) => Container(
          width: 7,
          height: 4 + 30 * v.clamp(0.0, 1.0),
          decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(4)),
        );
    return Material(
      color: selected ? scheme.primaryContainer : scheme.surfaceContainerLow,
      shape: selected
          ? const StadiumBorder()
          : RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOutBack,
          width: 64,
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [bar(income, colors.positive), const SizedBox(width: 3), bar(spent, scheme.error)],
            ),
            const SizedBox(height: 6),
            Text(label,
                style: TextStyle(
                    fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
                    color: selected ? scheme.onPrimaryContainer : null)),
            if (year.isNotEmpty) Text(year, style: Theme.of(context).textTheme.labelSmall),
          ]),
        ),
      ),
    );
  }
}

class _HeroTile extends StatelessWidget {
  const _HeroTile({required this.label, required this.value, this.sub});
  final String label;
  final String value;
  final String? sub;

  @override
  Widget build(BuildContext context) {
    final acc = context.accents;
    final fg = acc.onLavenderContainer;
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        color: acc.lavenderContainer,
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: fg, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: AlignmentDirectional.centerStart,
          child: CountUpText(value,
              style: Theme.of(context).textTheme.displaySmall?.copyWith(color: fg)),
        ),
        if (sub != null) ...[
          const SizedBox(height: 4),
          Text(sub!, style: TextStyle(color: fg.withValues(alpha: 0.85))),
        ],
      ]),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile(this.label, this.value, this.bg, this.fg, this.icon, {this.sub});
  final String label;
  final String value;
  final Color bg;
  final Color fg;
  final IconData icon;
  final String? sub;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 18, color: fg),
          const SizedBox(width: 6),
          Expanded(
              child: Text(label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: fg, fontWeight: FontWeight.w600))),
        ]),
        const Spacer(),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: AlignmentDirectional.centerStart,
          child: CountUpText(value,
              style: TextStyle(color: fg, fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        ),
        if (sub != null)
          Text(sub!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: fg.withValues(alpha: 0.8), fontSize: 11)),
      ]),
    );
  }
}

class _CategoryBar extends StatelessWidget {
  const _CategoryBar({
    required this.name,
    required this.amount,
    required this.share,
    required this.change,
    required this.currency,
    required this.color,
  });
  final String name;
  final String amount;
  final double share;
  final int? change;
  final String currency;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final app = appOf(context, listen: false);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis)),
          if (change != null && change != 0)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: 8),
              child: Text(
                '${change! > 0 ? '▲' : '▼'} ${money(context, change!.abs(), currency)}',
                style: TextStyle(
                    fontSize: 11,
                    color: change! > 0 ? scheme.error : context.moneyColors.positive),
                semanticsLabel: app.t(change! > 0 ? '{v} more than the month before' : '{v} less than the month before',
                    {'v': money(context, change!.abs(), currency)}),
              ),
            ),
          Text(amount, style: const TextStyle(fontWeight: FontWeight.w700)),
        ]),
        const SizedBox(height: 6),
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: share.clamp(0.0, 1.0)),
          duration: const Duration(milliseconds: 600),
          curve: Curves.easeOutBack,
          builder: (_, v, __) => ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: v.clamp(0.0, 1.0),
              minHeight: 10,
              color: color,
              backgroundColor: scheme.surfaceContainerHighest,
            ),
          ),
        ),
      ]),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend(this.color, this.label, {this.dashed = false});
  final Color color;
  final String label;
  final bool dashed;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 18,
            height: 3,
            color: dashed ? color.withValues(alpha: 0.5) : color),
        const SizedBox(width: 6),
        Text(label, style: Theme.of(context).textTheme.labelSmall),
      ]);
}

/// Cumulative spending through the month against the month before.
class _PacePainter extends CustomPainter {
  _PacePainter(this.daily, this.before,
      {required this.upTo, required this.line, required this.ghost});
  final List<int> daily;
  final List<int> before;
  final int upTo;
  final Color line;
  final Color ghost;

  List<double> _cumulative(List<int> v, int n) {
    final out = <double>[];
    var sum = 0.0;
    for (var i = 0; i < n && i < v.length; i++) {
      sum += v[i];
      out.add(sum);
    }
    return out;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final now = _cumulative(daily, upTo);
    final then = _cumulative(before, before.length);
    final top = [...now, ...then, 1.0].reduce(math.max);
    final days = math.max(daily.length, before.length) - 1;
    Offset at(int i, double v) => Offset(
        days == 0 ? 0 : size.width * i / days, size.height - size.height * v / top);
    Path path(List<double> v) {
      final p = Path();
      for (var i = 0; i < v.length; i++) {
        final o = at(i, v[i]);
        if (i == 0) {
          p.moveTo(o.dx, o.dy);
        } else {
          p.lineTo(o.dx, o.dy);
        }
      }
      return p;
    }

    final grid = Paint()
      ..color = ghost.withValues(alpha: 0.2)
      ..strokeWidth = 1;
    for (var g = 1; g <= 3; g++) {
      final y = size.height * g / 4;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    if (then.length > 1) {
      final dash = Paint()
        ..color = ghost.withValues(alpha: 0.6)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke;
      for (final metric in path(then).computeMetrics()) {
        for (var d = 0.0; d < metric.length; d += 10) {
          canvas.drawPath(metric.extractPath(d, d + 5), dash);
        }
      }
    }
    if (now.length > 1) {
      final p = path(now);
      final fill = Path.from(p)
        ..lineTo(at(now.length - 1, 0).dx, size.height)
        ..lineTo(0, size.height)
        ..close();
      canvas.drawPath(
          fill,
          Paint()
            ..shader = LinearGradient(
                    colors: [line.withValues(alpha: 0.35), line.withValues(alpha: 0)],
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter)
                .createShader(Offset.zero & size));
      canvas.drawPath(
          p,
          Paint()
            ..color = line
            ..strokeWidth = 3
            ..strokeCap = StrokeCap.round
            ..style = PaintingStyle.stroke);
      canvas.drawCircle(at(now.length - 1, now.last), 5, Paint()..color = line);
    }
  }

  @override
  bool shouldRepaint(_PacePainter old) =>
      old.daily != daily || old.before != before || old.line != line;
}

/// The year so far: income, spending, saved and the best and worst month.
class _YearCard extends StatelessWidget {
  const _YearCard({required this.year, required this.currency});
  final int year;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final now = DateTime.now();
    final last = year == now.year ? now.month : 12;
    final months = [for (var m = 1; m <= last; m++) app.repo.monthSummary(DateTime(year, m))];
    final income = months.fold<int>(0, (a, m) => a + m.income);
    final spent = months.fold<int>(0, (a, m) => a + m.spent);
    final saved = months.fold<int>(0, (a, m) => a + m.saved);
    final withSpend = months.where((m) => m.spent > 0).toList();
    withSpend.sort((a, b) => a.spent.compareTo(b.spent));
    String name(MonthSummary m) => DateFormat.MMMM(app.lang).format(m.month);
    Widget row(String label, String value, {Color? color}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            Expanded(child: Text(label)),
            Text(value, style: TextStyle(fontWeight: FontWeight.w700, color: color)),
          ]),
        );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          row(app.t('Earned'), money(context, income, currency), color: context.moneyColors.positive),
          row(app.t('Spent'), money(context, spent, currency)),
          row(app.t('Net'), money(context, income - spent, currency, sign: true)),
          row(app.t('Moved to savings'), money(context, saved, currency)),
          if (income > 0)
            row(app.t('Savings rate'), '${((income - spent) / income * 100).round()} %'),
          if (withSpend.length > 1) ...[
            const Divider(height: 20),
            row(app.t('Lowest spending'), '${name(withSpend.first)} · ${money(context, withSpend.first.spent, currency)}'),
            row(app.t('Highest spending'), '${name(withSpend.last)} · ${money(context, withSpend.last.spent, currency)}'),
          ],
        ]),
      ),
    );
  }
}
