// The sync engine: the same rules as backend/app/services/sync.py.
//
// Receive: apply the other devices' new change files (later updated_at
// wins, deletions as tombstones, rows created twice are merged by their
// natural key, children wait for their parents). Send: write this
// device's unsent changes as the next numbered, encrypted file.
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:sqlite3/sqlite3.dart';

import '../data/schema.dart';
import 'crypto.dart';
import 'store.dart';

const syncFormat = 1;
const pbkdf2Iterations = 600000;
const chunkSize = 2000;
const checkText = 'PFI-SYNC';

String nowUtc() {
  final d = DateTime.now().toUtc();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${d.year.toString().padLeft(4, '0')}-${two(d.month)}-${two(d.day)} '
      '${two(d.hour)}:${two(d.minute)}:${two(d.second)}.'
      '${d.millisecond.toString().padLeft(3, '0')}';
}

/// A sortable form of a stored time (fraction padded to 6 digits).
String normTime(Object? value) {
  if (value == null) return '';
  var s = value.toString().replaceAll('T', ' ');
  s = s.replaceAll(RegExp(r'(\+00:00|Z)$'), '');
  final dot = s.indexOf('.');
  final head = dot < 0 ? s : s.substring(0, dot);
  final frac = dot < 0 ? '' : s.substring(dot + 1);
  final h = head.length > 19 ? head.substring(0, 19) : head;
  return '$h.${'${frac}000000'.substring(0, 6)}';
}

String _aad(String device, int number) =>
    '$device/${number.toString().padLeft(8, '0')}';

String _randomHex(int bytes) {
  final r = Random.secure();
  return List.generate(bytes, (_) => r.nextInt(256))
      .map((b) => b.toRadixString(16).padLeft(2, '0'))
      .join();
}

class _Missing implements Exception {}

class SyncResult {
  SyncResult(this.sent, this.received, this.pending, this.problems);
  final int sent;
  final int received;
  final int pending;
  final List<String> problems;
}

class SyncEngine {
  SyncEngine(this.db, this.meta);
  final Database db;
  final SchemaMeta meta;

  // --- state ---------------------------------------------------------
  String? getState(String key) {
    final r = db.select('SELECT value FROM sync_state WHERE key = ?', [key]);
    return r.isEmpty ? null : r.first['value'] as String;
  }

  void setState(String key, String? value) {
    if (value == null) {
      db.execute('DELETE FROM sync_state WHERE key = ?', [key]);
    } else {
      db.execute('INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)',
          [key, value]);
    }
  }

  void _seen(String table, String uid, String u) => db.execute(
      'INSERT OR REPLACE INTO sync_seen (table_name, uid, u) VALUES (?, ?, ?)',
      [table, uid, u]);

  String deviceId() {
    var id = getState('device_id');
    if (id == null) {
      id = _randomHex(8);
      setState('device_id', id);
    }
    return id;
  }

  // --- setup ---------------------------------------------------------
  /// Creates or joins the sync folder; returns the derived key.
  Future<Uint8List> setup(SyncStore store, String passphrase,
      {String? deviceName, int iterations = pbkdf2Iterations}) async {
    if (passphrase.length < 8) {
      throw SyncException('Choose a sync passphrase of at least 8 characters.');
    }
    final manifest = await store.readManifest();
    late Uint8List key;
    if (manifest == null) {
      final salt = Uint8List.fromList(
          List.generate(16, (_) => Random.secure().nextInt(256)));
      key = await deriveKey(passphrase, salt, iterations);
      await store.writeManifest({
        'app': 'PFI',
        'format': syncFormat,
        'kdf': {
          'alg': 'pbkdf2-sha256',
          'iterations': iterations,
          'salt': base64.encode(salt)
        },
        'check': base64.encode(await seal(key, 'check', {'check': checkText})),
      });
    } else {
      if (manifest['app'] != 'PFI' || manifest['kdf'] == null) {
        throw SyncException('This folder is not a PFI sync folder.');
      }
      if ((manifest['format'] as int? ?? 0) > syncFormat) {
        throw SyncException('This sync folder was created by a newer version '
            'of PFI. Update the app first.');
      }
      final kdf = manifest['kdf'] as Map<String, dynamic>;
      key = await deriveKey(passphrase, base64.decode(kdf['salt'] as String),
          kdf['iterations'] as int);
      var ok = false;
      try {
        final check = await unseal(
            key, 'check', base64.decode(manifest['check'] as String));
        ok = check['check'] == checkText;
      } on SyncException {
        ok = false;
      }
      if (!ok) {
        throw SyncException('The passphrase does not match the one used to '
            'create this sync folder. Enter the passphrase from your other '
            'device.');
      }
    }
    final where = store.label;
    if (getState('folder') != where) {
      db.execute('DELETE FROM sync_seen');
      db.execute('DELETE FROM sync_aliases');
      db.execute('DELETE FROM sync_pending');
      db.execute("DELETE FROM sync_state WHERE key LIKE 'applied:%' "
          "OR key LIKE 'device:%' OR key IN ('next_seq', 'device_id')");
    }
    deviceId();
    if (deviceName != null && deviceName.trim().isNotEmpty) {
      setState('device_name', deviceName.trim());
    }
    setState('folder', where);
    setState('enabled', '1');
    return key;
  }

  // --- export --------------------------------------------------------
  final Map<String, Map<Object?, String>> _uidCache = {};

  String? _uidOf(String table, String col, Object? value) {
    if (value == null) return null;
    final cache = _uidCache.putIfAbsent('$table.$col', () {
      final m = <Object?, String>{};
      for (final r in db.select('SELECT $col AS k, uid FROM $table')) {
        final uid = r['uid'];
        if (uid != null) m[r['k']] = uid as String;
      }
      return m;
    });
    return cache[value];
  }

  List<Map<String, Object?>> collectChanges() {
    _uidCache.clear();
    final out = <Map<String, Object?>>[];
    for (final table in meta.tables) {
      final cols = meta.syncColumns(table);
      final fks = meta.fks[table]!;
      final rows = db.select(
          'SELECT t.* FROM $table t LEFT JOIN sync_seen s '
          'ON s.table_name = ? AND s.uid = t.uid '
          'WHERE t.uid IS NOT NULL AND t.updated_at IS NOT NULL AND '
          '(s.u IS NULL OR s.u <> CAST(t.updated_at AS TEXT)) '
          'ORDER BY t.rowid',
          [table]);
      for (final r in rows) {
        final row = <String, Object?>{};
        for (final c in cols) {
          Object? v = r[c];
          if (fks.containsKey(c)) {
            final ref = fks[c];
            v = ref == null ? null : _uidOf(ref[0], ref[1], v);
          }
          row[c] = v;
        }
        out.add({
          't': table,
          'uid': r['uid'],
          'u': r['updated_at'].toString(),
          'row': row
        });
      }
    }
    final order = {for (var i = 0; i < meta.tables.length; i++) meta.tables[i]: i};
    final dels = db.select(
        'SELECT d.table_name, d.uid, max(d.deleted_at) AS deleted_at '
        'FROM sync_tombstones d LEFT JOIN sync_seen s '
        'ON s.table_name = d.table_name AND s.uid = d.uid '
        'GROUP BY d.table_name, d.uid '
        "HAVING max(s.u) IS NULL OR max(s.u) <> 'del:' || max(d.deleted_at)")
        .where((r) => order.containsKey(r['table_name']))
        .toList()
      ..sort((a, b) => order[b['table_name']]!.compareTo(order[a['table_name']]!));
    for (final r in dels) {
      out.add({
        't': r['table_name'],
        'uid': r['uid'],
        'del': r['deleted_at'].toString()
      });
    }
    return out;
  }

  // --- import --------------------------------------------------------
  /// (rowid, local uid) of the row known as [uid] here.
  (int, String)? resolve(String table, String uid) {
    var r = db.select('SELECT rowid AS rid FROM $table WHERE uid = ?', [uid]);
    if (r.isNotEmpty) return (r.first['rid'] as int, uid);
    final a = db.select(
        'SELECT uid FROM sync_aliases WHERE table_name = ? AND alias_uid = ?',
        [table, uid]);
    if (a.isEmpty) return null;
    final local = a.first['uid'] as String;
    r = db.select('SELECT rowid AS rid FROM $table WHERE uid = ?', [local]);
    return r.isEmpty ? null : (r.first['rid'] as int, local);
  }

  Object? _localOf(String table, String col, String uid) {
    final found = resolve(table, uid);
    if (found == null) throw _Missing();
    return db.select('SELECT $col AS v FROM $table WHERE rowid = ?',
        [found.$1]).first['v'];
  }

  Map<String, Object?> _translate(String table, Map<String, dynamic> row) {
    final fks = meta.fks[table]!;
    final out = <String, Object?>{};
    for (final c in meta.syncColumns(table)) {
      if (!row.containsKey(c)) continue;
      Object? v = row[c];
      if (fks.containsKey(c)) {
        final ref = fks[c];
        v = (v == null || ref == null) ? null : _localOf(ref[0], ref[1], v as String);
      }
      out[c] = v;
    }
    return out;
  }

  String? _localTime(String table, int rid) => db.select(
      'SELECT CAST(updated_at AS TEXT) AS u FROM $table WHERE rowid = ?',
      [rid]).first['u'] as String?;

  bool _update(String table, int rid, String localUid,
      Map<String, Object?> values, String u) {
    if (normTime(u).compareTo(normTime(_localTime(table, rid))) <= 0) {
      return false;
    }
    final cols = values.keys.toList();
    final sets = [...cols.map((c) => '$c = ?'), 'updated_at = ?'].join(', ');
    db.execute('UPDATE $table SET $sets WHERE rowid = ?',
        [...cols.map((c) => values[c]), u, rid]);
    _seen(table, localUid, u);
    return true;
  }

  bool _applyUpsert(Map<String, dynamic> rec) {
    final table = rec['t'] as String;
    final uid = rec['uid'] as String;
    final u = rec['u'] as String;
    final values =
        _translate(table, (rec['row'] as Map?)?.cast<String, dynamic>() ?? {});
    final found = resolve(table, uid);
    if (found != null) return _update(table, found.$1, found.$2, values, u);
    final deleted = db.select(
        'SELECT max(deleted_at) AS d FROM sync_tombstones '
        'WHERE table_name = ? AND uid = ?',
        [table, uid]).first['d'];
    if (deleted != null && normTime(deleted).compareTo(normTime(u)) >= 0) {
      return false;
    }
    for (final key in meta.unique[table]!) {
      if (key.any((c) => values[c] == null)) continue;
      final where = key.map((c) => '$c = ?').join(' AND ');
      final hit = db.select('SELECT rowid AS rid, uid FROM $table WHERE $where',
          [for (final c in key) values[c]]);
      if (hit.isNotEmpty) {
        final localUid = hit.first['uid'] as String;
        db.execute(
            'INSERT OR REPLACE INTO sync_aliases (table_name, alias_uid, uid) '
            'VALUES (?, ?, ?)',
            [table, uid, localUid]);
        return _update(table, hit.first['rid'] as int, localUid, values, u);
      }
    }
    final names = [...values.keys, 'uid', 'updated_at'];
    db.execute(
        'INSERT INTO $table (${names.join(', ')}) '
        'VALUES (${List.filled(names.length, '?').join(', ')})',
        [...values.values, uid, u]);
    _uidCache.removeWhere((k, _) => k.startsWith('$table.'));
    _seen(table, uid, u);
    return true;
  }

  String _lastDel(String table, String uid) => db.select(
      'SELECT max(deleted_at) AS d FROM sync_tombstones '
      'WHERE table_name = ? AND uid = ?',
      [table, uid]).first['d'].toString();

  bool _applyDelete(Map<String, dynamic> rec) {
    final table = rec['t'] as String;
    final uid = rec['uid'] as String;
    final when = rec['del'] as String;
    final found = resolve(table, uid);
    if (found == null) {
      db.execute(
          'INSERT INTO sync_tombstones (table_name, uid, deleted_at) '
          'SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM sync_tombstones '
          'WHERE table_name = ? AND uid = ?)',
          [table, uid, when, table, uid]);
      _seen(table, uid, 'del:${_lastDel(table, uid)}');
      return false;
    }
    if (normTime(_localTime(table, found.$1)).compareTo(normTime(when)) > 0) {
      return false;
    }
    db.execute('DELETE FROM $table WHERE rowid = ?', [found.$1]);
    db.execute(
        'UPDATE sync_tombstones SET deleted_at = ? '
        'WHERE table_name = ? AND uid = ?',
        [when, table, found.$2]);
    _seen(table, found.$2, 'del:$when');
    return true;
  }

  /// Merges received records; returns (changed, waiting, problems).
  (int, List<Map<String, dynamic>>, List<String>) applyChanges(
      List<Map<String, dynamic>> records) {
    final order = {for (var i = 0; i < meta.tables.length; i++) meta.tables[i]: i};
    final upserts = records
        .where((r) => !r.containsKey('del') && order.containsKey(r['t']))
        .toList()
      ..sort((a, b) => order[a['t']]!.compareTo(order[b['t']]!));
    final deletes = records
        .where((r) => r.containsKey('del') && order.containsKey(r['t']))
        .toList()
      ..sort((a, b) => order[b['t']]!.compareTo(order[a['t']]!));
    _uidCache.clear();
    var changed = 0;
    final problems = <String>[];
    var todo = upserts;
    while (todo.isNotEmpty) {
      final waiting = <Map<String, dynamic>>[];
      for (final rec in todo) {
        try {
          if (_applyUpsert(rec)) changed++;
        } on _Missing {
          waiting.add(rec);
        } on SqliteException catch (e) {
          problems.add('${rec['t']} ${rec['uid']}: ${e.message}');
        }
      }
      final stuck = waiting.length == todo.length;
      todo = waiting;
      if (stuck) break;
    }
    for (final rec in deletes) {
      if (_applyDelete(rec)) changed++;
    }
    db.execute('DELETE FROM sync_tombstones WHERE rowid NOT IN (SELECT '
        'max(rowid) FROM sync_tombstones GROUP BY table_name, uid)');
    return (changed, todo, problems);
  }

  // --- run -----------------------------------------------------------
  Future<SyncResult> run(SyncStore store, List<int> key) async {
    final me = getState('device_id');
    if (getState('enabled') != '1' || me == null) {
      throw SyncException('Sync is not set up on this device.');
    }
    if (await store.readManifest() == null) {
      throw SyncException('The sync folder no longer contains '
          '$manifestName. Set up sync again.');
    }
    // 1. receive
    final records = <Map<String, dynamic>>[
      for (final r in db.select('SELECT payload FROM sync_pending'))
        jsonDecode(r['payload'] as String) as Map<String, dynamic>
    ];
    final applied = <String, int>{};
    final names = <String, Map<String, Object?>>{};
    for (final dev in await store.devices()) {
      if (dev == me) continue;
      final last = int.parse(getState('applied:$dev') ?? '0');
      for (final n in await store.numbers(dev)) {
        if (n <= last) continue;
        final payload = await unseal(key, _aad(dev, n), await store.read(dev, n));
        if ((payload['format'] as int? ?? 1) > syncFormat) {
          throw SyncException('Another device uses a newer version of PFI. '
              'Update the app to keep syncing.');
        }
        records.addAll((payload['changes'] as List)
            .map((e) => (e as Map).cast<String, dynamic>()));
        applied[dev] = n;
        names[dev] = {'name': payload['name'] ?? dev, 'seen': payload['created']};
      }
    }
    db.execute('BEGIN');
    late (int, List<Map<String, dynamic>>, List<String>) result;
    try {
      db.execute('DELETE FROM sync_pending');
      result = applyChanges(records);
      for (final rec in result.$2) {
        db.execute('INSERT INTO sync_pending (payload, attempts) VALUES (?, 1)',
            [jsonEncode(rec)]);
      }
      applied.forEach((dev, n) => setState('applied:$dev', '$n'));
      names.forEach((dev, info) => setState('device:$dev', jsonEncode(info)));
      db.execute('COMMIT');
    } catch (_) {
      db.execute('ROLLBACK');
      rethrow;
    }
    // 2. send
    final changes = collectChanges();
    var number = int.parse(getState('next_seq') ?? '1');
    final name = getState('device_name') ?? 'Phone';
    for (var start = 0; start < changes.length; start += chunkSize) {
      final part = changes.sublist(start, min(start + chunkSize, changes.length));
      await store.write(
          me,
          number,
          await seal(key, _aad(me, number), {
            'format': syncFormat,
            'device': me,
            'name': name,
            'seq': number,
            'created': nowUtc(),
            'changes': part
          }));
      db.execute('BEGIN');
      for (final rec in part) {
        _seen(rec['t'] as String, rec['uid'] as String,
            rec.containsKey('del') ? 'del:${rec['del']}' : rec['u'] as String);
      }
      number++;
      setState('next_seq', '$number');
      db.execute('COMMIT');
    }
    final res = SyncResult(changes.length, result.$1, result.$2.length, result.$3);
    setState(
        'last_result',
        jsonEncode({
          'at': nowUtc(),
          'sent': res.sent,
          'received': res.received,
          'error': res.problems.isEmpty ? null : res.problems.take(3).join('; ')
        }));
    return res;
  }
}
