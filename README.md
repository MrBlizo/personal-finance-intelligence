# Personal Finance Intelligence

A Windows 11 desktop app (**PFI.exe**) to track income, expenses,
investments and savings goals, forecast cash flow and analyse spending.
Base currency **CHF**, with accounts in any currency.

| Layer | Technology | Folder |
|---|---|---|
| Desktop app | WinUI 3 (C++/WinRT, Windows App SDK 2.x), WebView2, Mica | `desktop/` (open `PFI.sln`) |
| Screens | Next.js 16 (TypeScript, static export), plotly.js | `frontend/` |
| API & analytics | Python, FastAPI, pandas, Plotly | `backend/` |
| Database | PostgreSQL (private cluster bundled with the app) | created at runtime |
| Installer | PyInstaller + Inno Setup 7 → `dist\PFI-Setup-<version>.exe` | `scripts/`, `installer/` |

## Build the app (one click)

Double-click **`build.bat`**. It checks the tools, creates the conda
environment, runs the backend tests against PostgreSQL, builds the screens,
packages the backend, downloads the Windows App SDK packages, builds
`PFI.exe` with MSBuild, assembles `dist\PFI\`, smoke-tests the packaged
backend and creates **`dist\PFI-Setup-0.2.0.exe`**.

Progress: `dist\build.log`; result: `dist\build-status.txt`.
Options: `build.bat -SkipTests`, `build.bat -SkipInstaller`, `build.bat -DebugBuild`.

### Work on the desktop app in Visual Studio

Run `build.bat` once (or `scripts\restore-desktop.ps1`), then open
`desktop\PFI.sln`, choose **Debug | x64** and press **F5**. The Debug build
uses `pfi.dev.ini`: the backend runs from source with the conda `pfi`
environment and your installed PostgreSQL 18, data in `backend\.devdata`.

### Work on the screens in a browser

```bat
cd backend & python run.py --port 8765
cd frontend & npm run dev      (http://localhost:3000)
```

## Run and test the backend alone

Open **Anaconda Prompt** (or any terminal where `conda` works):

```bat
cd "%USERPROFILE%\Desktop\New folder\backend"
conda env create -f environment.yml
conda activate pfi
copy .env.example .env
```

### Run the tests (uses a temporary private PostgreSQL cluster)

```bat
set PFI_TEST_PG_BIN=C:\Program Files\PostgreSQL\18\bin
pytest -q
```

Expected: `22 passed`.

### Start the API

```bat
python run.py --port 8765
```

The first start creates a private database in `backend\.devdata\pgdata`.
Then open <http://127.0.0.1:8765/docs> for the interactive API page:

1. `POST /api/demo` → **Try it out** → **Execute** loads a synthetic demo
   dataset (clearly marked; remove it with `DELETE /api/demo`).
2. Try `GET /api/analytics/dashboard`, `GET /api/forecast`,
   `GET /api/insights`.

Stop with `Ctrl+C`; PostgreSQL is stopped automatically.

## What the backend does

- **Accounts:** checking, savings, cash, credit card, investment, loan; any
  currency. **Exchange rates** are entered manually (Settings) and
  converted at the rate valid on each transaction date (direct, inverse or
  via a third currency). Missing rates are reported, never guessed.
- **Transactions:** income/expense/transfer, search & filters, bulk
  categorisation, keyword/regex **rules**.
- **CSV import:** encoding/delimiter detection, Swiss formats (`1'234.50`,
  debit/credit columns), preview + column mapping, duplicate-safe
  re-import, undo per import. The original file is archived **read-only**
  in `<data>\imports`; unparseable rows are listed, not dropped.
- **Budgets** (monthly, per category, with end-of-month projection),
  **savings goals** (required monthly saving, projected finish date),
  **recurring items** (salary, rent, insurance…).
- **Investments:** holdings, buy/sell/dividend/fee trades (average cost),
  manual prices, realised/unrealised P&L, allocation; trades book the cash
  side automatically.
- **Forecast** (model prediction): scheduled recurring items + Monte Carlo
  block bootstrap of past discretionary spending → P5–P95 balance bands
  and probability of dropping below a threshold. Seeded, so reproducible.
- **Insights** (statistical observations): unusual expenses (robust
  z-score), subscription detection, month-over-month category shifts,
  data-quality warnings.
- **Charts:** Plotly figures (cash flow, savings rate, category sunburst,
  category trend, weekday heatmap, top payees, budget vs actual, net worth,
  allocation, forecast fan) returned as JSON for the UI.

## Data location (installed app)

`%LOCALAPPDATA%\PersonalFinanceIntelligence\` holds `pgdata\` (database),
`imports\` (archived CSVs), `logs\`. Back up this folder to back up
everything (close the app first).
