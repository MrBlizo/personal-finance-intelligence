// The phone's SQLite database: same tables as PFI on Windows.
import 'package:sqlite3/sqlite3.dart';

import 'schema.dart';

const _palette = [
  '#0072B2', '#E69F00', '#009E73', '#D55E00', '#56B4E9', '#CC79A7',
  '#F0E442', '#BE1818', '#6B7280', '#7C3AED', '#0F766E', '#9A3412'
];

/// Default categories, as PFI on Windows creates them (same names, so the
/// two lists merge when the phone and the PC sync).
const defaultCategories = <String, Map<String, List<String>>>{
  'income': {
    'Salary': [], 'Bonus': [], 'Freelance': [],
    'Investment Income': ['Dividends', 'Interest'], 'Gifts Received': [],
    'Refunds': [], 'Other Income': [],
  },
  'expense': {
    'Housing': ['Rent', 'Utilities', 'Internet & Phone', 'Household Insurance'],
    'Food': ['Groceries', 'Restaurants', 'Coffee & Snacks'],
    'Transport': ['Public Transport', 'Fuel', 'Car', 'Taxi & Rides'],
    'Health': ['Health Insurance', 'Doctor & Dentist', 'Pharmacy'],
    'Shopping': ['Clothing', 'Electronics', 'Home & Garden'],
    'Leisure': ['Entertainment', 'Subscriptions', 'Sports', 'Travel'],
    'Education': ['Courses', 'Books'],
    'Finance': ['Bank Fees', 'Taxes', 'Other Insurance'],
    'Family & Gifts': ['Gifts', 'Donations'],
    'Other Expense': [],
  },
};

class AppDatabase {
  AppDatabase._(this.db, this.meta);
  final Database db;
  final SchemaMeta meta;

  /// Opens (and if needed creates) the database at [path]; use
  /// ':memory:' in tests.
  static AppDatabase open(String path, String schemaSql, SchemaMeta meta) {
    final db = path == ':memory:' ? sqlite3.openInMemory() : sqlite3.open(path);
    db.execute('PRAGMA foreign_keys = ON');
    final version = db.select('PRAGMA user_version').first.values.first as int;
    if (version == 0) {
      db.execute(schemaSql);
      db.execute('PRAGMA user_version = ${meta.schema}');
    }
    return AppDatabase._(db, meta);
  }

  String? setting(String key) {
    final r = db.select('SELECT value FROM settings WHERE key = ?', [key]);
    return r.isEmpty ? null : r.first['value'] as String?;
  }

  void setSetting(String key, String value) => db.execute(
      'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
      [key, value]);

  bool get isEmpty =>
      (db.select('SELECT count(*) AS n FROM categories').first['n'] as int) == 0 &&
      (db.select('SELECT count(*) AS n FROM accounts').first['n'] as int) == 0;

  /// Starts a fresh budget: default categories and the currency.
  void seed(String baseCurrency) {
    setSetting('base_currency', baseCurrency);
    var i = 0;
    db.execute('BEGIN');
    try {
      defaultCategories.forEach((kind, parents) {
        parents.forEach((name, children) {
          final color = _palette[i++ % _palette.length];
          db.execute(
              'INSERT OR IGNORE INTO categories (name, kind, color) VALUES (?, ?, ?)',
              [name, kind, color]);
          final parentId = db.select(
              'SELECT id FROM categories WHERE name = ? AND kind = ?',
              [name, kind]).first['id'];
          for (final child in children) {
            db.execute(
                'INSERT OR IGNORE INTO categories (name, kind, parent_id, color) '
                'VALUES (?, ?, ?, ?)',
                [child, kind, parentId, color]);
          }
        });
      });
      db.execute('COMMIT');
    } catch (_) {
      db.execute('ROLLBACK');
      rethrow;
    }
  }

  void close() => db.dispose();
}
