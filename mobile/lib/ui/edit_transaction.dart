// Add or edit a transaction: big amount, number pad and category grid.
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/repo.dart';
import 'shell.dart' show confirmDelete;
import 'widgets.dart';

Future<void> openEditor(BuildContext context, {Txn? txn}) async {
  final app = appOf(context, listen: false);
  if (app.repo.accounts().isEmpty) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(app.t('Add an account first.'))));
    return;
  }
  await Navigator.of(context).push(MaterialPageRoute(
      fullscreenDialog: true, builder: (_) => EditTransactionPage(txn: txn)));
}

class EditTransactionPage extends StatefulWidget {
  const EditTransactionPage({super.key, this.txn});
  final Txn? txn;
  @override
  State<EditTransactionPage> createState() => _EditTransactionPageState();
}

class _EditTransactionPageState extends State<EditTransactionPage> {
  late String kind;
  late String amount;
  late int accountId;
  int? categoryId;
  late DateTime date;
  final payee = TextEditingController();
  final note = TextEditingController();
  bool categoryTouched = false;

  @override
  void initState() {
    super.initState();
    final t = widget.txn;
    final app = appOf(context, listen: false);
    kind = t == null ? 'expense' : (t.amount > 0 ? 'income' : 'expense');
    amount = t == null ? '' : (t.amount.abs() / 100).toStringAsFixed(2);
    accountId = t?.accountId ??
        int.tryParse(app.prefs.getString('last_account') ?? '') ??
        app.repo.accounts().first.id;
    if (!app.repo.accounts().any((a) => a.id == accountId)) {
      accountId = app.repo.accounts().first.id;
    }
    categoryId = t?.categoryId;
    date = t?.date ?? DateTime.now();
    payee.text = t?.merchant ?? (t?.description ?? '');
    note.text = t?.notes ?? '';
  }

  void _key(String k) {
    setState(() {
      if (k == '⌫') {
        if (amount.isNotEmpty) amount = amount.substring(0, amount.length - 1);
      } else if (k == '.') {
        if (!amount.contains('.')) amount = amount.isEmpty ? '0.' : '$amount.';
      } else {
        final dot = amount.indexOf('.');
        if (dot >= 0 && amount.length - dot > 2) return;
        if (amount.replaceAll('.', '').length >= 10) return;
        amount = amount == '0' ? k : '$amount$k';
      }
    });
  }

  Future<void> _save() async {
    final app = appOf(context, listen: false);
    final minor = parseMinor(amount);
    if (minor == null || minor == 0) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(app.t('Enter an amount.'))));
      return;
    }
    app.repo.saveTransaction(
      id: widget.txn?.id,
      accountId: accountId,
      date: date,
      amount: kind == 'expense' ? -minor.abs() : minor.abs(),
      kind: widget.txn?.kind == 'transfer' ? 'transfer' : kind,
      payee: payee.text,
      categoryId: categoryId,
      notes: note.text,
    );
    await app.prefs.setString('last_account', '$accountId');
    app.changed();
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final scheme = Theme.of(context).colorScheme;
    final accounts = app.repo.accounts();
    final account = accounts.firstWhere((a) => a.id == accountId);
    final cats = app.repo.categories(kind: kind);
    return Scaffold(
      appBar: AppBar(
        title: Text(app.t(widget.txn == null ? 'Add transaction' : 'Edit transaction')),
        actions: [
          if (widget.txn != null)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () async {
                if (await confirmDelete(context)) {
                  app.repo.deleteTransaction(widget.txn!.id);
                  app.changed();
                  if (context.mounted) Navigator.of(context).pop();
                }
              },
            ),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: ListView(padding: const EdgeInsets.symmetric(horizontal: 16), children: [
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'expense', label: Text(app.t('Expense')),
                    icon: const Icon(Icons.north_east_rounded)),
                ButtonSegment(value: 'income', label: Text(app.t('Income')),
                    icon: const Icon(Icons.south_west_rounded)),
              ],
              selected: {kind},
              onSelectionChanged: (s) => setState(() {
                kind = s.first;
                if (!categoryTouched) categoryId = null;
              }),
            ),
            const SizedBox(height: 16),
            Center(
              child: FittedBox(
                child: Text(
                  '${kind == 'expense' ? '−' : '+'} ${account.currency} '
                  '${amount.isEmpty ? '0' : amount}',
                  style: Theme.of(context).textTheme.displayMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                      color: kind == 'expense' ? scheme.onSurface : Colors.green.shade600),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Autocomplete<(String, int?)>(
              initialValue: TextEditingValue(text: payee.text),
              optionsBuilder: (v) =>
                  v.text.isEmpty ? const Iterable<(String, int?)>.empty() : app.repo.payees(v.text),
              displayStringForOption: (o) => o.$1,
              onSelected: (o) => setState(() {
                payee.text = o.$1;
                if (!categoryTouched && o.$2 != null) categoryId = o.$2;
              }),
              fieldViewBuilder: (ctx, ctl, focus, submit) => TextField(
                controller: ctl,
                focusNode: focus,
                onChanged: (v) => payee.text = v,
                decoration: InputDecoration(
                    labelText: app.t('Payee'), prefixIcon: const Icon(Icons.storefront_outlined)),
              ),
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: DropdownButtonFormField<int>(
                  value: accountId,
                  isExpanded: true,
                  decoration: InputDecoration(labelText: app.t('Account')),
                  items: [
                    for (final a in accounts)
                      DropdownMenuItem(value: a.id, child: Text('${a.name} (${a.currency})',
                          overflow: TextOverflow.ellipsis)),
                  ],
                  onChanged: (v) => setState(() => accountId = v ?? accountId),
                ),
              ),
              const SizedBox(width: 12),
              ActionChip(
                avatar: const Icon(Icons.event_outlined, size: 18),
                label: Text(DateFormat.MMMd(app.lang).format(date)),
                onPressed: () async {
                  final d = await showDatePicker(
                      context: context,
                      initialDate: date,
                      firstDate: DateTime(2000),
                      lastDate: DateTime(2100));
                  if (d != null) setState(() => date = d);
                },
              ),
            ]),
            SectionTitle(app.t('Category')),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final c in cats)
                ChoiceChip(
                  avatar: Icon(categoryIcon(c.icon, c.name), size: 18,
                      color: hexColor(c.color, scheme.primary)),
                  label: Text(c.name),
                  selected: categoryId == c.id,
                  onSelected: (sel) => setState(() {
                    categoryTouched = true;
                    categoryId = sel ? c.id : null;
                  }),
                ),
            ]),
            const SizedBox(height: 12),
            TextField(
              controller: note,
              decoration: InputDecoration(
                  labelText: app.t('Note'), prefixIcon: const Icon(Icons.notes_outlined)),
            ),
            const SizedBox(height: 12),
          ]),
        ),
        _Keypad(onKey: _key, onDone: _save, doneLabel: app.t('Save')),
      ]),
    );
  }
}

class _Keypad extends StatelessWidget {
  const _Keypad({required this.onKey, required this.onDone, required this.doneLabel});
  final void Function(String) onKey;
  final VoidCallback onDone;
  final String doneLabel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Widget key(String k) => Expanded(
          child: Padding(
            padding: const EdgeInsets.all(4),
            child: Material(
              color: scheme.surfaceContainerHigh,
              borderRadius: BorderRadius.circular(18),
              child: InkWell(
                borderRadius: BorderRadius.circular(18),
                onTap: () => onKey(k),
                child: SizedBox(
                  height: 54,
                  child: Center(
                    child: k == '⌫'
                        ? const Icon(Icons.backspace_outlined)
                        : Text(k, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
                  ),
                ),
              ),
            ),
          ),
        );
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
        color: scheme.surfaceContainerLow,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          for (final row in const [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            ['.', '0', '⌫'],
          ])
            Row(children: [for (final k in row) key(k)]),
          Padding(
            padding: const EdgeInsets.all(4),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                  onPressed: onDone, icon: const Icon(Icons.check), label: Text(doneLabel)),
            ),
          ),
        ]),
      ),
    );
  }
}
