// The phone joins a sync folder written by PFI on Windows (Python) and
// writes changes the PC must read. The folder is prepared by
// backend/tools/sync_fixture.py (see .github/workflows/mobile.yml).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/data/repo.dart';
import 'package:pfi/sync/engine.dart';
import 'package:pfi/sync/store.dart';

import 'support.dart';

void main() {
  final fixture = Platform.environment['PFI_SYNC_FIXTURE'];
  test('phone reads the PC and writes back', () async {
    final expected = jsonDecode(File('$fixture/expected.json').readAsStringSync())
        as Map<String, dynamic>;
    final app = memoryDb();
    final engine = SyncEngine(app.db, app.meta);
    final repo = Repo(app);
    final store = FolderStore('$fixture/cloud');
    final key = await engine.setup(store, expected['passphrase'] as String,
        deviceName: 'CI phone');
    final res = await engine.run(store, key);
    expect(res.problems, isEmpty);
    expect(res.pending, 0);
    int count(String table) =>
        app.db.select('SELECT count(*) AS n FROM $table').first['n'] as int;
    expect(count('accounts'), expected['accounts']);
    expect(count('categories'), expected['categories']);
    expect(count('transactions'), expected['transactions']);
    expect(app.db.select('SELECT sum(amount) AS s FROM transactions').first['s'],
        expected['amount_sum']);
    expect(res.sent, 0, reason: 'received rows must not be sent back');

    final account = repo.accounts().firstWhere((a) => a.liquid);
    final groceries =
        repo.categories(kind: 'expense').firstWhere((c) => c.name == 'Groceries');
    repo.saveTransaction(accountId: account.id, date: DateTime.now(), amount: -1234,
        kind: 'expense', payee: 'Added on the phone', categoryId: groceries.id);
    final first = repo.transactions(limit: 20).firstWhere((t) => t.title != 'Added on the phone');
    app.db.execute("UPDATE transactions SET notes = 'edited on the phone' WHERE id = ?",
        [first.id]);
    final back = await engine.run(store, key);
    expect(back.sent, 2);
  }, skip: fixture == null ? 'PFI_SYNC_FIXTURE not set' : false);
}
