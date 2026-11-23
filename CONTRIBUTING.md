# Contributing

Personal Finance is source-available under the [PolyForm Strict License](LICENSE): the
code is public so anyone can check it, but changed versions may not be
published. Because of that, **pull requests with code are not accepted**.

What helps most:

- **Bug reports:** open an
  [issue](https://github.com/MrBlizo/personal-finance-intelligence/issues)
  with what you did, what you expected and what happened. Add your Personal Finance
  version (Settings › About) and Windows or Android version.
- **Ideas:** open an issue describing the problem you want solved.
- **Translations:** suggest better wording for French or Arabic in an issue.
- **Bank file formats:** if your bank's CSV export doesn't import, describe
  its column headers and date format. Never attach real statements.

## Maintainer notes

Commit with conventional prefixes (`feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `chore:`) on a short-lived branch, and open a pull request
against `main`; CI must pass.

- Python: PEP 8 (flake8, max line length 79), NumPy-style docstrings,
  `pathlib.Path` for paths, error messages that say what went wrong, why,
  and how to fix it.
- TypeScript: strict mode; every visible text goes through `t()` with French
  and Arabic translations in `frontend/lib/locales/`.
- Never commit personal financial data, real bank exports or database dumps.
