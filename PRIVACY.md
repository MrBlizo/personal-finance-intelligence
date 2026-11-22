# Privacy policy

*Personal Finance Intelligence (PFI) · last updated 22 November 2026*

PFI is a desktop app (with an optional Android app) that keeps your
financial data on your own devices.

## What PFI stores

Everything you enter or import (accounts, transactions, budgets, goals,
investments, settings) is stored in a private database file in your Windows
user profile (`%LOCALAPPDATA%\PersonalFinanceIntelligence`, or the app's
private storage when installed from the Microsoft Store). Imported bank
files and receipts you attach are kept in the same folder. Backups are
written to its `backups` subfolder, or to a folder you choose (for example
in OneDrive); if you set a backup password they are encrypted (AES-256) and
the password is kept on this PC, protected by Windows for your user
account. When you choose a OneDrive folder, OneDrive (not PFI) uploads those
backup files under Microsoft's terms. Nothing is sent to the developer or to any server operated by the
developer. There is no account, no analytics, no advertising and no
telemetry.

## Sync between your PC and your phone (optional)

If you turn on sync (Settings › Sync), PFI writes your changes as files into
a folder in your own cloud drive (OneDrive or Google Drive), and reads the
files your other
devices wrote there. Every file is encrypted on the device with AES-256-GCM,
using a key derived from a passphrase only you know; the cloud provider
stores the encrypted files under its own terms and cannot read them. The
passphrase is not stored; the derived key is kept on each device (protected
by Windows on the PC, by the Android keystore on the phone). Receipt files
are not synced.

On the phone, PFI asks you to sign in to OneDrive with your Microsoft
account and the permission "Files.ReadWrite", which it uses only for the
sync folder (`Apps/PFI Sync`). The sign-in is handled by Microsoft; PFI
keeps only the sign-in tokens it receives, in the Android keystore. Stop
syncing removes the key and the sign-in from that device.

With Google Drive, PFI on the PC and on the phone asks you to sign in with
your Google account and the permission "drive.appdata". It lets PFI see only
its own hidden app folder in your Drive, not your other files; the sync files
are kept there. On the PC the sign-in token is stored protected by Windows;
on the phone the sign-in is handled by Google Play services.

## Bank sync (optional)

If you turn on Settings › Bank sync, PFI on the PC fetches new transactions
from your bank through a service you sign up to yourself. PFI is not a
customer of these services and has no server in between:

- **SimpleFIN Bridge** (US and Canada): you link your banks on the SimpleFIN
  website and give PFI a one-time setup token. PFI keeps the resulting access
  URL protected by Windows on your PC and asks SimpleFIN for your accounts and
  transactions. Your bank password stays with SimpleFIN and your bank.
- **Enable Banking** (Europe): you register your own application with Enable
  Banking and link your accounts there. PFI keeps the application's private
  key protected by Windows on your PC; you approve access on your bank's own
  pages. The bank sends a one-time code to the PFI website page
  `bank-callback/`, which only forwards it to PFI on your PC (the page has no
  server code and stores nothing).

The transactions are stored in your local database like imported statements.
Disconnecting in Settings deletes the saved access on the PC. The phone app
does not contact banks.

## The Android app

The phone app stores your data in a private database on the phone. It uses
the network only for the sync described above and for the update check
below. It has no account, no analytics, no advertising and no telemetry.

- **Receipt scanning** uses Google ML Kit's on-device text recognition. The
  photo is read on the phone and is not kept or uploaded; the recognition
  model is bundled with the app.
- **Statement import** reads the CSV file you choose on the phone.
- **Notifications** (bill reminders, over-budget alerts) are computed and shown
  on the phone. Android asks for your permission first; you can switch both
  off in Settings.

## Network requests

PFI makes only these requests, and only for the purposes described:

| Purpose | Service | Data sent | When |
|---|---|---|---|
| Exchange rates | [Exchange API](https://github.com/fawazahmed0/exchange-api) via cdn.jsdelivr.net or currency-api.pages.dev | currency codes (e.g. `chf`) and a date | once a day if enabled in Settings, or when you click "Update now" |
| Stock, ETF & fund prices | query1.finance.yahoo.com | the symbol you entered (e.g. `VWRL.L`) and a date range | once a day for holdings with Yahoo Finance as price source, or on request |
| Bank sync (optional) | SimpleFIN Bridge (bridge.simplefin.org) or api.enablebanking.com | your saved access or signed request, and a date range | every 6 hours while PFI runs, if you linked accounts |
| Crypto prices | api.coingecko.com | the coin id (e.g. `bitcoin`) and a currency code | once a day for holdings with CoinGecko as price source, or on request |
| Update check | api.github.com (the latest PFI release) | nothing beyond the request itself; only the version number is read | once a day on the PC (not in the Microsoft Store version, which the Store updates) and on the phone, unless switched off in Settings |

These services receive your IP address as part of any internet request;
their own privacy policies apply. You can switch both automatic updates off
in Settings and enter rates and prices manually.

PFI needs no API keys for prices. (Versions before 0.7.1 offered Twelve Data,
Alpha Vantage and stooq with your own key; keys saved by those versions stay
in your local database only and are no longer sent anywhere.)

## Windows features

- **Windows Hello** (optional app lock): verification is done by Windows; PFI
  only receives "verified" or "not verified".
- **Store rating** (asked once, after 14 days of use and 20 transactions):
  "Rate PFI" opens the Microsoft Store's own rating window, run by Windows
  under Microsoft's terms. PFI sends nothing itself and only learns whether
  the window was closed or a rating was submitted; your answer is stored on
  this PC.
- **Notifications** (bill reminders): shown locally by Windows.
- **Receipt scanning**: a receipt photo you drop on Quick add is read by
  Windows' built-in offline text recognition (Windows.Media.Ocr). Nothing is
  sent anywhere; the photo is stored with the transaction like any attachment.

## Your control

You can export everything (Excel, CSV, backups), and you can delete all data
by uninstalling the app and deleting the data folder named above.

## Contact

Questions: open an issue at
<https://github.com/MrBlizo/personal-finance-intelligence/issues>.
