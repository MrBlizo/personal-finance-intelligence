"""Switch to Personal Finance from Cashew or Mint in one step.

Both apps export one CSV with every transaction. Accounts and categories
are found by name or created; re-importing the same file adds nothing
twice (each row gets a fingerprint).

- Cashew (Settings › Export CSV): ``account, amount, currency, title, note,
  date, income, type, category name, subcategory name, ...``; the amount is
  signed and the date looks like ``2024-05-01 12:30:00.000``.
- Mint (Transactions › Export): ``Date, Description, Original Description,
  Amount, Transaction Type, Category, Account Name, Labels, Notes``; the
  amount is positive and ``Transaction Type`` says debit or credit.
"""
import csv
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Transaction
from .ynab import Report, _Names

SOURCES = ("cashew", "mint")
CASHEW_COLS = ("account", "amount", "title", "date", "category name")
MINT_COLS = ("Date", "Description", "Amount", "Transaction Type",
             "Category", "Account Name")
#: Mint's own top-level categories map to PFI's defaults where they exist.
MINT_PARENT = {
    "Auto & Transport": "Transport", "Bills & Utilities": "Housing",
    "Food & Dining": "Food", "Health & Fitness": "Health",
    "Home": "Housing", "Shopping": "Shopping", "Entertainment": "Leisure",
    "Travel": "Leisure", "Education": "Education", "Fees & Charges":
    "Finance", "Gifts & Donations": "Family & Gifts", "Taxes": "Finance",
    "Income": None, "Transfer": None,
}


class AppImportError(ValueError):
    """The file is not an export this importer understands."""


def _rows(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()}
            for r in csv.DictReader(io.StringIO(text), dialect=dialect)]


def _amount(text: str, where: str) -> Decimal:
    cleaned = text.replace(" ", "").replace(" ", "").replace("$", "")
    if cleaned.count(",") == 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise AppImportError(
            f"'{text}' in {where} is not an amount. Export the file again "
            "without editing it.") from None


def _date(text: str, where: str, fmts: tuple[str, ...]) -> date:
    value = text.strip()
    for fmt in fmts:
        for candidate in (value, value[:19], value[:10]):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    raise AppImportError(
        f"'{text}' in {where} is not a date this importer knows. Export "
        "the file again without opening it in a spreadsheet first.")


def detect(data: bytes) -> str | None:
    """Return ``cashew`` or ``mint`` when the header matches, else None."""
    rows = _rows(data[:20000])
    head = set(rows[0]) if rows else set()
    if all(c in head for c in CASHEW_COLS):
        return "cashew"
    if all(c in head for c in MINT_COLS):
        return "mint"
    return None


def normalise(data: bytes, source: str) -> list[dict]:
    """Read an export into ``account, currency, date, amount, description,
    notes, parent, category`` rows.

    Parameters
    ----------
    data : bytes
        The CSV file as exported by the app.
    source : str
        ``cashew`` or ``mint``.

    Returns
    -------
    list of dict
        One row per transaction, amounts signed (negative = money out).

    Raises
    ------
    AppImportError
        If the file does not have the expected columns or values.
    """
    rows = _rows(data)
    if not rows:
        raise AppImportError("The file is empty. Export it again from the "
                             "other app.")
    out = []
    if source == "cashew":
        missing = [c for c in CASHEW_COLS if c not in rows[0]]
        if missing:
            raise AppImportError(
                "This is not a Cashew export: the columns "
                + ", ".join(missing) + " are missing. In Cashew use "
                "Settings › Export CSV.")
        for i, r in enumerate(rows, start=2):
            where = f"row {i}"
            amount = _amount(r["amount"], where)
            if amount == 0:
                continue
            sub = r.get("subcategory name", "")
            out.append({
                "account": r["account"] or "Cashew",
                "currency": (r.get("currency") or "").upper()[:3] or None,
                "date": _date(r["date"], where,
                              ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")),
                "amount": amount, "description": r["title"] or "Cashew",
                "notes": r.get("note") or None,
                "parent": r["category name"] if sub else "",
                "category": sub or r["category name"]})
    elif source == "mint":
        missing = [c for c in MINT_COLS if c not in rows[0]]
        if missing:
            raise AppImportError(
                "This is not a Mint export: the columns "
                + ", ".join(missing) + " are missing. Use the CSV that "
                "Mint's Transactions page exported.")
        for i, r in enumerate(rows, start=2):
            where = f"row {i}"
            amount = _amount(r["Amount"], where)
            if r["Transaction Type"].lower() == "debit":
                amount = -abs(amount)
            if amount == 0 or r["Category"] in ("Transfer",
                                                "Credit Card Payment"):
                continue
            cat = r["Category"]
            if cat in MINT_PARENT:  # a Mint top-level category
                cat = MINT_PARENT[cat] or ""
            out.append({
                "account": r["Account Name"] or "Mint", "currency": None,
                "date": _date(r["Date"], where, ("%m/%d/%Y",)),
                "amount": amount,
                "description": r["Description"] or r.get(
                    "Original Description") or "Mint",
                "notes": r.get("Notes") or None,
                "parent": "", "category": "" if cat == "Uncategorized"
                else cat})
    else:
        raise AppImportError(f"Unknown source '{source}'. Use one of: "
                             + ", ".join(SOURCES) + ".")
    return out


def import_rows(db: Session, rows: list[dict], source: str, currency: str,
                dry_run: bool = True) -> dict:
    """Create accounts, categories and transactions from normalised rows.

    Parameters
    ----------
    db : Session
        The open database session.
    rows : list of dict
        The rows from :func:`normalise`.
    source : str
        ``cashew`` or ``mint`` (used in fingerprints and notes).
    currency : str
        The currency for accounts whose rows don't say.
    dry_run : bool
        The flag to roll back and only report what would happen.

    Returns
    -------
    dict
        The import report (accounts and categories created, transactions,
        duplicates skipped).
    """
    report = Report()
    names = _Names(db, currency, report)
    first = min((r["date"] for r in rows), default=date.today())
    seen = set(db.scalars(select(Transaction.fingerprint).where(
        Transaction.fingerprint.like(f"{source}:%"))))
    counts: dict[str, int] = {}
    for r in rows:
        created = len(report.accounts_created)
        acc = names.account(r["account"], first)
        if len(report.accounts_created) > created:
            acc.notes = f"Imported from {source.title()}."
            acc.currency = r["currency"] or currency
        kind = "income" if r["amount"] > 0 else "expense"
        cat = names.category(r["parent"], r["category"], kind) \
            if r["category"] else None
        key = f"{r['account']}|{r['date']}|{r['amount']}|{r['description']}"
        counts[key] = counts.get(key, 0) + 1
        fp = f"{source}:" + hashlib.sha256(
            f"{key}|{counts[key]}".encode()).hexdigest()[:56]
        if fp in seen:
            report.duplicates += 1
            continue
        seen.add(fp)
        db.add(Transaction(
            account_id=acc.id, txn_date=r["date"], amount=r["amount"],
            kind=kind, description=r["description"][:500],
            notes=r["notes"], category_id=cat.id if cat else None,
            category_source="import" if cat else None, fingerprint=fp,
            reviewed=True))
        report.transactions += 1
    db.flush()
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report.as_dict()
