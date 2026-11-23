// The main screens: Home, Budget, Spending, Accounts and Plan.
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/repo.dart';
import '../state.dart';
import '../updates.dart';
import 'count_up.dart';
import 'edit_transaction.dart';
import 'import_csv.dart';
import 'months.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

part 'budget.dart';
part 'plan.dart';

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
      HomePage(onTab: (i) => setState(() => tab = i)),
      const BudgetPage(),
      const TransactionsPage(),
      const AccountsPage(),
      const PlanPage(),
    ];
    return Scaffold(
      body: SafeArea(child: pages[tab]),
      floatingActionButton: tab == 0 || tab == 2
          ? FloatingActionButton.large(
              onPressed: () => openEditor(context),
              tooltip: app.t('Add transaction'),
              child: const Icon(Icons.add_rounded, size: 36),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [
          NavigationDestination(
              icon: const Icon(Icons.home_outlined),
              selectedIcon: const Icon(Icons.home_rounded),
              label: app.t('Home')),
          NavigationDestination(
              icon: const Icon(Icons.account_balance_wallet_outlined),
              selectedIcon: const Icon(Icons.account_balance_wallet_rounded),
              label: app.t('Budget')),
          NavigationDestination(
              icon: const Icon(Icons.receipt_long_outlined),
              selectedIcon: const Icon(Icons.receipt_long_rounded),
              label: app.t('Spending')),
          NavigationDestination(
              icon: const Icon(Icons.account_balance_outlined),
              selectedIcon: const Icon(Icons.account_balance_rounded),
              label: app.t('Accounts')),
          NavigationDestination(
              icon: const Icon(Icons.flag_outlined),
              selectedIcon: const Icon(Icons.flag_rounded),
              label: app.t('Plan')),
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
  const HomePage({super.key, required this.onTab});

  /// Switches the bottom tab (1 Budget, 2 Spending, 3 Accounts, 4 Plan).
  final void Function(int) onTab;

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
              _Hero(
                label: app.t('Cash on hand'),
                value: money(context, repo.cash(), base),
                actions: [
                  _QuickAction(Icons.add_rounded, app.t('Add'), () => openEditor(context)),
                  _QuickAction(Icons.account_balance_wallet_outlined, app.t('Budget'), () => onTab(1)),
                  _QuickAction(Icons.receipt_long_outlined, app.t('Spending'), () => onTab(2)),
                  _QuickAction(
                      app.syncEnabled ? Icons.sync_rounded : Icons.cloud_outlined,
                      app.t('Sync'),
                      app.syncEnabled
                          ? () => app.syncNow()
                          : () => Navigator.of(context).push(
                              MaterialPageRoute(builder: (_) => const SyncSetupPage()))),
                ],
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _Pill(app.t('Income'), money(context, income, base),
                    Icons.south_west_rounded, context.moneyColors.positive,
                    onTap: () => _openMonths(context))),
                const SizedBox(width: 12),
                Expanded(child: _Pill(app.t('Expenses'), money(context, -spent, base),
                    Icons.north_east_rounded, scheme.error,
                    onTap: () => _openMonths(context))),
              ]),
              const SizedBox(height: 12),
              Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                  leading: Icon(Icons.calendar_view_month_rounded, color: scheme.primary),
                  title: Text(app.t('Month by month')),
                  subtitle: Text(app.t('What you spent, paid and saved each month')),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _openMonths(context),
                ),
              ),
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
              if (repo.upcoming(days: 7) case final soon when soon.isNotEmpty) ...[
                const SizedBox(height: 12),
                Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                    leading: const Icon(Icons.event_repeat_outlined, color: Colors.deepOrange),
                    title: Text(app.t('{n} due this week', {'n': soon.length})),
                    subtitle: Text(soon.take(3).map((e) => e.$1.name).join(', ')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => const BillsPage())),
                  ),
                ),
              ],
              FutureBuilder<String?>(
                future: newerVersion(app),
                builder: (context, snap) => snap.data == null
                    ? const SizedBox.shrink()
                    : Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Card(
                          color: context.accents.limeContainer,
                          child: ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                            leading: Icon(Icons.system_update_rounded, color: context.accents.onLimeContainer),
                            title: Text(app.t('Personal Finance {v} is available.', {'v': snap.data}),
                                style: TextStyle(
                                    fontWeight: FontWeight.w700, color: context.accents.onLimeContainer)),
                            subtitle: Text(app.t('Tap to download the new APK from GitHub.'),
                                style: TextStyle(color: context.accents.onLimeContainer)),
                            onTap: () => launchUrl(Uri.parse(releasesPage),
                                mode: LaunchMode.externalApplication),
                          ),
                        ),
                      ),
              ),
              if (!app.syncEnabled) ...[
                const SizedBox(height: 12),
                Card(
                  color: scheme.tertiaryContainer,
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                    leading: Icon(Icons.sync_rounded, color: scheme.onTertiaryContainer),
                    title: Text(app.t('Connect to Personal Finance on my PC'),
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(app.t('Use the same OneDrive account and passphrase as on your PC.')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const SyncSetupPage())),
                  ),
                ),
              ],
              SectionTitle(app.t('Recent'),
                  action: TextButton(onPressed: () => onTab(2), child: Text(app.t('See all')))),
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

/// The big gradient card at the top of Home with round quick actions.
class _Hero extends StatelessWidget {
  const _Hero({required this.label, required this.value, required this.actions});
  final String label;
  final String value;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final acc = context.accents;
    final fg = acc.onLavenderContainer;
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: acc.lavenderContainer,
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            style: TextStyle(
                color: fg.withValues(alpha: 0.75),
                fontSize: 12,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.6)),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: AlignmentDirectional.centerStart,
          child: CountUpText(value,
              style: TextStyle(
                  color: fg, fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        ),
        const SizedBox(height: 20),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: actions),
      ]),
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction(this.icon, this.label, this.onTap);
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = context.accents.onLavenderContainer;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: Column(children: [
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
                color: fg.withValues(alpha: 0.1), shape: BoxShape.circle),
            child: Icon(icon, color: fg),
          ),
          const SizedBox(height: 6),
          Text(label,
              style: TextStyle(color: fg, fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
      ),
    );
  }
}

void _openMonths(BuildContext context) => Navigator.of(context)
    .push(MaterialPageRoute(builder: (_) => const MonthsPage()));

class _Pill extends StatelessWidget {
  const _Pill(this.label, this.value, this.icon, this.color, {this.onTap});
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
        onTap: onTap,
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
                    child: CountUpText(value,
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16))),
              ]),
            ),
          ]),
        ),
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
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              IconButton(
                  tooltip: app.t('Import a bank statement'),
                  onPressed: () => Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => const ImportCsvPage())),
                  icon: const Icon(Icons.upload_file_outlined)),
              IconButton(
                  tooltip: app.t('Add account'),
                  onPressed: () => addAccountDialog(context),
                  icon: const Icon(Icons.add_circle_outline)),
            ])),
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
  'USD', 'EUR', 'GBP', 'CHF', 'MAD', 'CAD', 'AUD', 'JPY', 'CNY', 'SEK',
  'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'AED', 'SAR', 'EGP', 'TND',
  'DZD', 'XOF', 'INR', 'BRL', 'MXN', 'ZAR',
];
