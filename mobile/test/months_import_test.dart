// Month by month and statement import on the phone.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/data/csv_import.dart';
import 'package:pfi/data/repo.dart';

import 'support.dart';

void main() {
  test('month summary: earned, spent, saved, paid and categories', () {
    final app = memoryDb()..seed('CHF');
    final repo = Repo(app);
    final main = repo.addAccount('Main', 'checking', 'CHF', 0, DateTime(2026, 1, 1));
    final savings = repo.addAccount('Rainy day', 'savings', 'CHF', 0, DateTime(2026, 1, 1));
    final food = repo.categories(kind: 'expense').first;
    repo.saveTransaction(accountId: main, date: DateTime(2026, 3, 1), amount: 300000, kind: 'income');
    repo.saveTransaction(
        accountId: main, date: DateTime(2026, 3, 5), amount: -12050, kind: 'expense',
        payee: 'Market', categoryId: food.id);
    repo.saveTransaction(accountId: main, date: DateTime(2026, 2, 10), amount: -8000, kind: 'expense');
    app.db.execute(
        "INSERT INTO transactions (account_id, txn_date, amount, kind, description, cleared, reviewed) "
        "VALUES (?, '2026-03-20', -50000, 'transfer', 'To savings', 0, 1), "
        "(?, '2026-03-20', 50000, 'transfer', 'From main', 0, 1)",
        [main, savings]);

    final m = repo.monthSummary(DateTime(2026, 3, 15));
    expect(m.income, 300000);
    expect(m.spent, 12050);
    expect(m.saved, 50000);
    expect(m.paid, 0);
    expect(m.categories[food.parentName ?? food.name], 12050);
    expect(m.daily[4], 12050);
    expect(m.biggest.first.$1, 'Market');
    expect(repo.monthSummary(DateTime(2026, 2)).spent, 8000);
    expect(repo.firstMonth(), DateTime(2026, 2));
  });

  test('CSV statement: guessed columns, decimal comma, no duplicates', () {
    const csv = 'Relevé du compte\n'
        'Date opération;Libellé;Débit;Crédit\n'
        '02/03/2026;CARREFOUR MARKET;45,90;\n'
        '05/03/2026;SALAIRE;;3 200,00\n'
        '05/03/2026;"BOULANGERIE ""LE PAIN""";4,20;\n'
        'xx;broken;1,00;\n';
    final table = readCsv(utf8.encode(csv));
    expect(table.header, ['Date opération', 'Libellé', 'Débit', 'Crédit']);
    final map = guessMapping(table);
    expect(map.date, 0);
    expect(map.description, 1);
    expect(map.debit, 2);
    expect(map.credit, 3);
    expect(map.decimalComma, isTrue);
    final (rows, bad) = readRows(table, map);
    expect(rows.map((r) => r.amount), [-4590, 320000, -420]);
    expect(rows[2].description, 'BOULANGERIE "LE PAIN"');
    expect(rows.first.date, DateTime(2026, 3, 2));
    expect(bad, [6]);

    final app = memoryDb()..seed('EUR');
    final repo = Repo(app);
    final acc = repo.addAccount('Banque', 'checking', 'EUR', 0, DateTime(2026, 1, 1));
    expect(repo.importRows(acc, rows), (added: 3, duplicates: 0));
    expect(repo.importRows(acc, rows), (added: 0, duplicates: 3));
    expect(repo.transactions(accountId: acc).where((t) => !t.reviewed).length, 3);
  });

  test('amounts and dates in bank formats', () {
    expect(parseCsvAmount("1'234.50", decimalComma: false), 123450);
    expect(parseCsvAmount('-1.234,50', decimalComma: true), -123450);
    expect(parseCsvAmount('(12.00)', decimalComma: false), -1200);
    expect(parseCsvAmount('12.00-', decimalComma: false), -1200);
    expect(parseCsvAmount('', decimalComma: false), isNull);
    expect(parseCsvDate('2026-03-04', dayFirst: true), DateTime(2026, 3, 4));
    expect(parseCsvDate('03/04/2026', dayFirst: false), DateTime(2026, 3, 4));
    expect(parseCsvDate('03/04/26', dayFirst: true), DateTime(2026, 4, 3));
    expect(parseCsvDate('31/02/2026', dayFirst: true), isNull);
  });

  test('fingerprints match the PC importer', () {
    // backend: fingerprint(7, date(2026, 3, 2), Decimal("-45.90"),
    //                      "Carrefour  Market", 0)
    expect(fingerprint(7, DateTime(2026, 3, 2), -4590, 'Carrefour  Market', 0),
        'd18f695f2099fa2f16772375658167f7bb277495faa433d07f18ff82f5b19177');
  });
}
