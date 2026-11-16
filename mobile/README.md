# PFI for Android and iOS

The phone app keeps its own SQLite database with the **same tables** as PFI
on Windows (`assets/db/schema.sql`, generated from the PC's models) and syncs
with the PC through a folder in your cloud drive. Format and merge rules:
[design/sync-protocol.md](../design/sync-protocol.md).

| Cloud drive | Folder on the PC                     | Phone access                        |
|-------------|--------------------------------------|-------------------------------------|
| OneDrive    | `OneDrive\Apps\PFI Sync`             | Microsoft Graph, `Files.ReadWrite`  |
| Dropbox     | `Dropbox\Apps\PFI Sync` (app folder) | Dropbox API, app folder "PFI Sync"  |

## Build

```bash
cd mobile
flutter create --org io.github.mrblizo --project-name pfi --platforms android,ios .   # first time only
flutter pub get
flutter run --dart-define=ONEDRIVE_CLIENT_ID=<id> --dart-define=DROPBOX_APP_KEY=<key>
```

The client ids are public (OAuth with PKCE, no secret). In GitHub Actions
they come from the repository variables `ONEDRIVE_CLIENT_ID` and
`DROPBOX_APP_KEY`.

## Registering the cloud apps (once)

* **OneDrive**: Azure portal › App registrations › New registration,
  "Personal Microsoft accounts and work accounts", platform "Mobile and
  desktop applications", redirect URI `io.github.mrblizo.pfi://auth`,
  API permission `Files.ReadWrite` (delegated), "Allow public client flows".
* **Dropbox**: App Console › Create app, "Scoped access", "App folder",
  name **PFI Sync**, permissions `files.content.read` and
  `files.content.write`, redirect URI `io.github.mrblizo.pfi://auth`.

## After changing a model on the PC

```bash
cd backend && python -m app.services.mobile_schema ../mobile/assets/db
```

`backend/tests/test_mobile_schema.py` fails until the copy is regenerated.

## Signing

Release APKs are signed in GitHub Actions with the PFI key (repository
secrets `PFI_KEYSTORE_BASE64` and `PFI_KEYSTORE_PASSWORD`, alias `pfi`).
Android only installs an update over an app signed with the same key, so
keep a backup of `pfi-upload.jks` and its password.

Public fingerprints (for Google Cloud and app stores):

* SHA-1: `E6:B2:69:D2:6E:14:C9:5C:BB:3C:AE:9E:01:B4:37:11:21:DE:5C:1A`
* SHA-256: `B2:57:CD:10:2B:C4:63:17:D8:28:43:7E:FB:52:A2:A9:0A:30:44:4E:8A:9D:3C:27:C9:EF:08:B6:33:01:6F:37`

Publishing a GitHub release attaches `PFI-<version>.apk` to it automatically.
