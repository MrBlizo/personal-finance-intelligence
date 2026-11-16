// Encryption of sync files: PBKDF2-SHA256 key, AES-256-GCM, gzip'ed JSON.
// Byte-compatible with backend/app/services/sync.py (see
// design/sync-protocol.md).
import 'dart:convert';
import 'dart:io' show gzip;
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

const List<int> fileMagic = [0x50, 0x46, 0x53, 0x31]; // "PFS1"

class SyncException implements Exception {
  SyncException(this.message);
  final String message;
  @override
  String toString() => message;
}

Future<Uint8List> deriveKey(
    String passphrase, List<int> salt, int iterations) async {
  final pbkdf2 = Pbkdf2(
      macAlgorithm: Hmac.sha256(), iterations: iterations, bits: 256);
  final key =
      await pbkdf2.deriveKeyFromPassword(password: passphrase, nonce: salt);
  return Uint8List.fromList(await key.extractBytes());
}

Future<Uint8List> seal(
    List<int> key, String aad, Map<String, Object?> payload) async {
  final raw = gzip.encode(utf8.encode(jsonEncode(payload)));
  final aes = AesGcm.with256bits();
  final nonce = aes.newNonce();
  final box = await aes.encrypt(raw,
      secretKey: SecretKey(key), nonce: nonce, aad: utf8.encode(aad));
  return Uint8List.fromList(
      [...fileMagic, ...nonce, ...box.cipherText, ...box.mac.bytes]);
}

Future<Map<String, dynamic>> unseal(
    List<int> key, String aad, List<int> data) async {
  if (data.length < 4 + 12 + 16 ||
      data[0] != fileMagic[0] ||
      data[1] != fileMagic[1] ||
      data[2] != fileMagic[2] ||
      data[3] != fileMagic[3]) {
    throw SyncException('$aad is not a PFI sync file.');
  }
  final nonce = data.sublist(4, 16);
  final body = data.sublist(16);
  final cipherText = body.sublist(0, body.length - 16);
  final mac = Mac(body.sublist(body.length - 16));
  final List<int> clear;
  try {
    clear = await AesGcm.with256bits().decrypt(
        SecretBox(cipherText, nonce: nonce, mac: mac),
        secretKey: SecretKey(key),
        aad: utf8.encode(aad));
  } on SecretBoxAuthenticationError {
    throw SyncException('$aad could not be decrypted: it was written with '
        'another sync passphrase or is damaged. Set up sync again with the '
        'passphrase used on your other devices.');
  }
  return jsonDecode(utf8.decode(gzip.decode(clear))) as Map<String, dynamic>;
}
