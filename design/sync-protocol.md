# PFI sync protocol, format 1

PFI on Windows and the PFI phone app keep the same data by exchanging
encrypted change files through a folder the user already has in a cloud
drive (OneDrive, Dropbox, Google Drive). There is no PFI server. The cloud
provider only ever sees encrypted files.

## Folder layout

```
<sync folder>/
  pfi-sync.json                 manifest: format, key-derivation salt, check value
  changes/<device-id>/00000001.pfisync
  changes/<device-id>/00000002.pfisync
  ...
```

* `device-id`: 16 random hex characters, created once per installation.
* Files are numbered per device from 1 and never rewritten. A device writes
  `<n>.pfisync.tmp` and renames it, so readers ignore half-written files.
* Each device remembers, per other device, the highest number it applied.

## Manifest (`pfi-sync.json`, plain JSON)

```json
{"app": "PFI", "format": 1,
 "kdf": {"alg": "pbkdf2-sha256", "iterations": 600000, "salt": "<base64 16 bytes>"},
 "check": "<base64 of an encrypted change file whose payload is {\"check\": \"PFI-SYNC\"}>"}
```

The first device creates it. A device that joins derives the key from the
sync passphrase and must be able to decrypt `check` (wrong passphrase
otherwise). The derived 32-byte key is kept on the device (Windows: DPAPI;
phone: the platform keystore); the passphrase itself is not stored.

## Change file

```
"PFS1" | nonce (12 bytes) | AES-256-GCM ciphertext
```

* Additional authenticated data: `"<device-id>/<number>"`, so a file cannot be
  moved to another name without failing to decrypt.
* Plaintext: gzip of UTF-8 JSON.

```json
{"format": 1, "device": "<device-id>", "name": "Ibrahim's PC", "seq": 7,
 "created": "2026-11-16 14:00:00.000",
 "changes": [
   {"t": "accounts", "uid": "...", "u": "2026-11-16 13:59:58.120",
    "row": {"name": "Cash", "currency": "CHF", "...": "..."}},
   {"t": "transactions", "uid": "...", "u": "...",
    "row": {"account_id": "<uid of the account>", "category_id": null, "...": "..."}},
   {"t": "tags", "uid": "...", "del": "2026-11-16 13:58:00.000"}
 ]}
```

* `row` holds the raw SQLite column values of the row (same schema on every
  device): money is a scaled integer, dates are `YYYY-MM-DD` text, times are
  `YYYY-MM-DD HH:MM:SS[.fff]` UTC text.
* The local integer `id` is left out. Every foreign-key column carries the
  **uid** of the referenced row instead of its local id. Foreign keys to
  tables that are not synced (`import_batch_id`) are sent as `null`.
* Changes are ordered parents first (accounts before transactions).

## Merging

* **Same uid on both sides:** the version with the later `u` wins (times
  compared after padding the fraction to 6 digits); equal times keep the
  local version.
* **Deletion (`del`):** deletes the local row unless the local row was
  changed after the deletion time. Deleted uids are remembered, so an older
  copy that arrives later does not bring the row back.
* **Same thing created on two devices** (a unique key such as an account
  name, a category name and kind, a budget month or a statement fingerprint
  already exists under another uid): the rows are merged. The incoming uid is
  recorded as an alias of the local row, and the newer field values win.
* **Parent not there yet** (a transaction whose account arrives in a later
  file): the change waits and is retried on the next sync.
* Rows a device received are not sent back (each device records the last
  version it sent or applied per uid).

## Tables

All tables with `uid`/`updated_at` take part, except `attachments` (receipt
files are not synced in format 1). Settings, import history, presets and
backups stay on each device.
