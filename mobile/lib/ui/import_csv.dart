// Import a bank statement (CSV) on the phone: choose the file, check the
// columns PFI guessed, see the first rows, import. Rows imported before are
// skipped, and new rows wait in the review list as on the PC.
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/csv_import.dart';
import 'widgets.dart';

class ImportCsvPage extends StatefulWidget {
  const ImportCsvPage({super.key});
  @override
  State<ImportCsvPage> createState() => _ImportCsvPageState();
}

class _ImportCsvPageState extends State<ImportCsvPage> {
  String? fileName;
  CsvTable? table;
  CsvMapping? mapping;
  int? accountId;
  String? error;
  bool busy = false;

  Future<void> _pick() async {
    final app = appOf(context, listen: false);
    setState(() => error = null);
    final res = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['csv', 'txt'], withData: true);
    final file = res?.files.firstOrNull;
    if (file == null) return;
    final bytes = file.bytes;
    if (bytes == null) {
      setState(() => error = app.t('The file could not be read. Copy it to the phone and try again.'));
      return;
    }
    final t = readCsv(bytes);
    if (t.rows.isEmpty) {
      setState(() => error = app.t('No rows were found in this file. Export a CSV statement from your bank.'));
      return;
    }
    setState(() {
      fileName = file.name;
      table = t;
      mapping = guessMapping(t, dayFirst: app.repo.baseCurrency != 'USD');
    });
  }

  Future<void> _import(List<CsvRow> rows) async {
    final app = appOf(context, listen: false);
    final account = accountId;
    if (account == null) {
      setState(() => error = app.t('Choose the account this statement belongs to.'));
      return;
    }
    setState(() => busy = true);
    try {
      final r = app.repo.importRows(account, rows);
      app.changed();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.task_alt_rounded),
          title: Text(app.t('{n} transactions imported', {'n': r.added})),
          content: Text(r.duplicates > 0
              ? app.t('{n} were already in PFI and were skipped. New rows are in the review list.', {'n': r.duplicates})
              : app.t('New rows are in the review list.')),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(app.t('Done')))],
        ),
      );
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      setState(() => error = app.t('The import failed: {e}', {'e': e.toString()}));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final scheme = Theme.of(context).colorScheme;
    final accounts = app.repo.accounts();
    accountId ??= accounts.firstOrNull?.id;
    final t = table, m = mapping;
    final (rows, bad) = t != null && m != null && m.complete ? readRows(t, m) : (<CsvRow>[], <int>[]);
    final currency = accounts.where((a) => a.id == accountId).firstOrNull?.currency ?? app.repo.baseCurrency;

    Widget column(String label, int? value, void Function(int?) set, {bool optional = false}) =>
        DropdownButtonFormField<int?>(
          value: value,
          isExpanded: true,
          decoration: InputDecoration(labelText: label),
          items: [
            if (optional) DropdownMenuItem(value: null, child: Text(app.t('None'))),
            for (var i = 0; i < t!.header.length; i++)
              DropdownMenuItem(value: i, child: Text(t.header[i].isEmpty ? '#${i + 1}' : t.header[i],
                  overflow: TextOverflow.ellipsis)),
          ],
          onChanged: (v) => setState(() => set(v)),
        );

    return Scaffold(
      appBar: AppBar(title: Text(app.t('Import a bank statement'))),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(
          color: scheme.secondaryContainer,
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            leading: Icon(Icons.upload_file_rounded, color: scheme.onSecondaryContainer),
            title: Text(fileName ?? app.t('Choose a CSV file'),
                style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onSecondaryContainer)),
            subtitle: Text(app.t('Export the statement from your bank app as CSV. The file stays on this phone.'),
                style: TextStyle(color: scheme.onSecondaryContainer)),
            onTap: _pick,
          ),
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(error!, style: TextStyle(color: scheme.error)),
          ),
        if (t != null && m != null) ...[
          SectionTitle(app.t('Account')),
          DropdownButtonFormField<int>(
            value: accountId,
            isExpanded: true,
            items: [
              for (final a in accounts)
                DropdownMenuItem(value: a.id, child: Text('${a.name} (${a.currency})')),
            ],
            onChanged: (v) => setState(() => accountId = v),
          ),
          SectionTitle(app.t('Columns')),
          column(app.t('Date'), m.date, (v) => m.date = v),
          const SizedBox(height: 8),
          column(app.t('Description'), m.description, (v) => m.description = v),
          const SizedBox(height: 8),
          if (m.amount != null || (m.debit == null && m.credit == null))
            column(app.t('Amount'), m.amount, (v) => m.amount = v)
          else ...[
            column(app.t('Money out (debit)'), m.debit, (v) => m.debit = v, optional: true),
            const SizedBox(height: 8),
            column(app.t('Money in (credit)'), m.credit, (v) => m.credit = v, optional: true),
          ],
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(app.t('Separate columns for money in and out')),
            value: m.amount == null,
            onChanged: (sep) => setState(() {
              if (sep) {
                m.debit = m.amount;
                m.amount = null;
              } else {
                m.amount = m.debit ?? m.credit;
                m.debit = m.credit = null;
              }
            }),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(app.t('Day before month (31/12/2026)')),
            value: m.dayFirst,
            onChanged: (v) => setState(() => m.dayFirst = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(app.t('Decimal comma (12,50)')),
            value: m.decimalComma,
            onChanged: (v) => setState(() => m.decimalComma = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(app.t('Flip signs (spending is shown as positive)')),
            value: m.invert,
            onChanged: (v) => setState(() => m.invert = v),
          ),
          SectionTitle(app.t('Preview')),
          if (!m.complete)
            Text(app.t('Choose the date, description and amount columns.'))
          else ...[
            Card(
              child: Column(children: [
                for (final r in rows.take(6))
                  ListTile(
                    dense: true,
                    title: Text(r.description.isEmpty ? '—' : r.description,
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    subtitle: Text(DateFormat.yMMMd(app.lang).format(r.date)),
                    trailing: AmountText(r.amount, currency),
                  ),
              ]),
            ),
            const SizedBox(height: 8),
            Text(app.t('{n} rows can be imported.', {'n': rows.length})),
            if (bad.isNotEmpty)
              Text(
                  app.t('{n} rows could not be read (lines {l}).',
                      {'n': bad.length, 'l': bad.take(8).join(', ') + (bad.length > 8 ? '…' : '')}),
                  style: TextStyle(color: scheme.error)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: busy || rows.isEmpty ? null : () => _import(rows),
              icon: const Icon(Icons.download_done_rounded),
              label: Text(app.t('Import {n} rows', {'n': rows.length})),
            ),
          ],
        ],
      ]),
    );
  }
}
