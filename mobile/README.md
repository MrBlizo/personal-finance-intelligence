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
