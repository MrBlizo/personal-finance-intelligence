// Reads the amount, date and shop from receipt text recognised on the phone
// (ML Kit, offline). The same rules as backend/app/services/receipts.py on
// the PC, so a receipt reads the same on both.

class ReceiptRead {
  ReceiptRead(this.amount, this.fromTotal, this.date, this.merchant,
      this.currency);

  /// The amount paid in minor units (cents), or null.
  final int? amount;

  /// True when a total line was found; false when the largest amount was used.
  final bool fromTotal;
  final DateTime? date;
  final String? merchant;
  final String? currency;
}

const _totalWords = [
  'net a payer', 'total a payer', 'montant a payer', 'a payer',
  'amount due', 'total due', 'balance due', 'grand total',
  'total ttc', 'montant ttc', 'zu zahlen', 'gesamtbetrag', 'gesamt',
  'summe', 'totale', 'total chf', 'total eur', 'total mad', 'total',
  'montant', 'betrag', 'importe', 'المجموع', 'المبلغ',
];
const _notTotal = [
  'subtotal', 'sous-total', 'sous total', 'zwischensumme', 'tva', 'tax',
  'mwst', 'vat', 'rendu', 'change', 'monnaie', 'rabais', 'remise',
  'discount', 'points', 'cash', 'especes', 'bar', 'carte', 'card',
];
const _skipShop = [
  'receipt', 'ticket', 'facture', 'invoice', 'quittung', 'beleg',
  'bienvenue', 'welcome', 'willkommen', 'merci', 'thank', 'danke', 'tel',
  'www', 'http', '@',
];
const _currencies = [
  ('CHF', 'CHF'), ('EUR', 'EUR'), ('€', 'EUR'), ('MAD', 'MAD'),
  ('DH', 'MAD'), ('DHS', 'MAD'), ('USD', 'USD'), (r'$', 'USD'),
  ('GBP', 'GBP'), ('£', 'GBP'), ('درهم', 'MAD'),
];
const _monthNames = [
  'jan janv januar enero', 'feb fev fevr februar febrero',
  'mar mars marz marzo', 'apr avr avril april abril', 'may mai mayo',
  'jun juin juni junio', 'jul juil juli julio', 'aug aout august agosto',
  'sep sept septembre september septiembre', 'oct octobre oktober octubre',
  'nov novembre november noviembre', 'dec decembre dezember diciembre',
];
final _months = {
  for (var i = 0; i < _monthNames.length; i++)
    for (final m in _monthNames[i].split(' ')) m: i + 1
};

final _amount = RegExp(
    r"(?<![\d.,'])(\d{1,3}(?:[ '., ]\d{3})+|\d+)([.,]\d{1,2})?(?!\d)");
final _numericDate = RegExp(r'\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b'
    r'|\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b');
final _letter = RegExp(r'\p{L}', unicode: true);
final _wordDate = RegExp(r'\b(\d{1,2})\.?\s+([a-z]{3,9})\.?\s+(\d{2,4})\b');

const _accents = {
  'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'ç': 'c', 'é': 'e', 'è': 'e',
  'ê': 'e', 'ë': 'e', 'î': 'i', 'ï': 'i', 'í': 'i', 'ô': 'o', 'ö': 'o',
  'ó': 'o', 'ù': 'u', 'û': 'u', 'ü': 'u', 'ú': 'u', 'ñ': 'n',
};

String _plain(String text) {
  final lower = text.toLowerCase();
  final out = StringBuffer();
  for (final r in lower.runes) {
    final c = String.fromCharCode(r);
    out.write(_accents[c] ?? c);
  }
  return out.toString();
}

/// One printed amount in minor units, whatever the thousands and decimal
/// marks ("1'234.50", "1.234,50", "12,5"); null when it is not an amount.
int? parseReceiptAmount(String token) {
  final s = token.trim().replaceAll(' ', ' ');
  final m = RegExp(r'^(.*?)([.,])(\d{1,2})$').firstMatch(s);
  var whole = m == null ? s : m[1]!;
  final cents = m == null ? '' : m[3]!;
  whole = whole.replaceAll(RegExp(r"[ '.,]"), '');
  if (whole.isEmpty || !RegExp(r'^\d+$').hasMatch(whole)) return null;
  final c = cents.isEmpty ? 0 : int.parse(cents.padRight(2, '0'));
  return int.parse(whole) * 100 + c;
}

List<int> _amounts(String line) => [
      for (final m in _amount.allMatches(line))
        if (m[2] != null)
          if (parseReceiptAmount(m[0]!) case final v? when v > 0) v
    ];

DateTime? _valid(int y, int m, int d, DateTime today) {
  if (y < 100) y += 2000;
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  final found = DateTime(y, m, d);
  if (found.month != m || found.day != d) return null;
  if (found.isBefore(DateTime(2000)) || found.isAfter(today)) return null;
  return found;
}

/// The first plausible purchase date on the receipt.
DateTime? findReceiptDate(String text, {DateTime? today, bool dayFirst = true}) {
  final now = today ?? DateTime.now();
  final limit = DateTime(now.year, now.month, now.day);
  for (final m in _numericDate.allMatches(text)) {
    DateTime? found;
    if (m[1] != null) {
      found = _valid(int.parse(m[1]!), int.parse(m[2]!), int.parse(m[3]!), limit);
    } else {
      final a = int.parse(m[4]!), b = int.parse(m[5]!), y = int.parse(m[6]!);
      var (d, mo) = dayFirst || a > 12 ? (a, b) : (b, a);
      if (mo > 12) (d, mo) = (mo, d);
      found = _valid(y, mo, d, limit);
    }
    if (found != null) return found;
  }
  for (final m in _wordDate.allMatches(_plain(text))) {
    final name = m[2]!;
    final month = _months[name.length >= 4 ? name.substring(0, 4) : name] ??
        _months[name.substring(0, 3)];
    if (month == null) continue;
    final found = _valid(int.parse(m[3]!), month, int.parse(m[1]!), limit);
    if (found != null) return found;
  }
  return null;
}

(int?, bool) _total(List<String> lines) {
  final plain = [for (final l in lines) _plain(l)];
  for (final word in _totalWords) {
    for (var i = 0; i < plain.length; i++) {
      final line = plain[i];
      if (!line.contains(word)) continue;
      if (_notTotal.any((n) => !word.contains(n) && line.contains(n))) continue;
      for (final candidate in [lines[i], if (i + 1 < lines.length) lines[i + 1]]) {
        final found = _amounts(candidate);
        if (found.isNotEmpty) return (found.last, true);
      }
    }
  }
  final every = [for (final l in lines) ..._amounts(l)];
  if (every.isEmpty) return (null, false);
  every.sort();
  return (every.last, false);
}

String? _shop(List<String> lines) {
  for (final line in lines.take(8)) {
    final text = line.replaceAll(RegExp(r'^[\s*\-=#:.]+|[\s*\-=#:.]+$'), '');
    final letters = _letter.allMatches(text).length;
    if (letters < 3 || letters < text.length / 2) continue;
    final p = _plain(text);
    if (_skipShop.any(p.contains)) continue;
    if (_numericDate.hasMatch(text)) continue;
    if (text == text.toUpperCase()) {
      return text
          .toLowerCase()
          .split(' ')
          .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
          .join(' ');
    }
    return text;
  }
  return null;
}

String? _currency(String text) {
  final counts = <String, int>{};
  for (final (mark, code) in _currencies) {
    final isWord = RegExp(r'^[A-Za-z]+$').hasMatch(mark);
    final re = isWord
        ? RegExp('(?<![A-Za-z])$mark(?![A-Za-z])', caseSensitive: false)
        : RegExp(RegExp.escape(mark));
    counts[code] = (counts[code] ?? 0) + re.allMatches(text).length;
  }
  final best = counts.entries.reduce((a, b) => b.value > a.value ? b : a);
  return best.value > 0 ? best.key : null;
}

/// Reads amount, date, shop and currency from recognised receipt text.
ReceiptRead parseReceipt(String text, {DateTime? today, bool dayFirst = true}) {
  final lines = [
    for (final l in text.split('\n'))
      if (l.trim().isNotEmpty) l.trim()
  ];
  final (amount, fromTotal) = _total(lines);
  return ReceiptRead(amount, fromTotal,
      findReceiptDate(text, today: today, dayFirst: dayFirst), _shop(lines),
      _currency(text));
}
