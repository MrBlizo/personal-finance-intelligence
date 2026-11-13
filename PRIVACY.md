# Privacy policy

*Personal Finance Intelligence (PFI) · last updated 10 November 2026*

PFI is a desktop app that keeps your financial data on your own computer.

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

## Network requests

PFI makes only these requests, and only for the purposes described:

| Purpose | Service | Data sent | When |
|---|---|---|---|
| Exchange rates | [Exchange API](https://github.com/fawazahmed0/exchange-api) via cdn.jsdelivr.net or currency-api.pages.dev | currency codes (e.g. `chf`) and a date | once a day if enabled in Settings, or when you click "Update now" |
| Stock & ETF prices | api.twelvedata.com | the symbol you entered (e.g. `VT`), a date range and your personal Twelve Data API key | once a day for holdings with Twelve Data as price source, or on request |
| Stock & ETF prices | www.alphavantage.co | the symbol you entered (e.g. `TSCO.LON`) and your personal Alpha Vantage API key | once a day for holdings with Alpha Vantage as price source, or on request |
| Market prices | stooq.com | the symbol you entered (e.g. `vt.us`), a date range and your personal stooq API key (if you entered one) | once a day for holdings with stooq as price source, or on request |
| Crypto prices | api.coingecko.com | the coin id (e.g. `bitcoin`) and a currency code | once a day for holdings with CoinGecko as price source, or on request |

These services receive your IP address as part of any internet request;
their own privacy policies apply. You can switch both automatic updates off
in Settings and enter rates and prices manually.

Your price-provider API keys (Twelve Data, Alpha Vantage, stooq) are stored
in your local database and each is only sent to its own provider; they are
never shown again in the app (only their last four characters).

## Windows features

- **Windows Hello** (optional app lock): verification is done by Windows; PFI
  only receives "verified" or "not verified".
- **Notifications** (bill reminders): shown locally by Windows.

## Your control

You can export everything (Excel, CSV, backups), and you can delete all data
by uninstalling the app and deleting the data folder named above.

## Contact

Questions: open an issue at
<https://github.com/MrBlizo/personal-finance-intelligence/issues>.
