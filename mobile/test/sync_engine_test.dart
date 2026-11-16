// The phone's sync engine against itself (two devices, one folder).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pfi/data/db.dart';
import 'package:pfi/data/repo.dart';
import 'package:pfi/sync/crypto.dart';
import 'package:pfi/sync/engine.dart';
import 'package:pfi/sync/store.dart';

import 'support.dart';

class Device {
  Device(this.name) : app = memoryDb() {
    engine = SyncEngine(app.db, app.meta);
    repo = Repo(app);
  }
  final String name;
  final AppDatabase app;
  late final SyncEngine engine;
  late final Repo repo;
  late List<int> key;

  Future<void> join(SyncStore store) async =>
      key = await engine.setup(store, 'correct horse', deviceName: name, iterations: 1000);
  Future<SyncResult> run(SyncStore store) => engine.run(store, key);
}

Future<void> tick() => Future.delayed(const Duration(milliseconds: 20));

void main() {
  late Directory tmp;
  late FolderStore store;
  late Device a, b;

  setUp(() async {
    tmp = Directory.systemTemp.createTempSync('pfi-sync-');
    store = FolderStore('${tmp.path}/PFI Sync');
    a = Device('phone A');
    b = Device('phone B');
    a.app.seed('CHF');
    b.app.seed('CHF');
    await a.join(store);
    await b.join(store);
  });

  tearDown(() {
    a.app.close();
    b.app.close();
    tmp.deleteSync(recursive: true);
  });

  test('crypto round trip and wrong key', () async {
    final key = List.filled(32, 7);
    final blob = await seal(key, 'dev/00000001', {'x': 'é'});
    expect(await unseal(key, 'dev/00000001', blob), {'x': 'é'});
    expect(() => unseal(List.filled(32, 8), 'dev/00000001', blob),
        throwsA(isA<SyncException>()));
    expect(() => unseal(key, 'dev/00000002', blob), throwsA(isA<SyncException>()));
  });

  test('wrong passphrase is refused', () async {
    final c = Device('C');
    expect(() => c.engine.setup(store, 'wrong passphrase', iterations: 1000),
        throwsA(isA<SyncException>()));
  });

  test('two devices converge and do not echo', () async {
    final acc = a.repo.addAccount('Cash', 'cash', 'CHF', 5000, DateTime(2026, 1, 1));
    final groceries = a.repo.categories(kind: 'expense').firstWhere((c) => c.name == 'Groceries');
    a.repo.saveTransaction(
        accountId: acc, date: DateTime(2026, 11, 10), amount: -4250,
        kind: 'expense', payee: 'Migros', categoryId: groceries.id);
    final sent = await a.run(store);
    expect(sent.sent, greaterThan(0));
    final got = await b.run(store);
    expect(got.pending, 0);
    expect(got.problems, isEmpty);
    final txns = b.repo.transactions();
    expect(txns.single.title, 'Migros');
    expect(txns.single.amount, -4250);
    expect(txns.single.categoryName, 'Groceries');
    // Both devices started with the same default categories: they are
    // merged once (no duplicates), after which nothing travels back.
    await a.run(store);
    expect(a.repo.categories().length, b.repo.categories().length);
    expect((await b.run(store)).sent, 0);
    final again = await a.run(store);
    expect(again.received, 0);
    expect(again.sent, 0);
  });

  test('edits, deletes and last writer wins', () async {
    final acc = a.repo.addAccount('Card', 'credit_card', 'CHF', 0, DateTime(2026, 1, 1));
    a.repo.saveTransaction(accountId: acc, date: DateTime(2026, 11, 1), amount: -500,
        kind: 'expense', payee: 'Bus');
    a.repo.saveTransaction(accountId: acc, date: DateTime(2026, 11, 2), amount: -900,
        kind: 'expense', payee: 'Lunch');
    await a.run(store);
    await b.run(store);
    await tick();
    final bus = a.repo.transactions().firstWhere((t) => t.title == 'Bus');
    a.repo.saveTransaction(id: bus.id, accountId: acc, date: bus.date, amount: -500,
        kind: 'expense', payee: 'Bus (A)');
    await tick();
    final busB = b.repo.transactions().firstWhere((t) => t.title == 'Bus');
    b.repo.saveTransaction(id: busB.id, accountId: busB.accountId, date: busB.date,
        amount: -550, kind: 'expense', payee: 'Bus (B, later)');
    b.repo.deleteTransaction(b.repo.transactions().firstWhere((t) => t.title == 'Lunch').id);
    await a.run(store);
    await b.run(store);
    await a.run(store);
    for (final d in [a, b]) {
      final list = d.repo.transactions();
      expect(list.map((t) => t.title), ['Bus (B, later)'], reason: d.name);
      expect(list.single.amount, -550);
    }
  });

  test('same account created on both devices is merged', () async {
    final accA = a.repo.addAccount('Wallet', 'cash', 'CHF', 0, DateTime(2026, 1, 1));
    final accB = b.repo.addAccount('Wallet', 'cash', 'CHF', 0, DateTime(2026, 1, 1));
    b.repo.saveTransaction(accountId: accB, date: DateTime(2026, 11, 3), amount: -300,
        kind: 'expense', payee: 'Bread');
    await b.run(store);
    await a.run(store);
    a.repo.saveTransaction(accountId: accA, date: DateTime(2026, 11, 4), amount: -400,
        kind: 'expense', payee: 'Milk');
    await a.run(store);
    await b.run(store);
    for (final d in [a, b]) {
      expect(d.repo.accounts().where((x) => x.name == 'Wallet').length, 1);
      expect(d.repo.transactions().map((t) => t.title).toSet(), {'Bread', 'Milk'});
    }
  });

  test('envelope month adds up', () async {
    final acc = a.repo.addAccount('Bank', 'checking', 'CHF', 100000, DateTime(2026, 11, 1));
    final food = a.repo.categories(kind: 'expense').firstWhere((c) => c.name == 'Groceries');
    a.repo.setAssigned(food.id, DateTime(2026, 11, 1), 30000);
    a.repo.saveTransaction(accountId: acc, date: DateTime(2026, 11, 5), amount: -12000,
        kind: 'expense', payee: 'Coop', categoryId: food.id);
    final env = a.repo.envelopeMonth(DateTime(2026, 11, 15));
    final row = env.rows.firstWhere((r) => r.category?.id == food.id);
    expect(row.assigned, 30000);
    expect(row.activity, -12000);
    expect(row.available, 18000);
    expect(env.readyToAssign, 100000 - 12000 - 18000);
    final dec = a.repo.envelopeMonth(DateTime(2026, 12, 1));
    expect(dec.rows.firstWhere((r) => r.category?.id == food.id).available, 18000);
  });

  test('normTime orders mixed precision', () {
    expect(normTime('2026-11-16 10:00:00').compareTo(normTime('2026-11-16 10:00:00.001')),
        lessThan(0));
    expect(normTime('2026-11-16T10:00:00.5+00:00'), '2026-11-16 10:00:00.500000');
  });
}
