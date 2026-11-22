// Queries and edits the screens use. Money is handled in minor units
// (cents): the database stores amounts as integers scaled by 100, the same
// as PFI on Windows.
import 'package:sqlite3/sqlite3.dart';

import 'csv_import.dart';
import 'db.dart';

const liquidTypes = ['checking', 'savings', 'cash', 'credit_card'];

String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

DateTime monthStart(DateTime d) => DateTime(d.year, d.month);
DateTime addMonths(DateTime d, int n) => DateTime(d.year, d.month + n);

class Account {
  Account(this.id, this.name, this.type, this.currency, this.balance,
      this.archived);
  final int id;
  final String name;
  final String type;
  final String currency;
  final int balance;
  final bool archived;
  bool get liquid => liquidTypes.contains(type);
}

class Category {
  Category(this.id, this.name, this.kind, this.parentId, this.parentName,
      this.color, this.icon);
  final int id;
  final String name;
  final String kind;
  final int? parentId;
  final String? parentName;
  final String? color;
  final String? icon;
  String get label => parentName == null ? name : '$parentName › $name';
}

class Txn {
  Txn(this.id, this.date, this.amount, this.kind, this.description,
      this.merchant, this.notes, this.accountId, this.accountName,
      this.currency, this.categoryId, this.categoryName, this.categoryColor,
      this.categoryIcon, this.reviewed);
  final int id;
  final DateTime date;
  final int amount;
  final String kind;
  final String description;
  final String? merchant;
  final String? notes;
  final int accountId;
  final String accountName;
  final String currency;
  final int? categoryId;
  final String? categoryName;
  final String? categoryColor;
  final String? categoryIcon;
  final bool reviewed;
  String get title =>
      (merchant?.isNotEmpty ?? false) ? merchant! : (description.isEmpty ? '—' : description);
}

class EnvelopeRow {
  EnvelopeRow(this.category, this.assigned, this.activity, this.available,
      this.need);
  final Category? category; // null = uncategorised spending
  final int assigned;
  final int activity;
  final int available;
  final int need;
}

class EnvelopeMonth {
  EnvelopeMonth(this.month, this.currency, this.readyToAssign, this.rows,
      this.missingFx);
  final DateTime month;
  final String currency;
  final int readyToAssign;
  final List<EnvelopeRow> rows;
  final Set<String> missingFx;
  int get assigned => rows.fold<int>(0, (s, r) => s + r.assigned);
  int get activity => rows.fold<int>(0, (s, r) => s + r.activity);
  int get available => rows.fold<int>(0, (s, r) => s + r.available);
}

/// Currency conversion with the exchange rates PFI on Windows downloads
/// (synced): the latest rate on or before the date, direct or inverse.
class Fx {
  Fx(Database db) {
    for (final r in db.select(
        'SELECT rate_date, from_currency, to_currency, rate FROM exchange_rates '
        'ORDER BY rate_date')) {
      final rate = (r['rate'] as int) / 1e8;
      _rates.putIfAbsent('${r['from_currency']}>${r['to_currency']}', () => [])
          .add((r['rate_date'] as String, rate));
    }
  }
  final Map<String, List<(String, double)>> _rates = {};

  double? _pick(String pair, String day) {
    final list = _rates[pair];
    if (list == null || list.isEmpty) return null;
    (String, double)? best;
    for (final e in list) {
      if (e.$1.compareTo(day) <= 0) {
        best = e;
      } else {
        break;
      }
    }
    return (best ?? list.first).$2;
  }

  double? _direct(String from, String to, String day) {
    final direct = _pick('$from>$to', day);
    if (direct != null) return direct;
    final inverse = _pick('$to>$from', day);
    return (inverse != null && inverse != 0) ? 1 / inverse : null;
  }

  double? rate(String from, String to, String day) {
    if (from == to) return 1;
    final direct = _direct(from, to, day);
    if (direct != null) return direct;
    final currencies = {for (final k in _rates.keys) ...k.split('>')};
    for (final mid in currencies) {
      if (mid == from || mid == to) continue;
      final a = _direct(from, mid, day);
      final b = a == null ? null : _direct(mid, to, day);
      if (a != null && b != null) return a * b;
    }
    return null;
  }
}

class Goal {
  Goal(this.id, this.name, this.currency, this.target, this.saved,
      this.targetDate, this.accountId, this.manualSaved, this.notes);
  final int id;
  final String name;
  final String currency;
  final int target;
  final int saved;
  final DateTime? targetDate;
  final int? accountId;
  final int manualSaved;
  final String? notes;
  double get progress => target <= 0 ? 0 : (saved / target).clamp(0.0, 1.0);
  int get remaining => (target - saved).clamp(0, target);

  /// Saving needed per month to reach the target on time (null: no date).
  int? monthlyNeeded(DateTime today) {
    if (targetDate == null) return null;
    final months = targetDate!.difference(today).inDays / 30.4375;
    return months <= 0 ? remaining : (remaining / months).round();
  }
}

class Bill {
  Bill(this.id, this.name, this.accountId, this.categoryId, this.amount,
      this.frequency, this.start, this.end, this.active, this.lastPosted);
  final int id;
  final String name;
  final int accountId;
  final int? categoryId;
  final int amount;
  final String frequency;
  final DateTime start;
  final DateTime? end;
  final bool active;
  final DateTime? lastPosted;

  /// The dates within [from, to], as in backend planning.occurrences.
  List<DateTime> occurrences(DateTime from, DateTime to) {
    final last = end != null && end!.isBefore(to) ? end! : to;
    final out = <DateTime>[];
    const days = {'weekly': 7, 'biweekly': 14};
    const months = {'monthly': 1, 'quarterly': 3, 'yearly': 12};
    for (var n = 0; n < 2000; n++) {
      final DateTime d;
      if (days.containsKey(frequency)) {
        d = start.add(Duration(days: n * days[frequency]!));
      } else {
        final m = start.month - 1 + n * months[frequency]!;
        final y = start.year + m ~/ 12;
        final mm = m % 12 + 1;
        final len = DateTime(y, mm + 1, 0).day;
        d = DateTime(y, mm, start.day > len ? len : start.day);
      }
      if (d.isAfter(last)) break;
      if (!d.isBefore(from)) out.add(d);
    }
    return out;
  }

  DateTime? nextDue(DateTime today) {
    final from = lastPosted != null && !lastPosted!.isBefore(today)
        ? lastPosted!.add(const Duration(days: 1))
        : today;
    final next = occurrences(from, from.add(const Duration(days: 400)));
    return next.isEmpty ? null : next.first;
  }
}

class Holding {
  Holding(this.id, this.accountId, this.symbol, this.name, this.assetClass,
      this.currency, this.quantity, this.cost, this.price, this.priceDate,
      this.dividends);
  final int id;
  final int accountId;
  final String symbol;
  final String name;
  final String assetClass;
  final String currency;
  /// Units held (a double: quantities have 8 decimals).
  final double quantity;
  /// Money paid for the units still held, in minor units.
  final int cost;
  /// Latest price per unit (null when no price is known).
  final double? price;
  final DateTime? priceDate;
  final int dividends;
  int? get value => price == null ? null : (quantity * price! * 100).round();
  int? get gain => value == null ? null : value! - cost;
}

class Debt {
  Debt(this.account, this.apr, this.minPayment);
  final Account account;
  /// Yearly interest in percent (e.g. 19.99).
  final double apr;
  final int minPayment;
  int get owed => account.balance < 0 ? -account.balance : 0;

  /// Months until paid off when paying [payment] each month (null: never).
  int? monthsToPayOff(int payment) {
    var left = owed.toDouble();
    final r = apr / 100 / 12;
    for (var m = 1; m <= 600; m++) {
      left = left * (1 + r) - payment;
      if (left <= 0) return m;
    }
    return null;
  }
}

/// One month's money: what came in, what went out, what was paid and saved.
class MonthSummary {
  MonthSummary(this.month);
  final DateTime month;
  int income = 0;
  int spent = 0;
  int bills = 0;
  int debtPayments = 0;
  int saved = 0;
  int get paid => bills + debtPayments;
  int get net => income - spent;
  double? get savingsRate => income > 0 ? (income - spent) / income : null;

  /// Spending per top-level category name ('' = uncategorised).
  final Map<String, int> categories = {};

  /// Bills paid: (name, amount, day).
  final List<(String, int, DateTime)> billsPaid = [];

  /// Biggest single expenses: (title, amount, day).
  final List<(String, int, DateTime)> biggest = [];

  /// Spending per day of the month (index 0 = day 1).
  late final List<int> daily =
      List.filled(DateTime(month.year, month.month + 1, 0).day, 0);
  final Set<String> missingFx = {};
}

class Repo {
  Repo(this.app);
  final AppDatabase app;
  Database get db => app.db;

  String get baseCurrency => app.setting('base_currency') ?? 'USD';

  List<Account> accounts({bool includeArchived = false}) {
    final rows = db.select(
        'SELECT a.id, a.name, a.type, a.currency, a.is_archived, '
        'a.opening_balance + coalesce((SELECT sum(amount) FROM transactions t '
        'WHERE t.account_id = a.id), 0) AS balance '
        'FROM accounts a ${includeArchived ? '' : 'WHERE a.is_archived = 0'} '
        'ORDER BY a.is_archived, a.name COLLATE NOCASE');
    return [
      for (final r in rows)
        Account(r['id'] as int, r['name'] as String, r['type'] as String,
            r['currency'] as String, r['balance'] as int,
            (r['is_archived'] as int) != 0)
    ];
  }

  List<Category> categories({String? kind}) {
    final rows = db.select(
        'SELECT c.id, c.name, c.kind, c.parent_id, p.name AS parent, '
        'coalesce(c.color, p.color) AS color, coalesce(c.icon, p.icon) AS icon '
        'FROM categories c LEFT JOIN categories p ON p.id = c.parent_id '
        '${kind == null ? '' : 'WHERE c.kind = ?'} '
        'ORDER BY coalesce(p.name, c.name) COLLATE NOCASE, '
        'c.parent_id IS NOT NULL, c.name COLLATE NOCASE',
        [if (kind != null) kind]);
    return [for (final r in rows) _cat(r)];
  }

  Category _cat(Row r) => Category(
      r['id'] as int,
      r['name'] as String,
      r['kind'] as String,
      r['parent_id'] as int?,
      r['parent'] as String?,
      r['color'] as String?,
      r['icon'] as String?);

  List<Txn> transactions({String search = '', int limit = 200, int? accountId}) {
    final where = <String>[];
    final args = <Object?>[];
    if (search.trim().isNotEmpty) {
      where.add('(t.description LIKE ? OR t.merchant LIKE ? OR t.notes LIKE ? '
          'OR c.name LIKE ?)');
      final q = '%${search.trim()}%';
      args.addAll([q, q, q, q]);
    }
    if (accountId != null) {
      where.add('t.account_id = ?');
      args.add(accountId);
    }
    final rows = db.select(
        'SELECT t.id, t.txn_date, t.amount, t.kind, t.description, t.merchant, '
        't.notes, t.account_id, a.name AS account, a.currency, t.category_id, '
        'c.name AS category, coalesce(c.color, p.color) AS color, '
        'coalesce(c.icon, p.icon) AS icon, t.reviewed '
        'FROM transactions t JOIN accounts a ON a.id = t.account_id '
        'LEFT JOIN categories c ON c.id = t.category_id '
        'LEFT JOIN categories p ON p.id = c.parent_id '
        '${where.isEmpty ? '' : 'WHERE ${where.join(' AND ')}'} '
        'ORDER BY t.txn_date DESC, t.id DESC LIMIT ?',
        [...args, limit]);
    return [
      for (final r in rows)
        Txn(
            r['id'] as int,
            DateTime.parse(r['txn_date'] as String),
            r['amount'] as int,
            r['kind'] as String,
            r['description'] as String,
            r['merchant'] as String?,
            r['notes'] as String?,
            r['account_id'] as int,
            r['account'] as String,
            r['currency'] as String,
            r['category_id'] as int?,
            r['category'] as String?,
            r['color'] as String?,
            r['icon'] as String?,
            (r['reviewed'] as int) != 0)
    ];
  }

  /// Payees used before, most recent first, with their last category.
  List<(String, int?)> payees(String prefix) {
    final rows = db.select(
        'SELECT merchant, category_id FROM transactions '
        "WHERE merchant LIKE ? AND merchant <> '' "
        'GROUP BY merchant ORDER BY max(txn_date) DESC LIMIT 8',
        ['${prefix.trim()}%']);
    return [for (final r in rows) (r['merchant'] as String, r['category_id'] as int?)];
  }

  int addAccount(String name, String type, String currency, int opening,
      DateTime openingDate) {
    db.execute(
        'INSERT INTO accounts (name, type, currency, opening_balance, '
        'opening_date, is_archived, is_demo) VALUES (?, ?, ?, ?, ?, 0, 0)',
        [name.trim(), type, currency, opening, isoDate(openingDate)]);
    return db.lastInsertRowId;
  }

  void saveTransaction({
    int? id,
    required int accountId,
    required DateTime date,
    required int amount,
    required String kind,
    String payee = '',
    int? categoryId,
    String? notes,
  }) {
    final args = [
      accountId, isoDate(date), amount, kind, payee.trim(),
      payee.trim().isEmpty ? null : payee.trim(), categoryId,
      (notes?.trim().isEmpty ?? true) ? null : notes!.trim(),
    ];
    if (id == null) {
      db.execute(
          'INSERT INTO transactions (account_id, txn_date, amount, kind, '
          'description, merchant, category_id, notes, category_source, '
          'cleared, reviewed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)',
          [...args, categoryId == null ? null : 'user']);
    } else {
      db.execute(
          'UPDATE transactions SET account_id = ?, txn_date = ?, amount = ?, '
          'kind = ?, description = ?, merchant = ?, category_id = ?, notes = ? '
          'WHERE id = ?',
          [...args, id]);
    }
  }

  /// Adds statement rows to an account, skipping rows imported before (same
  /// fingerprint as on the PC). Categories come from the category rules,
  /// then from the payee's last category. Imported rows wait in review.
  ({int added, int duplicates}) importRows(int accountId, List<CsvRow> rows) {
    final rules = [
      for (final r in db.select('SELECT pattern, match_field, is_regex, category_id '
          'FROM category_rules ORDER BY priority DESC, id'))
        r
    ];
    final known = <String, int?>{};
    int? categoryFor(String text) {
      for (final r in rules) {
        final pattern = r['pattern'] as String;
        final hit = (r['is_regex'] as int) != 0
            ? (RegExp(pattern, caseSensitive: false).hasMatch(text))
            : text.toLowerCase().contains(pattern.toLowerCase());
        if (hit) return r['category_id'] as int;
      }
      return known.putIfAbsent(text, () {
        final row = db.select(
            'SELECT category_id FROM transactions WHERE category_id IS NOT NULL '
            'AND (merchant = ? OR description = ?) ORDER BY txn_date DESC LIMIT 1',
            [text, text]);
        return row.isEmpty ? null : row.first['category_id'] as int?;
      });
    }

    final existing = {
      for (final r in db.select(
          'SELECT fingerprint FROM transactions WHERE account_id = ? AND fingerprint IS NOT NULL',
          [accountId]))
        r['fingerprint'] as String
    };
    final seen = <String, int>{};
    var added = 0, duplicates = 0;
    db.execute('BEGIN');
    try {
      for (final row in rows) {
        final key = '${isoDate(row.date)}|${row.amount}|${row.description.toLowerCase()}';
        final n = seen[key] = (seen[key] ?? 0) + 1;
        final fp = fingerprint(accountId, row.date, row.amount, row.description, n);
        if (existing.contains(fp)) {
          duplicates++;
          continue;
        }
        int? cat;
        try {
          cat = categoryFor(row.description);
        } on FormatException {
          cat = null; // a rule with an invalid pattern
        }
        db.execute(
            'INSERT INTO transactions (account_id, txn_date, amount, kind, description, '
            'merchant, category_id, category_source, fingerprint, cleared, reviewed) '
            'VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, 1, 0)',
            [
              accountId, isoDate(row.date), row.amount,
              row.amount < 0 ? 'expense' : 'income', row.description, cat,
              cat == null ? null : 'rule', fp,
            ]);
        added++;
      }
      db.execute('COMMIT');
    } catch (_) {
      db.execute('ROLLBACK');
      rethrow;
    }
    return (added: added, duplicates: duplicates);
  }

  // --- goals, bills, investments, debts (same rules as on the PC) ------
  List<Goal> goals() {
    final fx = Fx(db);
    final today = isoDate(DateTime.now());
    final bal = {for (final a in accounts(includeArchived: true)) a.id: a};
    final out = <Goal>[];
    for (final r in db.select(
        'SELECT * FROM savings_goals ORDER BY priority, name COLLATE NOCASE')) {
      final cur = r['currency'] as String;
      final manual = r['saved_amount'] as int;
      var saved = manual;
      final acc = bal[r['account_id']];
      if (acc != null) {
        final rate = fx.rate(acc.currency, cur, today);
        if (rate != null) saved = (acc.balance * rate).round();
      }
      final td = r['target_date'] as String?;
      out.add(Goal(r['id'] as int, r['name'] as String, cur,
          r['target_amount'] as int, saved,
          td == null ? null : DateTime.parse(td), acc?.id, manual,
          r['notes'] as String?));
    }
    return out;
  }

  void saveGoal({int? id, required String name, required int target,
      required String currency, DateTime? targetDate, int? accountId,
      int saved = 0, String? notes}) {
    final args = [name.trim(), target, currency,
      targetDate == null ? null : isoDate(targetDate), accountId, saved,
      (notes?.trim().isEmpty ?? true) ? null : notes!.trim()];
    if (id == null) {
      db.execute(
          'INSERT INTO savings_goals (name, target_amount, currency, '
          'target_date, account_id, saved_amount, notes, priority, created_at) '
          "VALUES (?, ?, ?, ?, ?, ?, ?, 0, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
          args);
    } else {
      db.execute(
          'UPDATE savings_goals SET name = ?, target_amount = ?, currency = ?, '
          'target_date = ?, account_id = ?, saved_amount = ?, notes = ? '
          'WHERE id = ?', [...args, id]);
    }
  }

  void deleteGoal(int id) =>
      db.execute('DELETE FROM savings_goals WHERE id = ?', [id]);

  List<Bill> bills({bool activeOnly = false}) {
    DateTime? d(Object? v) => v == null ? null : DateTime.parse(v as String);
    return [
      for (final r in db.select(
          'SELECT * FROM recurring_items '
          '${activeOnly ? 'WHERE is_active = 1 ' : ''}'
          'ORDER BY name COLLATE NOCASE'))
        Bill(r['id'] as int, r['name'] as String, r['account_id'] as int,
            r['category_id'] as int?, r['amount'] as int,
            r['frequency'] as String, d(r['start_date'])!, d(r['end_date']),
            (r['is_active'] as int) != 0, d(r['last_posted']))
    ];
  }

  /// Bills and income due within [days] days, soonest first.
  List<(Bill, DateTime)> upcoming({int days = 30}) {
    final today = DateTime.now();
    final from = DateTime(today.year, today.month, today.day);
    final to = from.add(Duration(days: days));
    final out = <(Bill, DateTime)>[];
    for (final b in bills(activeOnly: true)) {
      for (final d in b.occurrences(from, to)) {
        if (b.lastPosted != null && !d.isAfter(b.lastPosted!)) continue;
        out.add((b, d));
      }
    }
    out.sort((a, b) => a.$2.compareTo(b.$2));
    return out;
  }

  void saveBill({int? id, required String name, required int accountId,
      int? categoryId, required int amount, required String frequency,
      required DateTime start, int remindDays = 3}) {
    final args = [name.trim(), accountId, categoryId, amount, frequency,
      isoDate(start)];
    if (id == null) {
      db.execute(
          'INSERT INTO recurring_items (name, account_id, category_id, amount, '
          'frequency, start_date, is_active, auto_post, remind_days) '
          'VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)', [...args, remindDays]);
    } else {
      db.execute(
          'UPDATE recurring_items SET name = ?, account_id = ?, '
          'category_id = ?, amount = ?, frequency = ?, start_date = ? '
          'WHERE id = ?', [...args, id]);
    }
  }

  void deleteBill(int id) =>
      db.execute('DELETE FROM recurring_items WHERE id = ?', [id]);

  /// Records the bill due on [due] as a transaction and moves it on.
  void payBill(Bill b, DateTime due) {
    saveTransaction(
        accountId: b.accountId, date: DateTime.now(), amount: b.amount,
        kind: b.amount > 0 ? 'income' : 'expense', payee: b.name,
        categoryId: b.categoryId);
    db.execute('UPDATE recurring_items SET last_posted = ? WHERE id = ?',
        [isoDate(due), b.id]);
  }

  List<Holding> holdings() {
    final out = <Holding>[];
    for (final h in db.select(
        'SELECT * FROM holdings ORDER BY name COLLATE NOCASE')) {
      final id = h['id'] as int;
      var qty = 0.0, cost = 0.0, div = 0.0;
      for (final t in db.select(
          'SELECT trade_type, quantity, price, fees, cash_amount '
          'FROM investment_trades WHERE holding_id = ? '
          'ORDER BY trade_date, id', [id])) {
        final q = (t['quantity'] as int) / 1e8;
        final p = (t['price'] as int) / 1e6;
        final fees = (t['fees'] as int) / 100;
        switch (t['trade_type']) {
          case 'buy':
            qty += q;
            cost += q * p + fees;
          case 'sell':
            if (qty > 0) cost -= cost * (q / qty).clamp(0.0, 1.0);
            qty -= q;
          case 'dividend':
            div += ((t['cash_amount'] as int?) ?? 0) / 100;
        }
      }
      final last = db.select(
          'SELECT price, price_date FROM asset_prices WHERE holding_id = ? '
          'ORDER BY price_date DESC LIMIT 1', [id]);
      out.add(Holding(id, h['account_id'] as int, h['symbol'] as String,
          h['name'] as String, h['asset_class'] as String,
          h['currency'] as String, qty, (cost * 100).round(),
          last.isEmpty ? null : (last.first['price'] as int) / 1e6,
          last.isEmpty ? null
              : DateTime.parse(last.first['price_date'] as String),
          (div * 100).round()));
    }
    return out;
  }

  List<Debt> debts() {
    final terms = {
      for (final r in db.select('SELECT * FROM debt_terms'))
        r['account_id'] as int: r
    };
    return [
      for (final a in accounts())
        if (a.type == 'loan' || a.type == 'credit_card' ||
            terms.containsKey(a.id))
          if (a.balance < 0)
            Debt(a, ((terms[a.id]?['apr'] as int?) ?? 0) / 10000,
                (terms[a.id]?['min_payment'] as int?) ?? 0)
    ];
  }

  void deleteTransaction(int id) =>
      db.execute('DELETE FROM transactions WHERE id = ?', [id]);

  /// Income and spending of [month] in the base currency (transfers left out).
  /// Totals for one month, in the base currency (see [MonthSummary]).
  MonthSummary monthSummary(DateTime month) {
    month = monthStart(month);
    final out = MonthSummary(month);
    final fx = Fx(db);
    final base = baseCurrency;
    final rows = db.select(
        'SELECT t.amount, t.txn_date, t.kind, t.description, t.merchant, '
        't.recurring_id, a.currency, a.type, r.name AS bill, '
        'coalesce(p.name, c.name) AS top '
        'FROM transactions t JOIN accounts a ON a.id = t.account_id '
        'LEFT JOIN categories c ON c.id = t.category_id '
        'LEFT JOIN categories p ON p.id = c.parent_id '
        'LEFT JOIN recurring_items r ON r.id = t.recurring_id '
        'WHERE t.txn_date >= ? AND t.txn_date < ?',
        [isoDate(month), isoDate(addMonths(month, 1))]);
    final expenses = <(String, int, DateTime)>[];
    for (final r in rows) {
      final day = r['txn_date'] as String;
      final rate = fx.rate(r['currency'] as String, base, day);
      if (rate == null) {
        out.missingFx.add(r['currency'] as String);
        continue;
      }
      final v = ((r['amount'] as int) * rate).round();
      final type = r['type'] as String;
      if (r['kind'] == 'transfer') {
        if (v <= 0) continue;
        if (type == 'credit_card' || type == 'loan') out.debtPayments += v;
        if (type == 'savings' || type == 'investment') out.saved += v;
        continue;
      }
      if (v > 0) {
        out.income += v;
        continue;
      }
      final date = DateTime.parse(day);
      out.spent -= v;
      out.daily[date.day - 1] -= v;
      final top = r['top'] as String? ?? '';
      out.categories[top] = (out.categories[top] ?? 0) - v;
      final merchant = r['merchant'] as String?;
      final title = (merchant?.isNotEmpty ?? false)
          ? merchant!
          : (r['description'] as String).isEmpty
              ? '—'
              : r['description'] as String;
      if (r['recurring_id'] != null) {
        out.bills -= v;
        out.billsPaid.add((r['bill'] as String? ?? title, -v, date));
      }
      expenses.add((title, -v, date));
    }
    expenses.sort((a, b) => b.$2.compareTo(a.$2));
    out.biggest.addAll(expenses.take(5));
    out.billsPaid.sort((a, b) => a.$3.compareTo(b.$3));
    return out;
  }

  /// The month of the oldest transaction, or this month when there is none.
  DateTime firstMonth() {
    final r = db.select('SELECT min(txn_date) AS d FROM transactions').first;
    final d = r['d'] as String?;
    return monthStart(d == null ? DateTime.now() : DateTime.parse(d));
  }

  (int, int) monthTotals(DateTime month) {
    final fx = Fx(db);
    final from = isoDate(monthStart(month));
    final to = isoDate(addMonths(month, 1));
    var income = 0.0, spent = 0.0;
    for (final r in db.select(
        'SELECT t.amount, t.txn_date, a.currency FROM transactions t '
        'JOIN accounts a ON a.id = t.account_id '
        "WHERE t.kind <> 'transfer' AND t.txn_date >= ? AND t.txn_date < ?",
        [from, to])) {
      final rate = fx.rate(r['currency'] as String, baseCurrency,
          r['txn_date'] as String);
      if (rate == null) continue;
      final v = (r['amount'] as int) * rate;
      if (v > 0) {
        income += v;
      } else {
        spent += v;
      }
    }
    return (income.round(), spent.round());
  }

  /// Total of the liquid accounts in the base currency.
  int cash() {
    final fx = Fx(db);
    final today = isoDate(DateTime.now());
    var total = 0.0;
    for (final a in accounts().where((a) => a.liquid)) {
      total += a.balance * (fx.rate(a.currency, baseCurrency, today) ?? 0);
    }
    return total.round();
  }

  // --- envelopes (same rules as backend/app/services/envelope.py) -------
  EnvelopeMonth envelopeMonth(DateTime month) {
    month = monthStart(month);
    final base = baseCurrency;
    final fx = Fx(db);
    final missing = <String>{};
    final cats = {for (final c in categories(kind: 'expense')) c.id: c};
    final allKinds = {
      for (final r in db.select('SELECT id, kind FROM categories'))
        r['id'] as int: r['kind'] as String
    };
    final activity = <(int, DateTime), int>{};
    final assigned = <(int, DateTime), int>{};
    final flow = <DateTime, int>{};
    final liquid = {
      for (final a in db.select(
          'SELECT id, currency, opening_balance, opening_date FROM accounts '
          'WHERE type IN (${liquidTypes.map((_) => '?').join(', ')})',
          liquidTypes))
        a['id'] as int: a
    };
    for (final a in liquid.values) {
      final day = a['opening_date'] as String;
      final rate = fx.rate(a['currency'] as String, base, day);
      if (rate == null) {
        missing.add(a['currency'] as String);
        continue;
      }
      final m = monthStart(DateTime.parse(day));
      flow[m] = (flow[m] ?? 0) + ((a['opening_balance'] as int) * rate).round();
    }
    final splits = <int, List<(int?, int)>>{};
    for (final s in db.select(
        'SELECT transaction_id, category_id, amount FROM transaction_splits')) {
      splits.putIfAbsent(s['transaction_id'] as int, () => [])
          .add((s['category_id'] as int?, s['amount'] as int));
    }
    for (final t in db.select(
        'SELECT id, account_id, txn_date, amount, kind, category_id FROM transactions')) {
      final acc = liquid[t['account_id']];
      if (acc == null) continue;
      final day = t['txn_date'] as String;
      final rate = fx.rate(acc['currency'] as String, base, day);
      if (rate == null) {
        missing.add(acc['currency'] as String);
        continue;
      }
      final m = monthStart(DateTime.parse(day));
      flow[m] = (flow[m] ?? 0) + ((t['amount'] as int) * rate).round();
      if (t['kind'] == 'transfer') continue;
      final parts = splits[t['id']] ??
          [(t['category_id'] as int?, t['amount'] as int)];
      for (final (catId, amount) in parts) {
        final kind = catId == null ? null : allKinds[catId];
        if (kind != null && kind != 'expense') continue;
        if (kind == null && t['kind'] != 'expense') continue;
        final key = (kind == null ? 0 : catId!, m);
        activity[key] = (activity[key] ?? 0) + (amount * rate).round();
      }
    }
    for (final a in db.select(
        'SELECT category_id, month, amount FROM budget_assignments')) {
      final key = (a['category_id'] as int,
          monthStart(DateTime.parse(a['month'] as String)));
      assigned[key] = (assigned[key] ?? 0) + (a['amount'] as int);
    }
    final targets = {
      for (final r in db.select(
          'SELECT category_id, kind, amount, due_date FROM budget_targets'))
        r['category_id'] as int: r
    };
    final keys = {...cats.keys, 0}.toList()..sort();
    final months = [...flow.keys, ...assigned.keys.map((k) => k.$2)]..sort();
    var m = months.isEmpty || months.first.isAfter(month) ? month : months.first;
    final carry = {for (final k in keys) k: 0};
    final available = {for (final k in keys) k: 0};
    while (!m.isAfter(month)) {
      for (final k in keys) {
        available[k] =
            carry[k]! + (assigned[(k, m)] ?? 0) + (activity[(k, m)] ?? 0);
      }
      if (m.isBefore(month)) {
        for (final k in keys) {
          carry[k] = available[k]! > 0 ? available[k]! : 0;
        }
      }
      m = addMonths(m, 1);
    }
    final future = assigned.entries
        .where((e) => e.key.$2.isAfter(month))
        .fold<int>(0, (s, e) => s + e.value);
    var cashAt = 0;
    var running = 0;
    for (final fm in flow.keys.toList()..sort()) {
      running += flow[fm]!;
      if (!fm.isAfter(month)) cashAt = running;
    }
    final ready =
        cashAt - available.values.fold<int>(0, (s, v) => s + v) - future;
    final rows = <EnvelopeRow>[];
    for (final k in keys) {
      final cat = cats[k];
      if (k == 0 && (activity[(0, month)] ?? 0) == 0 && available[0] == 0) {
        continue;
      }
      rows.add(EnvelopeRow(cat, assigned[(k, month)] ?? 0,
          activity[(k, month)] ?? 0, available[k]!,
          _need(targets[k], month, carry[k]!)));
    }
    rows.sort((a, b) => (a.category?.label ?? '~')
        .toLowerCase()
        .compareTo((b.category?.label ?? '~').toLowerCase()));
    return EnvelopeMonth(month, base, ready, rows, missing);
  }

  int _need(Row? target, DateTime month, int carryIn) {
    if (target == null) return 0;
    final amount = target['amount'] as int;
    switch (target['kind']) {
      case 'monthly':
        return amount;
      case 'yearly':
        return (amount / 12).round();
      case 'weekly':
        final due = target['due_date'] as String?;
        final weekday = due == null ? DateTime.monday : DateTime.parse(due).weekday;
        final days = addMonths(month, 1).difference(month).inDays;
        var count = 0;
        for (var d = 0; d < days; d++) {
          if (month.add(Duration(days: d)).weekday == weekday) count++;
        }
        return amount * count;
      default:
        final due = target['due_date'] == null
            ? month
            : monthStart(DateTime.parse(target['due_date'] as String));
        var left = (due.year - month.year) * 12 + due.month - month.month + 1;
        if (left < 1) left = 1;
        final remaining = amount - carryIn > 0 ? amount - carryIn : 0;
        return (remaining / left).round();
    }
  }

  void setAssigned(int categoryId, DateTime month, int amount) {
    final m = isoDate(monthStart(month));
    final existing = db.select(
        'SELECT id FROM budget_assignments WHERE category_id = ? AND month = ?',
        [categoryId, m]);
    if (existing.isEmpty) {
      if (amount != 0) {
        db.execute(
            'INSERT INTO budget_assignments (category_id, month, amount) '
            'VALUES (?, ?, ?)',
            [categoryId, m, amount]);
      }
    } else {
      db.execute('UPDATE budget_assignments SET amount = ? WHERE id = ?',
          [amount, existing.first['id']]);
    }
  }
}
