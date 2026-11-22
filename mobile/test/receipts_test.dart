// The phone reads receipts like the PC (backend/tests/test_v10_receipts.py).
import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/data/receipts.dart';

final today = DateTime(2026, 11, 22);

const migros = '''MIGROS
Filiale Bern Bahnhof
Tel. 058 567 89 00
Bananen        1.95
Vollmilch 1l   1.60
Brot           3.20
Total CHF      6.75
Bar            10.00
Rückgeld       3.25
MWST 2.6%      0.17
21.11.2026 18:42
''';

const marjane = '''*** MARJANE ***
Bienvenue
Hay Riad Rabat
LAIT CENTRALE      7,50
PAIN               2,00
HUILE 1L          24,90
SOUS-TOTAL        34,40
NET A PAYER       34,40 DH
ESPECES           50,00
RENDU             15,60
Le 14/10/2026 a 11:05
''';

const us = r'''Whole Foods Market
www.wholefoods.com
Organic apples   4.99
Coffee beans    12.49
Subtotal        17.48
Tax              1.40
TOTAL          $18.88
VISA CARD      $18.88
03/04/2026 09:12
''';

const splitLines = '''CAFE DU MONDE
2 x Espresso
Montant TTC
9,80 €
Date: 2 nov. 2026
''';

const thousands = '''BRICO DEPOT
Perceuse                1 249,00
TOTAL TTC               1 249,00 EUR
05.09.2026
''';

void main() {
  for (final (text, amount, day, shop, currency) in [
    (migros, 675, DateTime(2026, 11, 21), 'Migros', 'CHF'),
    (marjane, 3440, DateTime(2026, 10, 14), 'Marjane', 'MAD'),
    (splitLines, 980, DateTime(2026, 11, 2), 'Cafe Du Monde', 'EUR'),
    (thousands, 124900, DateTime(2026, 9, 5), 'Brico Depot', 'EUR'),
  ]) {
    test('reads $shop', () {
      final r = parseReceipt(text, today: today);
      expect(r.amount, amount);
      expect(r.fromTotal, isTrue);
      expect(r.date, day);
      expect(r.merchant, shop);
      expect(r.currency, currency);
    });
  }

  test('US receipt: month first, skips subtotal and tax', () {
    final r = parseReceipt(us, today: today, dayFirst: false);
    expect(r.amount, 1888);
    expect(r.date, DateTime(2026, 3, 4));
    expect(r.merchant, 'Whole Foods Market');
    expect(r.currency, 'USD');
    expect(parseReceipt(us, today: today).date, DateTime(2026, 4, 3));
  });

  test('largest amount when there is no total; future dates ignored', () {
    final r = parseReceipt('Kiosk\nA 2.50\nB 4.10\n01.01.2099', today: today);
    expect(r.amount, 410);
    expect(r.fromTotal, isFalse);
    expect(r.date, isNull);
  });

  test('nothing readable', () {
    final r = parseReceipt('', today: today);
    expect(r.amount, isNull);
    expect(r.date, isNull);
    expect(r.merchant, isNull);
    expect(r.currency, isNull);
  });

  test('amount formats', () {
    expect(parseReceiptAmount("1'234.50"), 123450);
    expect(parseReceiptAmount('1.234,50'), 123450);
    expect(parseReceiptAmount('1,234.50'), 123450);
    expect(parseReceiptAmount('12,5'), 1250);
    expect(parseReceiptAmount('7'), 700);
    expect(parseReceiptAmount('abc'), isNull);
  });
}
