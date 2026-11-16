// The Budget tab: categories grouped in cards with coloured tiles and
// progress bars, filter chips, a category sheet with its target and
// Move money, and a Ready to Assign bar that stays at the bottom.
part of 'shell.dart';

enum _State { overspent, underfunded, spent, funded, none }

_State _stateOf(EnvelopeRow r) {
  if (r.available < 0) return _State.overspent;
  if (r.need > r.assigned) return _State.underfunded;
  if (r.assigned > 0 && r.available == 0) return _State.spent;
  if (r.assigned > 0 || r.available > 0) return _State.funded;
  return _State.none;
}

/// How full the bar is: spent share of the money, or funding for a target.
double _share(EnvelopeRow r, _State s) {
  if (s == _State.overspent) return 1;
  if (s == _State.underfunded) return r.need <= 0 ? 0 : (r.assigned / r.need).clamp(0, 1).toDouble();
  final spent = -r.activity;
  final total = spent + r.available;
  return total <= 0 ? 0 : (spent / total).clamp(0, 1).toDouble();
}

Color _stateColor(BuildContext context, _State s) {
  final scheme = Theme.of(context).colorScheme;
  switch (s) {
    case _State.overspent:
      return scheme.error;
    case _State.underfunded:
      return Colors.amber.shade700;
    case _State.spent:
      return scheme.outline;
    case _State.funded:
      return Colors.green.shade600;
    case _State.none:
      return scheme.outlineVariant;
  }
}

String _stateText(AppState app, _State s) {
  switch (s) {
    case _State.overspent:
      return app.t('Overspent');
    case _State.underfunded:
      return app.t('Underfunded');
    case _State.spent:
      return app.t('Fully spent');
    case _State.funded:
      return app.t('Funded');
    case _State.none:
      return '';
  }
}

class _Group {
  _Group(this.key, this.label, this.rows);
  final String key;
  final String label;
  final List<EnvelopeRow> rows;
  int get available => rows.fold<int>(0, (s, r) => s + r.available);
}

List<_Group> _groupsOf(EnvelopeMonth env, AppState app) {
  final byParent = <int, List<EnvelopeRow>>{};
  final names = <int, String>{};
  final singles = <EnvelopeRow>[];
  EnvelopeRow? uncategorised;
  for (final r in env.rows) {
    final c = r.category;
    if (c == null) {
      uncategorised = r;
      continue;
    }
    final key = c.parentId ?? c.id;
    byParent.putIfAbsent(key, () => []).add(r);
    if (c.parentId == null) names[c.id] = c.name;
    if (c.parentName != null) names.putIfAbsent(key, () => c.parentName!);
  }
  final out = <_Group>[];
  for (final e in byParent.entries) {
    if (e.value.length == 1 && e.value.first.category?.parentId == null) {
      singles.add(e.value.first);
    } else {
      out.add(_Group('p${e.key}', names[e.key] ?? '', e.value));
    }
  }
  out.sort((a, b) => a.label.toLowerCase().compareTo(b.label.toLowerCase()));
  if (singles.isNotEmpty) out.add(_Group('singles', app.t('Other categories'), singles));
  if (uncategorised != null) {
    out.add(_Group('none', app.t('Uncategorised'), [uncategorised]));
  }
  return out;
}

class BudgetPage extends StatefulWidget {
  const BudgetPage({super.key});
  @override
  State<BudgetPage> createState() => _BudgetPageState();
}

class _BudgetPageState extends State<BudgetPage> {
  DateTime month = monthStart(DateTime.now());
  String filter = 'all';
  final collapsed = <String>{};

  bool _keep(EnvelopeRow r) {
    final s = _stateOf(r);
    switch (filter) {
      case 'overspent':
        return s == _State.overspent;
      case 'underfunded':
        return s == _State.underfunded;
      case 'available':
        return r.available > 0;
      default:
        return true;
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final env = app.repo.envelopeMonth(month);
    final groups = _groupsOf(env, app);
    final counts = {
      'overspent': env.rows.where((r) => _stateOf(r) == _State.overspent).length,
      'underfunded': env.rows.where((r) => _stateOf(r) == _State.underfunded).length,
      'available': env.rows.where((r) => r.available > 0).length,
    };
    final shown = [
      for (final g in groups)
        if (g.rows.any(_keep)) g,
    ];
    return Stack(children: [
      ListView(
        padding: const EdgeInsets.only(bottom: 120),
        children: [
          _Header(app.t('Budget')),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(children: [
              IconButton(
                  onPressed: () => setState(() => month = addMonths(month, -1)),
                  icon: const Icon(Icons.chevron_left)),
              Expanded(
                  child: Text(DateFormat.yMMMM(app.lang).format(month),
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700))),
              IconButton(
                  onPressed: () => setState(() => month = addMonths(month, 1)),
                  icon: const Icon(Icons.chevron_right)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
                child: Row(children: [
                  _MiniStat(app.t('Assigned'), money(context, env.assigned, env.currency)),
                  _MiniStat(app.t('Activity'), money(context, env.activity, env.currency)),
                  _MiniStat(app.t('Available'), money(context, env.available, env.currency)),
                ]),
              ),
            ),
          ),
          SizedBox(
            height: 56,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
              children: [
                for (final (key, label) in [
                  ('all', app.t('All')),
                  ('overspent', app.t('Overspent')),
                  ('underfunded', app.t('Underfunded')),
                  ('available', app.t('Money available')),
                ])
                  Padding(
                    padding: const EdgeInsetsDirectional.only(end: 8),
                    child: FilterChip(
                      selected: filter == key,
                      showCheckmark: false,
                      shape: const StadiumBorder(),
                      label: Text(key == 'all' ? label : '$label  ${counts[key]}'),
                      onSelected: (_) => setState(() => filter = key),
                    ),
                  ),
              ],
            ),
          ),
          if (env.missingFx.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: Text(app.t(
                  'Some amounts are missing an exchange rate ({c}). Update the rates in PFI on your PC.',
                  {'c': env.missingFx.join(', ')})),
            ),
          if (shown.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16),
              child: _EmptyHint(app.t('Nothing here'),
                  app.t('No category matches this filter this month.')),
            ),
          for (final g in shown)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: _GroupCard(
                group: g,
                rows: g.rows.where(_keep).toList(),
                open: !collapsed.contains(g.key),
                onToggle: () => setState(() => collapsed.contains(g.key)
                    ? collapsed.remove(g.key)
                    : collapsed.add(g.key)),
                currency: env.currency,
                onTap: (r) => _openCategory(context, r, env),
              ),
            ),
        ],
      ),
      PositionedDirectional(
        start: 16,
        end: 16,
        bottom: 12,
        child: _ReadyBar(env: env, onFund: () => _fundTargets(context, env)),
      ),
    ]);
  }

  Future<void> _openCategory(BuildContext context, EnvelopeRow r, EnvelopeMonth env) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        builder: (_) => _CategorySheet(row: r, env: env, month: month),
      );

  /// Assigns what each target still needs, as far as Ready to Assign goes.
  Future<void> _fundTargets(BuildContext context, EnvelopeMonth env) async {
    final app = appOf(context, listen: false);
    var left = env.readyToAssign;
    final plan = <(EnvelopeRow, int)>[];
    for (final r in env.rows) {
      final c = r.category;
      if (c == null || r.need <= r.assigned || left <= 0) continue;
      final add = r.need - r.assigned < left ? r.need - r.assigned : left;
      plan.add((r, add));
      left -= add;
    }
    if (plan.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(env.readyToAssign <= 0
              ? app.t('There is no money left to assign.')
              : app.t('Every target is funded this month.'))));
      return;
    }
    final total = plan.fold<int>(0, (s, p) => s + p.$2);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(app.t('Fund targets')),
        content: Text(app.t('This assigns {a} to {n} categories so their targets are met.',
            {'a': money(context, total, env.currency), 'n': plan.length})),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(app.t('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(app.t('Assign'))),
        ],
      ),
    );
    if (ok != true) return;
    for (final (r, add) in plan) {
      app.repo.setAssigned(r.category!.id, month, r.assigned + add);
    }
    app.changed();
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat(this.label, this.value);
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 2),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
          ),
        ]),
      );
}

class _GroupCard extends StatelessWidget {
  const _GroupCard({
    required this.group,
    required this.rows,
    required this.open,
    required this.onToggle,
    required this.currency,
    required this.onTap,
  });
  final _Group group;
  final List<EnvelopeRow> rows;
  final bool open;
  final VoidCallback onToggle;
  final String currency;
  final void Function(EnvelopeRow) onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(children: [
        InkWell(
          onTap: onToggle,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
            child: Row(children: [
              AnimatedRotation(
                turns: open ? 0.25 : 0,
                duration: const Duration(milliseconds: 150),
                child: Icon(Icons.chevron_right, size: 20, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(group.label,
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
              ),
              Text(money(context, group.available, currency),
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: group.available < 0 ? scheme.error : scheme.onSurfaceVariant)),
            ]),
          ),
        ),
        if (open)
          for (final r in rows) _EnvelopeTile(r, currency, () => onTap(r)),
        if (open) const SizedBox(height: 6),
      ]),
    );
  }
}

class _EnvelopeTile extends StatelessWidget {
  const _EnvelopeTile(this.r, this.currency, this.onTap);
  final EnvelopeRow r;
  final String currency;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context, listen: false);
    final scheme = Theme.of(context).colorScheme;
    final c = r.category;
    final s = _stateOf(r);
    final color = _stateColor(context, s);
    final pill = switch (s) {
      _State.overspent => scheme.errorContainer,
      _State.underfunded => Colors.amber.withValues(alpha: 0.3),
      _State.funded => Colors.green.withValues(alpha: 0.18),
      _ => scheme.surfaceContainerHighest,
    };
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
        child: Row(children: [
          CategoryAvatar(icon: c?.icon, name: c?.name, color: c?.color, size: 42, square: true),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(
                  child: Text(c?.name ?? app.t('Uncategorised spending'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
                if (s != _State.none)
                  Text(_stateText(app, s),
                      style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
              ]),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: _share(r, s),
                  minHeight: 5,
                  color: color,
                  backgroundColor: scheme.surfaceContainerHighest,
                ),
              ),
            ]),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(color: pill, borderRadius: BorderRadius.circular(12)),
            child: Text(money(context, r.available, currency),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          ),
        ]),
      ),
    );
  }
}

class _ReadyBar extends StatelessWidget {
  const _ReadyBar({required this.env, required this.onFund});
  final EnvelopeMonth env;
  final VoidCallback onFund;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context, listen: false);
    final scheme = Theme.of(context).colorScheme;
    final bad = env.readyToAssign < 0;
    final bg = bad ? scheme.error : scheme.primary;
    final fg = bad ? scheme.onError : scheme.onPrimary;
    return Material(
      color: bg,
      elevation: 6,
      shadowColor: bg.withValues(alpha: 0.4),
      borderRadius: BorderRadius.circular(22),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 12, 12),
        child: Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(app.t('Ready to assign'),
                  style: TextStyle(color: fg.withValues(alpha: 0.85), fontSize: 12)),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: AlignmentDirectional.centerStart,
                child: Text(money(context, env.readyToAssign, env.currency),
                    style: TextStyle(
                        color: fg, fontSize: 22, fontWeight: FontWeight.w800)),
              ),
            ]),
          ),
          FilledButton.tonalIcon(
            onPressed: onFund,
            style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
            icon: const Icon(Icons.bolt_rounded, size: 20),
            label: Text(app.t('Fund targets')),
          ),
        ]),
      ),
    );
  }
}

class _CategorySheet extends StatelessWidget {
  const _CategorySheet({required this.row, required this.env, required this.month});
  final EnvelopeRow row;
  final EnvelopeMonth env;
  final DateTime month;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context, listen: false);
    final scheme = Theme.of(context).colorScheme;
    final c = row.category;
    final s = _stateOf(row);
    final cur = env.currency;
    Widget stat(String label, int v, {bool strong = false}) => Expanded(
          child: Column(children: [
            Text(label, style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: 2),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(money(context, v, cur),
                  style: TextStyle(
                      fontWeight: strong ? FontWeight.w800 : FontWeight.w600,
                      fontSize: strong ? 17 : 14,
                      color: strong && v < 0 ? scheme.error : null)),
            ),
          ]),
        );
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
            20, 0, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            CategoryAvatar(icon: c?.icon, name: c?.name, color: c?.color, size: 48, square: true),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(c?.label ?? app.t('Uncategorised spending'),
                    style: Theme.of(context).textTheme.titleLarge),
                Text(DateFormat.yMMMM(app.lang).format(month),
                    style: Theme.of(context).textTheme.bodySmall),
              ]),
            ),
          ]),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
              child: Row(children: [
                stat(app.t('Assigned'), row.assigned),
                stat(app.t('Activity'), row.activity),
                stat(app.t('Available'), row.available, strong: true),
              ]),
            ),
          ),
          if (s == _State.overspent || s == _State.underfunded) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: _stateColor(context, s).withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                  s == _State.overspent
                      ? app.t('Overspent by {a}. Move money here from another category to cover it.',
                          {'a': money(context, -row.available, cur)})
                      : app.t('Needs {a} more to meet its target.',
                          {'a': money(context, row.need - row.assigned, cur)}),
                  style: TextStyle(color: _stateColor(context, s), fontWeight: FontWeight.w600)),
            ),
          ],
          if (row.need > 0) ...[
            const SizedBox(height: 16),
            Text(app.t('Target'), style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: (row.assigned / row.need).clamp(0, 1).toDouble(),
                    minHeight: 8,
                    color: row.assigned >= row.need ? Colors.green.shade600 : Colors.amber.shade700,
                    backgroundColor: scheme.surfaceContainerHighest,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text('${money(context, row.assigned, cur)} / ${money(context, row.need, cur)}',
                  style: Theme.of(context).textTheme.bodySmall),
            ]),
          ],
          if (c != null) ...[
            const SizedBox(height: 20),
            Row(children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: () async {
                    final v = await _askAmount(context, app.t('Assign to {c}', {'c': c.name}),
                        row.assigned, cur);
                    if (v == null) return;
                    app.repo.setAssigned(c.id, month, v);
                    app.changed();
                    if (context.mounted) Navigator.pop(context);
                  },
                  icon: const Icon(Icons.edit_outlined),
                  label: Text(app.t('Assign')),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: () async {
                    final done = await _moveMoney(context, env, month, row);
                    if (done && context.mounted) Navigator.pop(context);
                  },
                  icon: const Icon(Icons.swap_horiz_rounded),
                  label: Text(s == _State.overspent ? app.t('Cover') : app.t('Move money')),
                ),
              ),
            ]),
            if (row.need > row.assigned) ...[
              const SizedBox(height: 10),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(minimumSize: const Size(64, 48)),
                onPressed: () {
                  app.repo.setAssigned(c.id, month, row.need);
                  app.changed();
                  Navigator.pop(context);
                },
                icon: const Icon(Icons.bolt_rounded),
                label: Text(app.t('Fund target')),
              ),
            ],
          ],
        ]),
      ),
    );
  }
}

Future<int?> _askAmount(BuildContext context, String title, int initial, String currency) {
  final app = appOf(context, listen: false);
  final ctl = TextEditingController(text: (initial / 100).toStringAsFixed(2));
  return showDialog<int>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: ctl,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
        decoration: InputDecoration(suffixText: currency),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: Text(app.t('Cancel'))),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, parseMinor(ctl.text)),
            child: Text(app.t('Save'))),
      ],
    ),
  );
}

/// Moves assigned money between this category and another one. When the
/// category is overspent the money comes in; otherwise it goes out.
Future<bool> _moveMoney(
    BuildContext context, EnvelopeMonth env, DateTime month, EnvelopeRow row) async {
  final app = appOf(context, listen: false);
  final incoming = row.available < 0;
  final others = env.rows
      .where((r) => r.category != null && r.category!.id != row.category!.id)
      .toList();
  if (others.isEmpty) return false;
  others.sort((a, b) => b.available.compareTo(a.available));
  var other = others.first;
  final ctl = TextEditingController(
      text: ((incoming ? -row.available : (row.available > 0 ? row.available : 0)) / 100)
          .toStringAsFixed(2));
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setLocal) => AlertDialog(
        title: Text(incoming
            ? app.t('Cover {c}', {'c': row.category!.name})
            : app.t('Move money from {c}', {'c': row.category!.name})),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          DropdownButtonFormField<int>(
            initialValue: other.category!.id,
            isExpanded: true,
            decoration: InputDecoration(labelText: incoming ? app.t('From') : app.t('To')),
            items: [
              for (final r in others)
                DropdownMenuItem(
                  value: r.category!.id,
                  child: Text('${r.category!.label}  ·  ${money(ctx, r.available, env.currency)}',
                      overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (v) => setLocal(
                () => other = others.firstWhere((r) => r.category!.id == v)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: ctl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(labelText: app.t('Amount'), suffixText: env.currency),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(app.t('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(app.t('Move'))),
        ],
      ),
    ),
  );
  final amount = parseMinor(ctl.text);
  if (ok != true || amount == null || amount <= 0) return false;
  final from = incoming ? other : row;
  final to = incoming ? row : other;
  app.repo.setAssigned(from.category!.id, month, from.assigned - amount);
  app.repo.setAssigned(to.category!.id, month, to.assigned + amount);
  app.changed();
  return true;
}
