# Personal Finance Intelligence

A Windows 11 desktop app to track income, expenses, investments and savings
goals, forecast cash flow and analyse spending. Everything runs and stays on
your PC: a private PostgreSQL database is bundled with the app, there is no
account and no cloud.

**English · Français · العربية**, base currency of your choice (CHF, EUR,
MAD, USD…) with accounts in any currency.

## Features

- **Accounts & transactions:** checking, savings, cash, cards, investments,
  loans; transfers between accounts (also across currencies); CSV import
  from any bank with column presets, duplicate detection and undo.
- **Smart categories:** your own rules first, then suggestions learned from
  the transactions you categorised yourself (naive Bayes, validated
  chronologically on your newest transactions against a "most common
  category" baseline; the accuracy is shown in Settings).
- **Bills & recurring:** salary, rent and subscriptions can post themselves on
  the due date, and Windows notifications remind you before they are due.
- **Budgets & goals:** monthly limits per category with projection; savings
  goals linked to accounts.
- **Investments:** average-cost positions, prices from stooq (end of day) or
  CoinGecko (crypto), or entered manually; money-weighted (XIRR) and
  time-weighted returns, dividend income, target allocation with drift.
- **Forecast:** recurring items plus a block-bootstrap Monte Carlo of your
  everyday spending, with percentile bands and the chance of going below a
  threshold.
- **Insights:** unusual expenses (robust z-score), detected subscriptions,
  category shifts.
- **Reports:** monthly PDF report, Excel workbook, CSV export, net-worth
  history.
- **Security & data:** optional app lock with Windows Hello; weekly automatic
  backups, manual backup and restore.

## Architecture

| Layer | Technology | Folder |
|---|---|---|
| Desktop shell | WinUI 3 (C++/WinRT, Windows App SDK), NavigationView, Mica, WebView2, Windows Hello, app notifications | `desktop/` |
| Screens | Next.js 16 (static export), TypeScript, Fluent UI React v9, plotly.js | `frontend/` |
| API & analytics | Python 3.12, FastAPI, SQLAlchemy, pandas, numpy, Plotly, reportlab, openpyxl | `backend/` |
| Database | PostgreSQL, a private cluster started by the app | created at runtime |
| Packaging | PyInstaller, Inno Setup (`.exe` installer), MakeAppx (`.msix` for the Microsoft Store) | `scripts/`, `installer/`, `packaging/` |

The shell starts the backend (`pfi-api.exe`) in a Windows job object on a
free localhost port with a per-launch token, then shows the screens in
WebView2. The backend starts PostgreSQL on 127.0.0.1 with a random password
stored in the data folder (`%LOCALAPPDATA%\PersonalFinanceIntelligence`).

## Build

Requirements: Windows 11, Visual Studio 2022/2026 with *Desktop development
with C++* and *WinUI application development* (includes a Windows SDK),
Miniconda, Node.js LTS, PostgreSQL 18 (EDB installer) and Inno Setup.

Double-click **`build.bat`**. It runs the backend tests against PostgreSQL,
builds the screens, packages the backend, builds `PFI.exe`, smoke-tests the
packaged app and creates:

- `dist\PFI-Setup-0.3.0.exe`: installer for direct download;
- `dist\PFI-0.3.0.0-x64.msix`: package for the Microsoft Store (fill in
  `packaging\store.json` with the identity from Partner Center first).

Progress: `dist\build.log`; result: `dist\build-status.txt`. Options:
`-SkipTests`, `-SkipInstaller`, `-SkipMsix`, `-DebugBuild`.

### Develop

```bat
:: backend (conda-forge environment)
cd backend
conda env create -f environment.yml
conda activate pfi
set PFI_TEST_PG_BIN=C:\Program Files\PostgreSQL\18\bin
pytest -q
python run.py --port 8765          :: API docs at http://127.0.0.1:8765/docs

:: screens in a browser, against the backend above
cd frontend
npm ci
npm run dev                         :: http://localhost:3000
```

For the desktop shell, run `build.bat` once (or `scripts\restore-desktop.ps1`),
open `desktop\PFI.sln`, choose **Debug | x64** and press **F5**; the Debug
build runs the backend from source (`pfi.dev.ini`).

## Data and privacy

Your financial data never leaves your PC. The only network requests are
optional: daily exchange rates (only currency codes are sent) and market
prices for holdings you link to an online source (only the symbol is sent).
See [PRIVACY.md](PRIVACY.md).

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Ibrahim (MrBlizo)
