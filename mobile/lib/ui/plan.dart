// The Plan tab: savings goals, bills, investments and debts.
part of 'shell.dart';

class PlanPage extends StatelessWidget {
  const PlanPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final repo = app.repo;
    final base = repo.baseCurrency;
    final goals = repo.goals();
    final due = repo.upcoming(days: 30);
    final holdings = repo.holdings();
    final debts = repo.debts();
    final invested = holdings.fold<int>(0, (s, h) => s + (h.value ?? h.cost));
    final owed = debts.fold<int>(0, (s, d) => s + d.owed);
    final dueSum = due.fold<int>(0, (s, e) => s + (e.$1.amount < 0 ? e.$1.amount : 0));
    void open(Widget page) =>
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    return ListView(
      padding: const EdgeInsets.only(bottom: 40),
      children: [
        _Header(app.t('Plan')),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            _PlanCard(
              icon: Icons.flag_outlined,
              color: Colors.teal,
              title: app.t('Goals'),
              value: goals.isEmpty
                  ? app.t('Save for something')
                  : app.t('{n} goals · {p}% saved', {
                      'n': goals.length,
                      'p': (goals.fold<double>(0, (s, g) => s + g.progress) /
                              goals.length * 100)
                          .round()
                    }),
              onTap: () => open(const GoalsPage()),
            ),
            _PlanCard(
              icon: Icons.event_repeat_outlined,
              color: Colors.deepOrange,
              title: app.t('Bills'),
              value: due.isEmpty
                  ? app.t('Nothing due in the next 30 days')
                  : app.t('{n} due in 30 days · {a}',
                      {'n': due.length, 'a': money(context, dueSum, base)}),
              onTap: () => open(const BillsPage()),
            ),
            _PlanCard(
              icon: Icons.show_chart_rounded,
              color: Colors.indigo,
              title: app.t('Investments'),
              value: holdings.isEmpty
                  ? app.t('Add holdings on your PC')
                  : app.t('{n} holdings · {a}',
                      {'n': holdings.length, 'a': money(context, invested, base)}),
              onTap: () => open(const InvestmentsPage()),
            ),
            _PlanCard(
              icon: Icons.trending_down_rounded,
              color: context.moneyColors.negative,
              title: app.t('Debts'),
              value: debts.isEmpty
                  ? app.t('No debts')
                  : app.t('{n} debts · {a} owed',
                      {'n': debts.length, 'a': money(context, owed, base)}),
              onTap: () => open(const DebtsPage()),
            ),
          ]),
        ),
      ],
    );
  }
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.icon, required this.color, required this.title,
      required this.value, required this.onTap});
  final IconData icon;
  final Color color;
  final String title;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
          leading: Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
                color: color.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(14)),
            child: Icon(icon, color: color),
          ),
          title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          subtitle: Text(value),
          trailing: const Icon(Icons.chevron_right),
          onTap: onTap,
        ),
      );
}

/// A full-screen list with a back arrow and an optional add button.
class _SubPage extends StatelessWidget {
  const _SubPage({required this.title, required this.children, this.onAdd});
  final String title;
  final List<Widget> children;
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      floatingActionButton: onAdd == null
          ? null
          : FloatingActionButton.extended(
              onPressed: onAdd,
              icon: const Icon(Icons.add_rounded),
              label: Text(app.t('Add'))),
      body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 120), children: children),
    );
  }
}

String _date(BuildContext context, DateTime d) =>
    DateFormat.yMMMd(appOf(context, listen: false).lang).format(d);

// --- Goals ------------------------------------------------------------
class GoalsPage extends StatelessWidget {
  const GoalsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final goals = app.repo.goals();
    final scheme = Theme.of(context).colorScheme;
    final now = DateTime.now();
    return _SubPage(
      title: app.t('Goals'),
      onAdd: () => _editGoal(context),
      children: [
        if (goals.isEmpty)
          _EmptyHint(app.t('No goals yet'),
              app.t('A goal sets money aside for something: a trip, a car, an emergency fund.')),
        for (final g in goals)
          Card(
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => _editGoal(context, g),
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                        child: Text(g.name,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700))),
                    Text('${(g.progress * 100).round()}%',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, color: scheme.primary)),
                  ]),
                  const SizedBox(height: 10),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: TweenAnimationBuilder<double>(
                      tween: Tween(begin: 0, end: g.progress),
                      duration: const Duration(milliseconds: 700),
                      curve: Curves.easeOutCubic,
                      builder: (_, v, __) => LinearProgressIndicator(
                          value: v, minHeight: 10,
                          color: g.progress >= 1 ? Colors.green.shade600 : null),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(app.t('{s} of {t}', {
                    's': money(context, g.saved, g.currency),
                    't': money(context, g.target, g.currency)
                  })),
                  if (g.targetDate != null && g.remaining > 0)
                    Text(
                        app.t('{m} a month until {d}', {
                          'm': money(context, g.monthlyNeeded(now) ?? 0, g.currency),
                          'd': _date(context, g.targetDate!)
                        }),
                        style: Theme.of(context).textTheme.bodySmall),
                  if (g.accountId != null)
                    Text(app.t('Follows the balance of the linked account'),
                        style: Theme.of(context).textTheme.bodySmall),
                ]),
              ),
            ),
          ),
      ],
    );
  }
}

Future<void> _editGoal(BuildContext context, [Goal? g]) async {
  final app = appOf(context, listen: false);
  final name = TextEditingController(text: g?.name ?? '');
  final target = TextEditingController(
      text: g == null ? '' : (g.target / 100).toStringAsFixed(2));
  final saved = TextEditingController(
      text: g == null ? '' : (g.manualSaved / 100).toStringAsFixed(2));
  var date = g?.targetDate;
  int? account = g?.accountId;
  final accounts = app.repo.accounts();
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, set) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(g == null ? app.t('New goal') : app.t('Edit goal'),
              style: Theme.of(ctx).textTheme.titleLarge),
          const SizedBox(height: 12),
          TextField(controller: name, decoration: InputDecoration(labelText: app.t('Name'))),
          TextField(
              controller: target,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                  labelText: app.t('Target amount'), suffixText: app.repo.baseCurrency)),
          DropdownButtonFormField<int?>(
            value: account,
            decoration: InputDecoration(labelText: app.t('Saved in')),
            items: [
              DropdownMenuItem(value: null, child: Text(app.t('Not linked (enter the amount)'))),
              for (final a in accounts) DropdownMenuItem(value: a.id, child: Text(a.name)),
            ],
            onChanged: (v) => set(() => account = v),
          ),
          if (account == null)
            TextField(
                controller: saved,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(labelText: app.t('Saved so far'))),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            icon: const Icon(Icons.event_outlined),
            label: Text(date == null ? app.t('No target date') : _date(ctx, date!)),
            onPressed: () async {
              final d = await showDatePicker(
                  context: ctx,
                  initialDate: date ?? DateTime.now().add(const Duration(days: 365)),
                  firstDate: DateTime.now().subtract(const Duration(days: 3650)),
                  lastDate: DateTime.now().add(const Duration(days: 365 * 50)));
              if (d != null) set(() => date = d);
            },
          ),
          const SizedBox(height: 16),
          Row(children: [
            if (g != null)
              TextButton(
                onPressed: () async {
                  if (!await confirmDelete(ctx)) return;
                  app.repo.deleteGoal(g.id);
                  app.changed();
                  if (ctx.mounted) Navigator.pop(ctx);
                },
                child: Text(app.t('Delete')),
              ),
            const Spacer(),
            FilledButton(
              onPressed: () {
                final t = parseMinor(target.text);
                if (name.text.trim().isEmpty || t == null || t <= 0) return;
                app.repo.saveGoal(
                    id: g?.id, name: name.text, target: t,
                    currency: g?.currency ?? app.repo.baseCurrency,
                    targetDate: date, accountId: account,
                    saved: account == null ? (parseMinor(saved.text) ?? 0) : 0,
                    notes: g?.notes);
                app.changed();
                Navigator.pop(ctx);
              },
              child: Text(app.t('Save')),
            ),
          ]),
        ]),
      ),
    ),
  );
}

// --- Bills ------------------------------------------------------------
const _frequencies = ['weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'];
const _freqLabels = {
  'weekly': 'Weekly', 'biweekly': 'Every two weeks', 'monthly': 'Monthly',
  'quarterly': 'Quarterly', 'yearly': 'Yearly'
};

class BillsPage extends StatelessWidget {
  const BillsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final repo = app.repo;
    final due = repo.upcoming(days: 30);
    final all = repo.bills();
    final accounts = {for (final a in repo.accounts(includeArchived: true)) a.id: a};
    final today = DateTime.now();
    final day = DateTime(today.year, today.month, today.day);
    return _SubPage(
      title: app.t('Bills'),
      onAdd: () => _editBill(context),
      children: [
        SectionTitle(app.t('Due in the next 30 days')),
        if (due.isEmpty)
          _EmptyHint(app.t('Nothing due'), app.t('Add rent, subscriptions and salary to see them coming.'))
        else
          Card(
            child: Column(children: [
              for (final (b, d) in due)
                ListTile(
                  leading: CircleAvatar(
                    backgroundColor: (d.isBefore(day.add(const Duration(days: 3)))
                            ? Colors.deepOrange
                            : Theme.of(context).colorScheme.primary)
                        .withValues(alpha: 0.14),
                    child: Text('${d.day}',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                  title: Text(b.name),
                  subtitle: Text(dayLabel(context, d)),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    AmountText(b.amount, accounts[b.accountId]?.currency ?? repo.baseCurrency),
                    IconButton(
                      tooltip: app.t('Mark as paid'),
                      icon: const Icon(Icons.check_circle_outline),
                      onPressed: () {
                        repo.payBill(b, d);
                        app.changed();
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(app.t('{n} recorded', {'n': b.name}))));
                      },
                    ),
                  ]),
                ),
            ]),
          ),
        SectionTitle(app.t('All bills and income')),
        if (all.isNotEmpty)
          Card(
            child: Column(children: [
              for (final b in all)
                ListTile(
                  title: Text(b.name),
                  subtitle: Text([
                    app.t(_freqLabels[b.frequency] ?? b.frequency),
                    if (b.nextDue(day) case final n?) app.t('next {d}', {'d': _date(context, n)}),
                    if (!b.active) app.t('paused'),
                  ].join(' · ')),
                  trailing: AmountText(
                      b.amount, accounts[b.accountId]?.currency ?? repo.baseCurrency),
                  onTap: () => _editBill(context, b),
                ),
            ]),
          ),
      ],
    );
  }
}

Future<void> _editBill(BuildContext context, [Bill? b]) async {
  final app = appOf(context, listen: false);
  final repo = app.repo;
  final accounts = repo.accounts();
  if (accounts.isEmpty) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(app.t('Add an account first.'))));
    return;
  }
  final name = TextEditingController(text: b?.name ?? '');
  final amount = TextEditingController(
      text: b == null ? '' : (b.amount.abs() / 100).toStringAsFixed(2));
  var income = (b?.amount ?? -1) > 0;
  var account = b?.accountId ?? accounts.first.id;
  if (!accounts.any((a) => a.id == account)) account = accounts.first.id;
  int? category = b?.categoryId;
  var freq = b?.frequency ?? 'monthly';
  var start = b?.start ?? DateTime.now();
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => StatefulBuilder(builder: (ctx, set) {
      final cats = repo.categories(kind: income ? 'income' : 'expense');
      if (category != null && !cats.any((c) => c.id == category)) category = null;
      return Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(b == null ? app.t('New bill') : app.t('Edit bill'),
                style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 12),
            SegmentedButton<bool>(
              segments: [
                ButtonSegment(value: false, label: Text(app.t('Bill'))),
                ButtonSegment(value: true, label: Text(app.t('Income'))),
              ],
              selected: {income},
              onSelectionChanged: (v) => set(() => income = v.first),
            ),
            TextField(controller: name, decoration: InputDecoration(labelText: app.t('Name'))),
            TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(labelText: app.t('Amount'))),
            DropdownButtonFormField<String>(
              value: freq,
              decoration: InputDecoration(labelText: app.t('Repeats')),
              items: [
                for (final f in _frequencies)
                  DropdownMenuItem(value: f, child: Text(app.t(_freqLabels[f]!)))
              ],
              onChanged: (v) => set(() => freq = v ?? freq),
            ),
            DropdownButtonFormField<int>(
              value: account,
              decoration: InputDecoration(labelText: app.t('Account')),
              items: [for (final a in accounts) DropdownMenuItem(value: a.id, child: Text(a.name))],
              onChanged: (v) => set(() => account = v ?? account),
            ),
            DropdownButtonFormField<int?>(
              value: category,
              isExpanded: true,
              decoration: InputDecoration(labelText: app.t('Category')),
              items: [
                DropdownMenuItem(value: null, child: Text(app.t('None'))),
                for (final c in cats) DropdownMenuItem(value: c.id, child: Text(c.label)),
              ],
              onChanged: (v) => set(() => category = v),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.event_outlined),
              label: Text(app.t('First due {d}', {'d': _date(ctx, start)})),
              onPressed: () async {
                final d = await showDatePicker(
                    context: ctx, initialDate: start,
                    firstDate: DateTime(2000), lastDate: DateTime(2100));
                if (d != null) set(() => start = d);
              },
            ),
            const SizedBox(height: 16),
            Row(children: [
              if (b != null)
                TextButton(
                  onPressed: () async {
                    if (!await confirmDelete(ctx)) return;
                    repo.deleteBill(b.id);
                    app.changed();
                    if (ctx.mounted) Navigator.pop(ctx);
                  },
                  child: Text(app.t('Delete')),
                ),
              const Spacer(),
              FilledButton(
                onPressed: () {
                  final v = parseMinor(amount.text);
                  if (name.text.trim().isEmpty || v == null || v == 0) return;
                  repo.saveBill(
                      id: b?.id, name: name.text, accountId: account,
                      categoryId: category, amount: income ? v.abs() : -v.abs(),
                      frequency: freq, start: start);
                  app.changed();
                  Navigator.pop(ctx);
                },
                child: Text(app.t('Save')),
              ),
            ]),
          ]),
        ),
      );
    }),
  );
}

// --- Investments ------------------------------------------------------
class InvestmentsPage extends StatelessWidget {
  const InvestmentsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final repo = app.repo;
    final holdings = repo.holdings().where((h) => h.quantity > 1e-9).toList();
    final fx = Fx(repo.db);
    final today = isoDate(DateTime.now());
    final base = repo.baseCurrency;
    var total = 0.0, cost = 0.0;
    for (final h in holdings) {
      final r = fx.rate(h.currency, base, today) ?? 0;
      total += (h.value ?? h.cost) * r;
      cost += h.cost * r;
    }
    final gain = (total - cost).round();
    final scheme = Theme.of(context).colorScheme;
    return _SubPage(
      title: app.t('Investments'),
      children: [
        _Hero(
          label: app.t('Portfolio value'),
          value: money(context, total.round(), base),
          actions: [
            Text(
                app.t('{g} since bought ({p}%)', {
                  'g': money(context, gain, base, sign: true),
                  'p': cost == 0 ? '0' : (gain / cost * 100).toStringAsFixed(1)
                }),
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 12),
        if (holdings.isEmpty)
          _EmptyHint(app.t('No holdings'),
              app.t('Add stocks, funds and crypto in PFI on your PC; they appear here after a sync.'))
        else
          Card(
            child: Column(children: [
              for (final h in holdings)
                ListTile(
                  leading: CircleAvatar(
                    backgroundColor: scheme.primaryContainer,
                    child: Text(h.symbol.isEmpty ? '?' : h.symbol.characters.first,
                        style: TextStyle(color: scheme.onPrimaryContainer)),
                  ),
                  title: Text(h.name),
                  subtitle: Text([
                    '${NumberFormat('#,##0.####', app.lang == 'en' ? 'en_US' : app.lang).format(h.quantity)} ${h.symbol}',
                    if (h.priceDate != null) _date(context, h.priceDate!),
                  ].join(' · ')),
                  trailing: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(money(context, h.value ?? h.cost, h.currency),
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      if (h.gain != null)
                        Text(money(context, h.gain!, h.currency, sign: true),
                            style: TextStyle(
                                fontSize: 12,
                                color: h.gain! < 0
                                    ? scheme.error
                                    : context.moneyColors.positive)),
                    ],
                  ),
                ),
            ]),
          ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: Text(app.t('Prices and trades are updated in PFI on your PC.'),
              style: Theme.of(context).textTheme.bodySmall),
        ),
      ],
    );
  }
}

// --- Debts ------------------------------------------------------------
class DebtsPage extends StatelessWidget {
  const DebtsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final debts = app.repo.debts()..sort((a, b) => b.apr.compareTo(a.apr));
    final now = DateTime.now();
    return _SubPage(
      title: app.t('Debts'),
      children: [
        if (debts.isEmpty)
          _EmptyHint(app.t('No debts'), app.t('Loans and credit cards with a balance appear here.'))
        else ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
            child: Text(app.t('Highest interest first (avalanche): extra money goes to the top one.'),
                style: Theme.of(context).textTheme.bodySmall),
          ),
          for (final d in debts)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                        child: Text(d.account.name,
                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16))),
                    Text(money(context, d.owed, d.account.currency),
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ]),
                  const SizedBox(height: 6),
                  Text(app.t('{r}% a year · minimum {m}', {
                    'r': d.apr.toStringAsFixed(2),
                    'm': money(context, d.minPayment, d.account.currency)
                  })),
                  if (d.minPayment > 0)
                    Text(
                        switch (d.monthsToPayOff(d.minPayment)) {
                          final m? => app.t('Paid off around {d} at the minimum', {
                              'd': DateFormat.yMMMM(app.lang)
                                  .format(DateTime(now.year, now.month + m))
                            }),
                          null => app.t('The minimum does not cover the interest'),
                        },
                        style: Theme.of(context).textTheme.bodySmall),
                ]),
              ),
            ),
        ],
      ],
    );
  }
}
