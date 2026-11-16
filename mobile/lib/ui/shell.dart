// The main screens: Home, Transactions, Budget and Accounts.
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/repo.dart';
import 'edit_transaction.dart';
import 'settings.dart';
import 'widgets.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int tab = 0;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final pages = [
      HomePage(onSeeAll: () => setState(() => tab = 1)),
      const TransactionsPage(),
      const BudgetPage(),
      const AccountsPage(),
    ];
    return Scaffold(
      body: SafeArea(child: pages[tab]),
      floatingActionButton: tab == 3
          ? null
          : FloatingActionButton.large(
              onPressed: () => openEditor(context),
              tooltip: app.t('Add transaction'),
              child: const Icon(Icons.add_rounded, size: 36),
            ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [
          NavigationDestination(
              icon: const Icon(Icons.home_outlined),
              selectedIcon: const Icon(Icons.home_rounded),
              label: app.t('Home')),
          NavigationDestination(
              icon: const Icon(Icons.receipt_long_outlined),
              selectedIcon: const Icon(Icons.receipt_long_rounded),
              label: app.t('Transactions')),
          NavigationDestination(
              icon: const Icon(Icons.pie_chart_outline_rounded),
              selectedIcon: const Icon(Icons.pie_chart_rounded),
              label: app.t('Budget')),
          NavigationDestination(
              icon: const Icon(Icons.account_balance_wallet_outlined),
              selectedIcon: const Icon(Icons.account_balance_wallet_rounded),
              label: app.t('Accounts')),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header(this.title, {this.trailing});
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 12, 4),
        child: Row(children: [
          Expanded(
              child: Text(title,
                  style: Theme.of(context).textTheme.headlineLarge)),
          if (trailing != null) trailing!,
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SettingsPage())),
          ),
        ]),
      );
}

class _SyncIndicator extends StatelessWidget {
  const _SyncIndicator();
  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    if (!app.syncEnabled) return const SizedBox.shrink();
    if (app.syncing) {
      return const Padding(
          padding: EdgeInsets.all(12),
          child: SizedBox(
              width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)));
    }
    return IconButton(
      tooltip: app.syncMessage ?? app.t('Sync now'),
      icon: Icon(app.syncMessage == null
          ? Icons.cloud_done_outlined
          : Icons.cloud_off_outlined),
      onPressed: () => app.syncNow(),
    );
  }
}

// --- Home ------------------------------------------------------------
class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.onSeeAll});
  final VoidCallback onSeeAll;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final repo = app.repo;
    final scheme = Theme.of(context).colorScheme;
    final base = repo.baseCurrency;
    final now = DateTime.now();
    final (income, spent) = repo.monthTotals(now);
    final env = repo.envelopeMonth(now);
    final recent = repo.transactions(limit: 6);
    final hour = now.hour;
    final hello = app.t(hour < 12
        ? 'Good morning'
        : hour < 18
            ? 'Good afternoon'
            : 'Good evening');
    return RefreshIndicator(
      onRefresh: () async => app.syncNow(),
      child: ListView(
        padding: const EdgeInsets.only(bottom: 120),
        children: [
          _Header(hello, trailing: const _SyncIndicator()),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Card(
                color: scheme.primaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(app.t('Cash on hand'),
                        style: TextStyle(color: scheme.onPrimaryContainer)),
                    const SizedBox(height: 6),
                    Text(money(context, repo.cash(), base),
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(color: scheme.onPrimaryContainer)),
                  ]),
                ),
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _Pill(app.t('Income'), money(context, income, base),
                    Icons.south_west_rounded, Colors.green.shade600)),
                const SizedBox(width: 12),
                Expanded(child: _Pill(app.t('Expenses'), money(context, -spent, base),
                    Icons.north_east_rounded, scheme.error)),
              ]),
              const SizedBox(height: 12),
              Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                  leading: Icon(Icons.savings_outlined, color: scheme.primary),
                  title: Text(app.t('Ready to assign')),
                  subtitle: Text(DateFormat.yMMMM(app.lang).format(now)),
                  trailing: Text(money(context, env.readyToAssign, env.currency),
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: env.readyToAssign < 0 ? scheme.error : null)),
                ),
              ),
              if (!app.syncEnabled) ...[
                const SizedBox(height: 12),
                Card(
                  color: scheme.tertiaryContainer,
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                    leading: Icon(Icons.sync_rounded, color: scheme.onTertiaryContainer),
                    title: Text(app.t('Connect to PFI on my PC'),
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(app.t('Use the same OneDrive account and passphrase as on your PC.')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const SyncSetupPage())),
                  ),
                ),
              ],
              SectionTitle(app.t('Recent'),
                  action: TextButton(onPressed: onSeeAll, child: Text(app.t('See all')))),
              if (recent.isEmpty)
                _EmptyHint(app.t('No transactions yet'), app.t('Tap + to add your first one.'))
              else
                Card(child: Column(children: [for (final t in recent) TxnTile(t)])),
            ]),
          ),
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill(this.label, this.value, this.icon, this.color);
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            CircleAvatar(
                radius: 18,
                backgroundColor: color.withValues(alpha: 0.15),
                child: Icon(icon, color: color, size: 20)),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(label, style: Theme.of(context).textTheme.labelMedium),
                FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: AlignmentDirectional.centerStart,
                    child: Text(value,
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16))),
              ]),
            ),
          ]),
        ),
      );
}

class _EmptyHint extends StatelessWidget {
  const _EmptyHint(this.title, this.text);
  final String title;
  final String text;
  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(children: [
            Icon(Icons.receipt_long_outlined,
                size: 40, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 8),
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            Text(text, textAlign: TextAlign.center),
          ]),
        ),
      );
}

class TxnTile extends StatelessWidget {
  const TxnTile(this.t, {super.key});
  final Txn t;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context, listen: false);
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: CategoryAvatar(
          icon: t.categoryIcon, name: t.categoryName, color: t.categoryColor),
      title: Text(t.title, maxLines: 1, overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(
          [t.categoryName ?? (t.kind == 'transfer' ? '⇄' : app.t('Uncategorised')),
            t.accountName].join(' · '),
          maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: AmountText(t.amount, t.currency),
      onTap: () => openEditor(context, txn: t),
    );
  }
}

// --- Transactions ----------------------------------------------------
class TransactionsPage extends StatefulWidget {
  const TransactionsPage({super.key});
  @override
  State<TransactionsPage> createState() => _TransactionsPageState();
}

class _TransactionsPageState extends State<TransactionsPage> {
  String search = '';

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final items = app.repo.transactions(search: search, limit: 500);
    final groups = <DateTime, List<Txn>>{};
    for (final t in items) {
      groups.putIfAbsent(t.date, () => []).add(t);
    }
    return Column(children: [
      _Header(app.t('Transactions')),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: SearchBar(
          hintText: app.t('Search'),
          leading: const Icon(Icons.search),
          elevation: const WidgetStatePropertyAll(0),
          onChanged: (v) => setState(() => search = v),
        ),
      ),
      Expanded(
        child: items.isEmpty
            ? Padding(
                padding: const EdgeInsets.all(16),
                child: _EmptyHint(app.t('No transactions yet'),
                    app.t('Tap + to add your first one.')))
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 120),
                children: [
                  for (final e in groups.entries) ...[
                    SectionTitle(dayLabel(context, e.key)),
                    Card(
                      child: Column(children: [
                        for (final t in e.value)
                          Dismissible(
                            key: ValueKey(t.id),
                            direction: DismissDirection.endToStart,
                            background: Container(
                              alignment: AlignmentDirectional.centerEnd,
                              padding: const EdgeInsets.symmetric(horizontal: 24),
                              color: Theme.of(context).colorScheme.errorContainer,
                              child: const Icon(Icons.delete_outline),
                            ),
                            confirmDismiss: (_) => confirmDelete(context),
                            onDismissed: (_) {
                              app.repo.deleteTransaction(t.id);
                              app.changed();
                            },
                            child: TxnTile(t),
                          ),
                      ]),
                    ),
                  ],
                ],
              ),
      ),
    ]);
  }
}

Future<bool> confirmDelete(BuildContext context) async {
  final app = appOf(context, listen: false);
  return await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text(app.t('Delete this transaction?')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: Text(app.t('Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(app.t('Delete'))),
          ],
        ),
      ) ??
      false;
}

// --- Budget (envelopes) ----------------------------------------------
class BudgetPage extends StatefulWidget {
  const BudgetPage({super.key});
  @override
  State<BudgetPage> createState() => _BudgetPageState();
}

class _BudgetPageState extends State<BudgetPage> {
  DateTime month = monthStart(DateTime.now());

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final scheme = Theme.of(context).colorScheme;
    final env = app.repo.envelopeMonth(month);
    return ListView(
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
                    style: Theme.of(context).textTheme.titleMedium)),
            IconButton(
                onPressed: () => setState(() => month = addMonths(month, 1)),
                icon: const Icon(Icons.chevron_right)),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Card(
              color: env.readyToAssign < 0 ? scheme.errorContainer : scheme.primaryContainer,
              child: Padding(
                padding: const EdgeInsets.all(22),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(app.t('Ready to assign')),
                  Text(money(context, env.readyToAssign, env.currency),
                      style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 8),
                  Text('${app.t('Assigned')} ${money(context, env.assigned, env.currency)}  ·  '
                      '${app.t('Activity')} ${money(context, env.activity, env.currency)}'),
                ]),
              ),
            ),
            if (env.missingFx.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(app.t(
                    'Some amounts are missing an exchange rate ({c}). Update the rates in PFI on your PC.',
                    {'c': env.missingFx.join(', ')})),
              ),
            const SizedBox(height: 12),
            Card(
              child: Column(children: [
                for (final r in env.rows) _EnvelopeTile(r, month, env.currency),
              ]),
            ),
          ]),
        ),
      ],
    );
  }
}

class _EnvelopeTile extends StatelessWidget {
  const _EnvelopeTile(this.r, this.month, this.currency);
  final EnvelopeRow r;
  final DateTime month;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final app = appOf(context, listen: false);
    final scheme = Theme.of(context).colorScheme;
    final c = r.category;
    final over = r.available < 0;
    final short = r.need > r.assigned;
    final pillColor = over
        ? scheme.errorContainer
        : short
            ? Colors.amber.withValues(alpha: 0.35)
            : Colors.green.withValues(alpha: 0.2);
    return ListTile(
      contentPadding: EdgeInsetsDirectional.fromSTEB(c?.parentId == null ? 16 : 32, 2, 16, 2),
      leading: CategoryAvatar(icon: c?.icon, name: c?.name, color: c?.color, size: 38),
      title: Text(c?.name ?? app.t('Uncategorised'),
          style: TextStyle(fontWeight: c?.parentId == null ? FontWeight.w700 : FontWeight.w500)),
      subtitle: Text(r.need > 0
          ? app.t('Needs {a} this month', {'a': money(context, r.need, currency)})
          : '${app.t('Assigned')} ${money(context, r.assigned, currency)}'),
      trailing: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(color: pillColor, borderRadius: BorderRadius.circular(12)),
        child: Text(money(context, r.available, currency),
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
      onTap: c == null ? null : () => _assign(context, c.id, c.name),
    );
  }

  Future<void> _assign(BuildContext context, int id, String name) async {
    final app = appOf(context, listen: false);
    final ctl = TextEditingController(text: (r.assigned / 100).toStringAsFixed(2));
    final value = await showDialog<int>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(app.t('Assign to {c}', {'c': name})),
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
    if (value == null) return;
    app.repo.setAssigned(id, month, value);
    app.changed();
  }
}

// --- Accounts --------------------------------------------------------
class AccountsPage extends StatelessWidget {
  const AccountsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final accounts = app.repo.accounts();
    final totals = <String, int>{};
    for (final a in accounts) {
      totals[a.currency] = (totals[a.currency] ?? 0) + a.balance;
    }
    return ListView(
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        _Header(app.t('Accounts'),
            trailing: IconButton(
                tooltip: app.t('Add account'),
                onPressed: () => addAccountDialog(context),
                icon: const Icon(Icons.add_circle_outline))),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (accounts.isEmpty)
              _EmptyHint(app.t('No accounts yet'), app.t('Add account'))
            else ...[
              Card(
                color: Theme.of(context).colorScheme.secondaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(app.t('Total')),
                    for (final e in totals.entries)
                      Text(money(context, e.value, e.key),
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800)),
                  ]),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: Column(children: [
                  for (final a in accounts)
                    ListTile(
                      leading: CircleAvatar(
                        backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                        child: Icon(_accountIcon(a.type)),
                      ),
                      title: Text(a.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Text(app.t(_typeLabel(a.type))),
                      trailing: AmountText(a.balance, a.currency),
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => _AccountTransactions(a))),
                    ),
                ]),
              ),
            ],
          ]),
        ),
      ],
    );
  }
}

class _AccountTransactions extends StatelessWidget {
  const _AccountTransactions(this.account);
  final Account account;
  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final items = app.repo.transactions(accountId: account.id, limit: 500);
    return Scaffold(
      appBar: AppBar(title: Text(account.name)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [Card(child: Column(children: [for (final t in items) TxnTile(t)]))],
      ),
    );
  }
}

IconData _accountIcon(String type) => switch (type) {
      'savings' => Icons.savings_outlined,
      'cash' => Icons.payments_outlined,
      'credit_card' => Icons.credit_card,
      'investment' => Icons.trending_up,
      'loan' => Icons.request_quote_outlined,
      _ => Icons.account_balance_outlined,
    };

String _typeLabel(String type) => switch (type) {
      'savings' => 'Savings',
      'cash' => 'Cash',
      'credit_card' => 'Credit card',
      'investment' => 'Investment',
      'loan' => 'Loan',
      _ => 'Checking',
    };

Future<void> addAccountDialog(BuildContext context) async {
  final app = appOf(context, listen: false);
  final name = TextEditingController();
  final opening = TextEditingController(text: '0.00');
  var type = 'checking';
  var currency = app.repo.baseCurrency;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: Text(app.t('Add account')),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: name, decoration: InputDecoration(labelText: app.t('Name'))),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: type,
              decoration: InputDecoration(labelText: app.t('Type')),
              items: [
                for (final t in ['checking', 'savings', 'cash', 'credit_card'])
                  DropdownMenuItem(value: t, child: Text(app.t(_typeLabel(t)))),
              ],
              onChanged: (v) => setState(() => type = v ?? type),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: currency,
              decoration: InputDecoration(labelText: app.t('Currency')),
              items: [
                for (final c in currencies)
                  DropdownMenuItem(value: c, child: Text(c)),
              ],
              onChanged: (v) => setState(() => currency = v ?? currency),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: opening,
              keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
              decoration: InputDecoration(labelText: app.t('Opening balance')),
            ),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(app.t('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(app.t('Save'))),
        ],
      ),
    ),
  );
  if (ok != true || name.text.trim().isEmpty) return;
  try {
    app.repo.addAccount(name.text, type, currency, parseMinor(opening.text) ?? 0,
        DateTime.now());
    app.changed();
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }
}

const currencies = [
  'CHF', 'EUR', 'USD', 'GBP', 'MAD', 'CAD', 'AUD', 'JPY', 'CNY', 'SEK',
  'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'AED', 'SAR', 'EGP', 'TND',
  'DZD', 'XOF', 'INR', 'BRL', 'MXN', 'ZAR',
];
