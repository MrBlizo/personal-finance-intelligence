// Cloud drives the phone syncs through: OneDrive and Dropbox, through
// their web APIs. The folder is the one PFI on Windows uses through the
// drive's desktop app:
//   OneDrive: OneDrive/Apps/PFI Sync
//   Dropbox:  Dropbox/Apps/PFI Sync (the app folder of the "PFI Sync" app)
// Google Drive: the hidden app data folder, which PFI on Windows reaches
// through the Drive API too (backend/app/services/gdrive.py); flat names
// "pfi-sync.json" and "<device>-<00000001>.pfisync".
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'crypto.dart';
import 'store.dart';

enum CloudProvider { onedrive, gdrive, dropbox }

extension CloudProviderInfo on CloudProvider {
  String get title => switch (this) {
        CloudProvider.onedrive => 'OneDrive',
        CloudProvider.gdrive => 'Google Drive',
        CloudProvider.dropbox => 'Dropbox',
      };
  String get pcFolder => switch (this) {
        CloudProvider.onedrive => r'OneDrive\Apps\PFI Sync',
        CloudProvider.gdrive => 'Google Drive (PFI app data)',
        CloudProvider.dropbox => r'Dropbox\Apps\PFI Sync',
      };
  bool get configured => switch (this) {
        CloudProvider.onedrive => oneDriveClientId.isNotEmpty,
        CloudProvider.gdrive => googleServerClientId.isNotEmpty,
        CloudProvider.dropbox => dropboxAppKey.isNotEmpty,
      };
}

const _storage = FlutterSecureStorage();

String _random(int n) {
  const chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  final r = Random.secure();
  return List.generate(n, (_) => chars[r.nextInt(chars.length)]).join();
}

Future<String> _challenge(String verifier) async {
  final hash = await Sha256().hash(ascii.encode(verifier));
  return base64Url.encode(hash.bytes).replaceAll('=', '');
}

/// OAuth 2 with PKCE (no client secret), refresh token kept in the
/// platform keystore.
class CloudAuth {
  CloudAuth(this.provider);
  final CloudProvider provider;
  String? _access;
  DateTime _expires = DateTime.fromMillisecondsSinceEpoch(0);

  String get _refreshKey => 'oauth_refresh_${provider.name}';

  Uri get _authorize => switch (provider) {
        CloudProvider.onedrive => Uri.parse(
            'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'),
        CloudProvider.gdrive =>
          Uri.parse('https://accounts.google.com/o/oauth2/v2/auth'),
        CloudProvider.dropbox =>
          Uri.parse('https://www.dropbox.com/oauth2/authorize'),
      };
  Uri get _token => switch (provider) {
        CloudProvider.onedrive => Uri.parse(
            'https://login.microsoftonline.com/common/oauth2/v2.0/token'),
        CloudProvider.gdrive => Uri.parse('https://oauth2.googleapis.com/token'),
        CloudProvider.dropbox =>
          Uri.parse('https://api.dropboxapi.com/oauth2/token'),
      };
  String get _clientId => switch (provider) {
        CloudProvider.onedrive => oneDriveClientId,
        CloudProvider.gdrive => googleServerClientId,
        CloudProvider.dropbox => dropboxAppKey,
      };
  String get _redirect => oauthRedirect;
  static const _oneDriveScope = 'Files.ReadWrite offline_access';
  static const _googleScope = 'https://www.googleapis.com/auth/drive.appdata';

  Future<bool> get signedIn async =>
      (await _storage.read(key: _refreshKey)) != null;

  static bool _googleReady = false;

  static Future<GoogleSignIn> _google() async {
    if (!_googleReady) {
      await GoogleSignIn.instance.initialize(serverClientId: googleServerClientId);
      _googleReady = true;
    }
    return GoogleSignIn.instance;
  }

  /// Opens the provider's sign-in page in the browser (Google: the account
  /// picker of Google Play services).
  Future<void> signIn() async {
    if (provider == CloudProvider.gdrive) {
      final g = await _google();
      try {
        await g.authorizationClient.authorizeScopes(const [_googleScope]);
      } on GoogleSignInException catch (e) {
        throw SyncException(e.code == GoogleSignInExceptionCode.canceled
            ? 'Sign-in was cancelled.'
            : 'Google sign-in failed (${e.description ?? e.code.name}).');
      }
      await _storage.write(key: _refreshKey, value: 'google');
      return;
    }
    if (_clientId.isEmpty) {
      throw SyncException('${provider.title} is not available in this build '
          'of PFI yet.');
    }
    final verifier = _random(64);
    final state = _random(24);
    final url = _authorize.replace(queryParameters: {
      'client_id': _clientId,
      'response_type': 'code',
      'redirect_uri': _redirect,
      'code_challenge': await _challenge(verifier),
      'code_challenge_method': 'S256',
      'state': state,
      if (provider == CloudProvider.onedrive) 'scope': _oneDriveScope,
      if (provider == CloudProvider.dropbox) 'token_access_type': 'offline',
    });
    final result = await FlutterWebAuth2.authenticate(
        url: url.toString(), callbackUrlScheme: oauthScheme);
    final params = Uri.parse(result).queryParameters;
    if (params['state'] != state) {
      throw SyncException('Sign-in was interrupted. Please try again.');
    }
    final code = params['code'];
    if (code == null) {
      throw SyncException(params['error_description'] ??
          'Sign-in was cancelled or refused.');
    }
    await _exchange({
      'grant_type': 'authorization_code',
      'code': code,
      'redirect_uri': _redirect,
      'code_verifier': verifier,
    });
  }

  Future<void> signOut() async {
    _access = null;
    await _storage.delete(key: _refreshKey);
    if (provider == CloudProvider.gdrive) {
      try {
        await (await _google()).disconnect();
      } catch (_) {}
    }
  }

  Future<void> _exchange(Map<String, String> body) async {
    final r = await http.post(_token, body: {
      ...body,
      'client_id': _clientId,
      if (provider == CloudProvider.onedrive) 'scope': _oneDriveScope,
    });
    if (r.statusCode != 200) {
      throw SyncException('${provider.title} refused the sign-in '
          '(${r.statusCode}). Sign in again in Settings › Sync.');
    }
    final json = jsonDecode(r.body) as Map<String, dynamic>;
    _access = json['access_token'] as String;
    _expires = DateTime.now()
        .add(Duration(seconds: (json['expires_in'] as num? ?? 3600).toInt() - 60));
    final refresh = json['refresh_token'] as String?;
    if (refresh == null && body['grant_type'] == 'authorization_code') {
      throw SyncException('${provider.title} did not allow offline access. '
          'Sign in again and allow PFI to keep its sync files.');
    }
    if (refresh != null) await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<String> token() async {
    if (_access != null && DateTime.now().isBefore(_expires)) return _access!;
    if (provider == CloudProvider.gdrive) {
      final headers = await (await _google())
          .authorizationClient
          .authorizationHeaders(const [_googleScope]);
      final value = headers?['Authorization'] ?? headers?['authorization'];
      if (value == null) {
        throw SyncException('Sign in to Google Drive again in Settings › Sync.');
      }
      _access = value.replaceFirst(RegExp(r'^Bearer\s+', caseSensitive: false), '');
      _expires = DateTime.now().add(const Duration(minutes: 45));
      return _access!;
    }
    final refresh = await _storage.read(key: _refreshKey);
    if (refresh == null) {
      throw SyncException('Sign in to ${provider.title} in Settings › Sync.');
    }
    await _exchange({'grant_type': 'refresh_token', 'refresh_token': refresh});
    return _access!;
  }
}

SyncStore cloudStore(CloudProvider p, CloudAuth auth) => switch (p) {
      CloudProvider.onedrive => OneDriveStore(auth),
      CloudProvider.gdrive => GoogleDriveStore(auth),
      CloudProvider.dropbox => DropboxStore(auth),
    };

class _NotFound implements Exception {}

class OneDriveStore implements SyncStore {
  OneDriveStore(this.auth);
  final CloudAuth auth;
  static const _folder = ['Apps', 'PFI Sync'];

  @override
  String get label => 'OneDrive › Apps › PFI Sync';

  Uri _item(List<String> path, String suffix,
      [Map<String, String>? query]) {
    final p = [..._folder, ...path].map(Uri.encodeComponent).join('/');
    return Uri.parse('https://graph.microsoft.com/v1.0/me/drive/root:/$p:$suffix')
        .replace(queryParameters: query);
  }

  Future<http.Response> _send(String method, Uri url,
      {List<int>? body, String? type}) async {
    final req = http.Request(method, url)
      ..headers['Authorization'] = 'Bearer ${await auth.token()}';
    if (body != null) {
      req.bodyBytes = body;
      req.headers['Content-Type'] = type ?? 'application/octet-stream';
    }
    final res = await http.Response.fromStream(await req.send());
    if (res.statusCode == 404) throw _NotFound();
    if (res.statusCode >= 300) {
      throw SyncException('OneDrive answered ${res.statusCode}. Check your '
          'connection and try again.');
    }
    return res;
  }

  Future<List<Map<String, dynamic>>> _children(List<String> path) async {
    final out = <Map<String, dynamic>>[];
    Uri? url = _item(path, '/children', {r'$select': 'name,folder', r'$top': '200'});
    try {
      while (url != null) {
        final j = jsonDecode((await _send('GET', url)).body) as Map<String, dynamic>;
        out.addAll((j['value'] as List).cast<Map<String, dynamic>>());
        final next = j['@odata.nextLink'] as String?;
        url = next == null ? null : Uri.parse(next);
      }
    } on _NotFound {
      return [];
    }
    return out;
  }

  @override
  Future<Map<String, dynamic>?> readManifest() async {
    try {
      final r = await _send('GET', _item([manifestName], '/content'));
      return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    } on _NotFound {
      return null;
    }
  }

  @override
  Future<void> writeManifest(Map<String, dynamic> manifest) async {
    await _send('PUT', _item([manifestName], '/content'),
        body: utf8.encode(const JsonEncoder.withIndent(' ').convert(manifest)),
        type: 'application/json');
  }

  @override
  Future<List<String>> devices() async => [
        for (final c in await _children(['changes']))
          if (c['folder'] != null && deviceIdPattern.hasMatch(c['name'] as String))
            c['name'] as String
      ]..sort();

  @override
  Future<List<int>> numbers(String device) async => numbersFromNames(
      (await _children(['changes', device])).map((c) => c['name'] as String));

  @override
  Future<Uint8List> read(String device, int number) async =>
      (await _send('GET', _item(['changes', device, fileName(number)], '/content')))
          .bodyBytes;

  @override
  Future<void> write(String device, int number, Uint8List data) async {
    await _send(
        'PUT',
        _item(['changes', device, fileName(number)], '/content',
            {'@microsoft.graph.conflictBehavior': 'fail'}),
        body: data);
  }
}

class DropboxStore implements SyncStore {
  DropboxStore(this.auth);
  final CloudAuth auth;

  @override
  String get label => 'Dropbox › Apps › PFI Sync';

  Future<http.Response> _rpc(String endpoint, Map<String, Object?> args) async {
    final r = await http.post(
        Uri.parse('https://api.dropboxapi.com/2/$endpoint'),
        headers: {
          'Authorization': 'Bearer ${await auth.token()}',
          'Content-Type': 'application/json'
        },
        body: jsonEncode(args));
    if (r.statusCode == 409 && r.body.contains('not_found')) throw _NotFound();
    if (r.statusCode >= 300) {
      throw SyncException('Dropbox answered ${r.statusCode}. Check your '
          'connection and try again.');
    }
    return r;
  }

  Future<http.Response> _content(String endpoint, Map<String, Object?> args,
      [List<int>? body]) async {
    final r = await http.post(
        Uri.parse('https://content.dropboxapi.com/2/$endpoint'),
        headers: {
          'Authorization': 'Bearer ${await auth.token()}',
          'Dropbox-API-Arg': jsonEncode(args),
          if (body != null) 'Content-Type': 'application/octet-stream',
        },
        body: body);
    if (r.statusCode == 409 && r.body.contains('not_found')) throw _NotFound();
    if (r.statusCode >= 300) {
      throw SyncException('Dropbox answered ${r.statusCode}. Check your '
          'connection and try again.');
    }
    return r;
  }

  Future<List<Map<String, dynamic>>> _list(String path) async {
    final out = <Map<String, dynamic>>[];
    try {
      var j = jsonDecode((await _rpc('files/list_folder', {'path': path})).body)
          as Map<String, dynamic>;
      out.addAll((j['entries'] as List).cast<Map<String, dynamic>>());
      while (j['has_more'] == true) {
        j = jsonDecode((await _rpc('files/list_folder/continue',
                {'cursor': j['cursor']}))
            .body) as Map<String, dynamic>;
        out.addAll((j['entries'] as List).cast<Map<String, dynamic>>());
      }
    } on _NotFound {
      return [];
    }
    return out;
  }

  @override
  Future<Map<String, dynamic>?> readManifest() async {
    try {
      final r = await _content('files/download', {'path': '/$manifestName'});
      return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    } on _NotFound {
      return null;
    }
  }

  @override
  Future<void> writeManifest(Map<String, dynamic> manifest) async {
    await _content('files/upload', {'path': '/$manifestName', 'mode': 'overwrite'},
        utf8.encode(const JsonEncoder.withIndent(' ').convert(manifest)));
  }

  @override
  Future<List<String>> devices() async => [
        for (final e in await _list('/changes'))
          if (e['.tag'] == 'folder' && deviceIdPattern.hasMatch(e['name'] as String))
            e['name'] as String
      ]..sort();

  @override
  Future<List<int>> numbers(String device) async => numbersFromNames(
      (await _list('/changes/$device')).map((e) => e['name'] as String));

  @override
  Future<Uint8List> read(String device, int number) async =>
      (await _content('files/download',
              {'path': '/changes/$device/${fileName(number)}'}))
          .bodyBytes;

  @override
  Future<void> write(String device, int number, Uint8List data) async {
    await _content(
        'files/upload',
        {
          'path': '/changes/$device/${fileName(number)}',
          'mode': 'add',
          'autorename': false
        },
        data);
  }
}

/// Google Drive's hidden app data folder (permission drive.appdata only).
class GoogleDriveStore implements SyncStore {
  GoogleDriveStore(this.auth);
  final CloudAuth auth;
  Map<String, String>? _files;
  static final _name = RegExp(r'^([0-9a-f]{16})-(\d{8})\.pfisync$');
  static const _api = 'https://www.googleapis.com/drive/v3';

  @override
  String get label => 'Google Drive › PFI app data';

  Future<http.Response> _send(String method, Uri url,
      {Map<String, String>? headers, List<int>? body}) async {
    final req = http.Request(method, url)
      ..headers['Authorization'] = 'Bearer ${await auth.token()}';
    if (headers != null) req.headers.addAll(headers);
    if (body != null) req.bodyBytes = body;
    final r = await http.Response.fromStream(await req.send());
    if (r.statusCode == 401) {
      throw SyncException('Google Drive refused access. Sign in to Google '
          'Drive again in Settings › Sync.');
    }
    if (r.statusCode >= 300) {
      throw SyncException('Google Drive answered ${r.statusCode}. Check your '
          'connection and try again.');
    }
    return r;
  }

  Future<Map<String, String>> _list() async {
    if (_files != null) return _files!;
    final files = <String, String>{};
    String? page;
    do {
      final r = await _send(
          'GET',
          Uri.parse('$_api/files').replace(queryParameters: {
            'spaces': 'appDataFolder',
            'pageSize': '1000',
            'fields': 'nextPageToken, files(id, name)',
            if (page != null) 'pageToken': page,
          }));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      for (final f in (j['files'] as List? ?? []).cast<Map<String, dynamic>>()) {
        files.putIfAbsent(f['name'] as String, () => f['id'] as String);
      }
      page = j['nextPageToken'] as String?;
    } while (page != null);
    return _files = files;
  }

  Future<Uint8List?> _download(String name) async {
    final id = (await _list())[name];
    if (id == null) return null;
    return (await _send('GET',
            Uri.parse('$_api/files/$id').replace(queryParameters: {'alt': 'media'})))
        .bodyBytes;
  }

  Future<void> _upload(String name, List<int> data, String mime) async {
    final boundary = 'pfi${DateTime.now().microsecondsSinceEpoch}';
    final meta = jsonEncode({
      'name': name,
      'parents': ['appDataFolder']
    });
    final body = <int>[
      ...utf8.encode('--$boundary\r\nContent-Type: application/json; '
          'charset=UTF-8\r\n\r\n$meta\r\n--$boundary\r\n'
          'Content-Type: $mime\r\n\r\n'),
      ...data,
      ...utf8.encode('\r\n--$boundary--'),
    ];
    final r = await _send(
        'POST',
        Uri.parse('https://www.googleapis.com/upload/drive/v3/files')
            .replace(queryParameters: {'uploadType': 'multipart', 'fields': 'id'}),
        headers: {'Content-Type': 'multipart/related; boundary=$boundary'},
        body: body);
    (await _list())[name] = (jsonDecode(r.body) as Map<String, dynamic>)['id'] as String;
  }

  @override
  Future<Map<String, dynamic>?> readManifest() async {
    final raw = await _download(manifestName);
    return raw == null ? null : jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
  }

  @override
  Future<void> writeManifest(Map<String, dynamic> manifest) => _upload(manifestName,
      utf8.encode(const JsonEncoder.withIndent(' ').convert(manifest)), 'application/json');

  @override
  Future<List<String>> devices() async => {
        for (final n in (await _list()).keys)
          if (_name.firstMatch(n) case final m?) m[1]!
      }.toList()
        ..sort();

  @override
  Future<List<int>> numbers(String device) async => [
        for (final n in (await _list()).keys)
          if (_name.firstMatch(n) case final m? when m[1] == device) int.parse(m[2]!)
      ]..sort();

  @override
  Future<Uint8List> read(String device, int number) async {
    final name = '$device-${fileName(number)}';
    final raw = await _download(name);
    if (raw == null) {
      throw SyncException('$name is missing in Google Drive. Try syncing again.');
    }
    return raw;
  }

  @override
  Future<void> write(String device, int number, Uint8List data) async {
    final name = '$device-${fileName(number)}';
    if ((await _list()).containsKey(name)) {
      throw SyncException('$name already exists in Google Drive. Set up sync '
          'again on this phone.');
    }
    await _upload(name, data, 'application/octet-stream');
  }
}
