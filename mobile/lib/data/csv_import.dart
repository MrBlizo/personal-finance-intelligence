// Bank statement (CSV) import on the phone: reading the file, guessing the
// columns, and adding the rows without duplicates. Fingerprints use the same
// recipe as the PC importer (backend/app/services/importer.py).
import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'repo.dart';

/// A CSV file split into a header and rows.
class CsvTable {
  CsvTable(this.header, this.rows, {this.firstLine = 2});
  final List<String> header;
  final List<List<String>> rows;

  /// The file's line number of the first row (for error messages).
  final int firstLine;
}

/// Which columns hold what, and how to read them.
class CsvMapping {
  int? date;
  int? description;
  int? amount;
  int? debit;
  int? credit;
  bool dayFirst = true;
  bool decimalComma = false;
  bool invert = false;
  bool get complete =>
      date != null && description != null && (amount != null || debit != null || credit != null);
}

/// Decodes the file (UTF-8, else Latin-1) and splits it into cells.
CsvTable readCsv(List<int> bytes) {
  String text;
  try {
    text = utf8.decode(bytes);
  } on FormatException {
    text = latin1.decode(bytes);
  }
  if (text.startsWith('﻿')) text = text.substring(1);
  final lines = const LineSplitter().convert(text).where((l) => l.trim().isNotEmpty).toList();
  if (lines.isEmpty) return CsvTable([], []);
  final sample = lines.take(5).join('\n');
  final sep = [';', '\t', ',', '|']
      .reduce((a, b) => b.allMatches(sample).length > a.allMatches(sample).length ? b : a);
  final all = _split(lines.join('\n'), sep);
  // Skip title lines some banks print above the header: the header is the
  // first row with as many cells as the rows below it.
  final width = all.length > 1 ? all[all.length ~/ 2].length : all.first.length;
  final start = all.indexWhere((r) => r.length >= width && r.where((c) => c.trim().isNotEmpty).length >= 2);
  final from = start < 0 ? 0 : start;
  return CsvTable([for (final h in all[from]) h.trim()],
      [for (final r in all.skip(from + 1)) if (r.any((c) => c.trim().isNotEmpty)) r],
      firstLine: from + 2);
}

List<List<String>> _split(String text, String sep) {
  final rows = <List<String>>[];
  var row = <String>[];
  final cell = StringBuffer();
  var quoted = false;
  for (var i = 0; i < text.length; i++) {
    final c = text[i];
    if (quoted) {
      if (c == '"') {
        if (i + 1 < text.length && text[i + 1] == '"') {
          cell.write('"');
          i++;
        } else {
          quoted = false;
        }
      } else {
        cell.write(c);
      }
    } else if (c == '"') {
      quoted = true;
    } else if (c == sep) {
      row.add(cell.toString());
      cell.clear();
    } else if (c == '\n') {
      row.add(cell.toString());
      cell.clear();
      rows.add(row);
      row = <String>[];
    } else if (c != '\r') {
      cell.write(c);
    }
  }
  row.add(cell.toString());
  rows.add(row);
  return rows;
}

String _plain(String s) => s
    .toLowerCase()
    .replaceAll(RegExp('[éèêë]'), 'e')
    .replaceAll(RegExp('[àâä]'), 'a')
    .replaceAll(RegExp('[ùûü]'), 'u')
    .replaceAll(RegExp('[ôö]'), 'o')
    .trim();

Set<int> _ids(List<int?> xs) => {for (final x in xs) if (x != null) x};

int? _find(List<String> header, List<String> words, {Set<int> skip = const {}}) {
  for (final w in words) {
    for (var i = 0; i < header.length; i++) {
      if (!skip.contains(i) && _plain(header[i]).contains(w)) return i;
    }
  }
  return null;
}

/// Guesses the columns from the header names (English, French, German) and
/// the number format from the values.
CsvMapping guessMapping(CsvTable t, {bool dayFirst = true}) {
  final m = CsvMapping()..dayFirst = dayFirst;
  final h = t.header;
  m.date = _find(h, ['date operation', 'booking date', 'buchungsdatum', 'date', 'datum', 'fecha', 'التاريخ']);
  m.debit = _find(h, ['debit', 'soll', 'withdrawal', 'belastung', 'مدين'], skip: _ids([m.date]));
  m.credit = _find(h, ['credit', 'haben', 'deposit', 'gutschrift', 'دائن'], skip: _ids([m.date, m.debit]));
  if (m.debit == null || m.credit == null) {
    m.debit = m.credit = null;
    m.amount = _find(h, ['amount', 'montant', 'betrag', 'importe', 'value', 'المبلغ'], skip: _ids([m.date]));
  }
  m.description = _find(h, [
    'libelle', 'description', 'payee', 'merchant', 'beschreibung', 'buchungstext',
    'details', 'memo', 'name', 'text', 'البيان'
  ], skip: _ids([m.date, m.amount, m.debit, m.credit]));
  final values = [
    for (final r in t.rows.take(30))
      for (final i in [m.amount, m.debit, m.credit])
        if (i != null && i < r.length) r[i].trim()
  ];
  final comma = values.where((v) => RegExp(r',\d{1,2}$').hasMatch(v)).length;
  final dot = values.where((v) => RegExp(r'\.\d{1,2}$').hasMatch(v)).length;
  m.decimalComma = comma > dot;
  return m;
}

/// One amount in minor units, or null when the cell is empty or not a number.
int? parseCsvAmount(String text, {required bool decimalComma}) {
  var s = text.trim().replaceAll(RegExp(r"[\s'  ]"), '');
  s = s.replaceAll(RegExp(r'[^\d.,\-+()]'), '');
  if (s.isEmpty) return null;
  var negative = s.startsWith('-') || s.endsWith('-') || (s.startsWith('(') && s.endsWith(')'));
  s = s.replaceAll(RegExp(r'[\-+()]'), '');
  s = decimalComma ? s.replaceAll('.', '').replaceAll(',', '.') : s.replaceAll(',', '');
  final v = double.tryParse(s);
  if (v == null) return null;
  final minor = (v * 100).round();
  if (minor == 0) negative = false;
  return negative ? -minor : minor;
}

/// A date in the usual bank formats; [dayFirst] decides 03/04/2026.
DateTime? parseCsvDate(String text, {required bool dayFirst}) {
  final s = text.trim();
  var m = RegExp(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})').firstMatch(s);
  if (m != null) return _date(int.parse(m[1]!), int.parse(m[2]!), int.parse(m[3]!));
  m = RegExp(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})').firstMatch(s);
  if (m != null) {
    final a = int.parse(m[1]!), b = int.parse(m[2]!);
    var y = int.parse(m[3]!);
    if (y < 100) y += 2000;
    return dayFirst || a > 12 ? _date(y, b, a) : _date(y, a, b);
  }
  m = RegExp(r'^(\d{4})(\d{2})(\d{2})$').firstMatch(s);
  if (m != null) return _date(int.parse(m[1]!), int.parse(m[2]!), int.parse(m[3]!));
  return null;
}

DateTime? _date(int y, int m, int d) {
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  final out = DateTime(y, m, d);
  return out.month == m ? out : null;
}

/// One readable row of the statement.
class CsvRow {
  CsvRow(this.line, this.date, this.amount, this.description);
  final int line;
  final DateTime date;
  final int amount;
  final String description;
}

/// The rows that could be read, and the line numbers of those that could not.
(List<CsvRow>, List<int>) readRows(CsvTable t, CsvMapping m) {
  final ok = <CsvRow>[];
  final bad = <int>[];
  String cell(List<String> r, int? i) => i == null || i >= r.length ? '' : r[i];
  for (var n = 0; n < t.rows.length; n++) {
    final r = t.rows[n];
    final date = parseCsvDate(cell(r, m.date), dayFirst: m.dayFirst);
    int? amount;
    if (m.amount != null) {
      amount = parseCsvAmount(cell(r, m.amount), decimalComma: m.decimalComma);
    } else {
      final d = parseCsvAmount(cell(r, m.debit), decimalComma: m.decimalComma);
      final c = parseCsvAmount(cell(r, m.credit), decimalComma: m.decimalComma);
      if (d != null || c != null) amount = (c?.abs() ?? 0) - (d?.abs() ?? 0);
    }
    if (date == null || amount == null || amount == 0) {
      bad.add(t.firstLine + n);
      continue;
    }
    ok.add(CsvRow(t.firstLine + n, date, m.invert ? -amount : amount,
        cell(r, m.description).replaceAll(RegExp(r'\s+'), ' ').trim()));
  }
  return (ok, bad);
}

/// The PC's de-duplication hash of an imported row.
String fingerprint(int accountId, DateTime day, int amount, String description, int occurrence) {
  final a = amount.abs();
  final text = '${amount < 0 ? '-' : ''}${a ~/ 100}.${(a % 100).toString().padLeft(2, '0')}';
  final key = '$accountId|${isoDate(day)}|$text|'
      '${description.replaceAll(RegExp(r'\s+'), ' ').trim().toLowerCase()}|$occurrence';
  return sha256.convert(utf8.encode(key)).toString();
}
