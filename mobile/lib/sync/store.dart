// Where sync files live. The phone talks to the cloud drive's web API
// (cloud.dart); this file holds the interface and a plain-folder version
// used by tests and desktop builds.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

const manifestName = 'pfi-sync.json';
final _seqName = RegExp(r'^(\d{8})\.pfisync$');
final deviceIdPattern = RegExp(r'^[0-9a-f]{16}$');

String fileName(int number) => '${number.toString().padLeft(8, '0')}.pfisync';

abstract class SyncStore {
  /// Shown in Settings, e.g. "OneDrive › Apps › PFI Sync".
  String get label;
  Future<Map<String, dynamic>?> readManifest();
  Future<void> writeManifest(Map<String, dynamic> manifest);
  Future<List<String>> devices();
  Future<List<int>> numbers(String device);
  Future<Uint8List> read(String device, int number);
  Future<void> write(String device, int number, Uint8List data);
}

class FolderStore implements SyncStore {
  FolderStore(this.root);
  final String root;

  @override
  String get label => root;

  @override
  Future<Map<String, dynamic>?> readManifest() async {
    final f = File(p.join(root, manifestName));
    if (!await f.exists()) return null;
    return jsonDecode(await f.readAsString()) as Map<String, dynamic>;
  }

  @override
  Future<void> writeManifest(Map<String, dynamic> manifest) async {
    await Directory(root).create(recursive: true);
    await _atomic(File(p.join(root, manifestName)),
        utf8.encode(const JsonEncoder.withIndent(' ').convert(manifest)));
  }

  @override
  Future<List<String>> devices() async {
    final dir = Directory(p.join(root, 'changes'));
    if (!await dir.exists()) return [];
    final out = <String>[];
    await for (final e in dir.list()) {
      final name = p.basename(e.path);
      if (e is Directory && deviceIdPattern.hasMatch(name)) out.add(name);
    }
    return out..sort();
  }

  @override
  Future<List<int>> numbers(String device) async {
    final dir = Directory(p.join(root, 'changes', device));
    if (!await dir.exists()) return [];
    final out = <int>[];
    await for (final e in dir.list()) {
      final m = _seqName.firstMatch(p.basename(e.path));
      if (m != null) out.add(int.parse(m[1]!));
    }
    return out..sort();
  }

  @override
  Future<Uint8List> read(String device, int number) =>
      File(p.join(root, 'changes', device, fileName(number))).readAsBytes();

  @override
  Future<void> write(String device, int number, Uint8List data) async {
    final f = File(p.join(root, 'changes', device, fileName(number)));
    if (await f.exists()) {
      throw StateError('${f.path} already exists');
    }
    await f.parent.create(recursive: true);
    await _atomic(f, data);
  }

  static Future<void> _atomic(File target, List<int> data) async {
    final tmp = File('${target.path}.tmp');
    await tmp.writeAsBytes(data, flush: true);
    await tmp.rename(target.path);
  }
}

/// Parses the folder listing of a cloud drive into the file numbers.
List<int> numbersFromNames(Iterable<String> names) {
  final out = <int>[];
  for (final n in names) {
    final m = _seqName.firstMatch(n);
    if (m != null) out.add(int.parse(m[1]!));
  }
  return out..sort();
}
