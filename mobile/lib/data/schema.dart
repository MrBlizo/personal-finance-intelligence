// What the app knows about the tables it shares with Personal Finance on Windows.
//
// `assets/db/schema.json` and `assets/db/schema.sql` are generated from the
// PC's models (backend/app/services/mobile_schema.py), so both sides store
// the same raw values: money as scaled integers, dates as text.
import 'dart:convert';

class SchemaMeta {
  SchemaMeta(Map<String, dynamic> json)
      : format = json['format'] as int,
        schema = json['schema'] as int,
        tables = List<String>.from(json['tables'] as List),
        hasId = Map<String, bool>.from(json['has_id'] as Map),
        columns = (json['columns'] as Map).map(
            (k, v) => MapEntry(k as String, List<String>.from(v as List))),
        fks = (json['fks'] as Map).map((k, v) => MapEntry(
            k as String,
            (v as Map).map((c, ref) => MapEntry(c as String,
                ref == null ? null : List<String>.from(ref as List))))),
        unique = (json['unique'] as Map).map((k, v) => MapEntry(
            k as String,
            (v as List).map((key) => List<String>.from(key as List)).toList())),
        money = (json['money'] as Map).map(
            (k, v) => MapEntry(k as String, Map<String, int>.from(v as Map))),
        defaults = (json['defaults'] as Map).map((k, v) =>
            MapEntry(k as String, Map<String, Object?>.from(v as Map)));

  factory SchemaMeta.parse(String text) =>
      SchemaMeta(jsonDecode(text) as Map<String, dynamic>);

  final int format;
  final int schema;

  /// Synced tables, parents before children.
  final List<String> tables;
  final Map<String, bool> hasId;
  final Map<String, List<String>> columns;

  /// Foreign-key column -> [table, column], or null when the referenced
  /// table is not synced (such values travel as null).
  final Map<String, Map<String, List<String>?>> fks;

  /// Natural keys used to merge rows created on two devices.
  final Map<String, List<List<String>>> unique;

  /// Money columns and their scale (number of decimals stored).
  final Map<String, Map<String, int>> money;

  /// Python-side defaults, as raw column values.
  final Map<String, Map<String, Object?>> defaults;

  /// The exchanged columns of [table] (no local id, uid or updated_at).
  List<String> syncColumns(String table) => columns[table]!
      .where((c) =>
          c != 'uid' &&
          c != 'updated_at' &&
          !(c == 'id' && (hasId[table] ?? false)))
      .toList();
}
