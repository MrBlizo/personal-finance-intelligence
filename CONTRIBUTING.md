# Contributing

Thanks for helping improve Personal Finance Intelligence.

## Workflow

1. Fork the repository and clone your fork.
2. Create a short, descriptive branch from an up-to-date `main`
   (`fix-import-dates`, `feat-goal-chart`).
3. Commit with conventional prefixes: `feat:`, `fix:`, `docs:`, `test:`,
   `refactor:`, `chore:`.
4. Open a pull request against `main`. CI must pass.

## Code style

- Python: PEP 8 (flake8, max line length 79), NumPy-style docstrings,
  `pathlib.Path` for paths, error messages that say what went wrong, why,
  and how to fix it.
- TypeScript: strict mode; screens use Fluent UI v9 components and the
  shared building blocks in `frontend/components/ui.tsx`. Every visible
  text goes through `t()`; add French and Arabic translations to
  `frontend/lib/locales/`.
- C++: C++20, C++/WinRT.

## Tests

```bat
cd backend
set PFI_TEST_PG_BIN=C:\Program Files\PostgreSQL\18\bin
pytest -q
cd ..\frontend
npx tsc --noEmit
npm run build
```

## Data

Never commit personal financial data, real bank exports or database dumps.
Use the demo data (`POST /api/demo`) or synthetic files in tests.
