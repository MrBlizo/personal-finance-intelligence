"""Bank-statement CSV import with preview, mapping and de-duplication.

The original upload is archived unchanged (read-only) before parsing. Rows
that cannot be parsed are reported back, never silently dropped. Duplicates
are detected with a fingerprint of account, date, amount, description and
the occurrence index of identical rows within the file, so re-importing
the same file is safe while genuine same-day repeats are kept.
"""
import csv
import hashlib
import io
import json
import re
import stat
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category, CategoryRule, ImportBatch, Transaction
from ..schemas import ImportMapping
from . import statements

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
DELIMITERS = ",;\t|"
_HINTS = {
    "date": ("date", "datum", "booking", "buchung", "valuta", "valeur",
             "transaction date", "value date"),
    "description": ("description", "text", "libell", "details", "memo",
                    "beschreibung", "buchungstext", "purpose", "payee"),
    "amount": ("amount", "betrag", "montant", "value", "sum"),
    "debit": ("debit", "belastung", "lastschrift", "withdrawal", "out"),
    "credit": ("credit", "gutschrift", "deposit", "in"),
    "merchant": ("merchant", "payee", "counterparty", "empf",
                 "beneficiary", "name"),
}


class ImportError_(ValueError):
    """Raised when an uploaded file cannot be read as CSV."""


def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ImportError_(
        "The file is not valid text in UTF-8 or Windows-1252. Export the "
        "statement from your bank again as CSV and retry.")


def read_csv(raw: bytes, skip_rows: int = 0
             ) -> tuple[pd.DataFrame, str, str]:
    """Decode and parse a CSV upload with automatic delimiter detection.

    Parameters
    ----------
    raw : bytes
        The uploaded file content.
    skip_rows : int
        The number of leading lines (bank headers) to ignore.

    Returns
    -------
    tuple of (DataFrame, str, str)
        The table (all values as strings), the delimiter and the encoding.
    """
    text, encoding = _decode(raw)
    lines = text.splitlines()[skip_rows:]
    body = "\n".join(lines)
    if not body.strip():
        raise ImportError_(
            "The file is empty after skipping header lines. Lower "
            "'skip rows' or choose a different file.")
    sample = "\n".join(lines[:50])
    try:
        delimiter = csv.Sniffer().sniff(sample, DELIMITERS).delimiter
    except csv.Error:
        delimiter = max(DELIMITERS, key=sample.count)
    try:
        df = pd.read_csv(io.StringIO(body), sep=delimiter, dtype=str,
                         keep_default_na=False, skipinitialspace=True,
                         on_bad_lines="error")
    except (pd.errors.ParserError, ValueError) as exc:
        raise ImportError_(
            f"Could not parse the CSV ({exc}). The file may contain bank "
            "header lines above the column names; set 'skip rows' to "
            "the number of lines before the header.") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return df, delimiter, encoding


def read_statement(raw: bytes, skip_rows: int = 0
                   ) -> tuple[pd.DataFrame, str, str, str]:
    """Read a CSV, OFX/QFX, QIF or CAMT.053 statement into a text table.

    Parameters
    ----------
    raw : bytes
        The uploaded file content.
    skip_rows : int
        The number of leading lines to ignore (CSV only).

    Returns
    -------
    tuple of (DataFrame, str, str, str)
        The table, the delimiter (empty for non-CSV), the encoding and the
        format: ``csv``, ``ofx``, ``qif`` or ``camt``.
    """
    text, encoding = _decode(raw)
    fmt = statements.detect(text)
    if fmt is None:
        df, delimiter, encoding = read_csv(raw, skip_rows)
        return df, delimiter, encoding, "csv"
    try:
        rows = (statements.parse_camt(raw) if fmt == "camt" else
                statements.parse_ofx(text) if fmt == "ofx" else
                statements.parse_qif(text))
    except statements.StatementError as exc:
        raise ImportError_(str(exc)) from exc
    return (pd.DataFrame(rows, columns=statements.COLUMNS, dtype=str), "",
            encoding, fmt)


def structured_mapping() -> dict[str, str | bool | None]:
    """Return the fixed column mapping of OFX, QIF and CAMT statements."""
    return {"date_column": "Date", "amount_column": "Amount",
            "debit_column": None, "credit_column": None,
            "description_column": "Description", "merchant_column": "Payee",
            "decimal": ".", "date_format": "%Y-%m-%d", "dayfirst": False,
            "mostly_positive": False}


def _find(columns: list[str], kind: str, exclude: set[str]) -> str | None:
    for hint in _HINTS[kind]:
        for col in columns:
            if col not in exclude and hint in col.lower():
                return col
    return None


def guess_mapping(df: pd.DataFrame) -> dict[str, str | bool | None]:
    """Guess which columns hold date, description and amounts."""
    cols = list(df.columns)
    used: set[str] = set()
    guess: dict[str, str | bool | None] = {}
    for kind in ("date", "amount", "debit", "credit", "description",
                 "merchant"):
        col = _find(cols, kind, used)
        guess[f"{kind}_column"] = col
        if col:
            used.add(col)
    sample = " ".join(df.head(30).to_numpy().ravel().astype(str).tolist())
    guess["decimal"] = "," if re.search(r"\d,\d{2}(?!\d)", sample) and \
        not re.search(r"\d\.\d{2}(?!\d)", sample) else "."
    guess["mostly_positive"] = False
    if guess["amount_column"]:
        values = []
        for cell in df[guess["amount_column"]].head(200):
            try:
                v = parse_amount(cell, str(guess["decimal"]))
            except ValueError:
                continue
            if v:
                values.append(v)
        # Bank exports where purchases are positive need "invert signs".
        guess["mostly_positive"] = bool(values) and (
            sum(v > 0 for v in values) / len(values) > 0.7)
    return guess


def parse_amount(text: str, decimal: str = ".") -> Decimal | None:
    """Parse bank-style amounts such as ``1'234.50``, ``-12,30`` or
    ``(45.00)``.

    Parameters
    ----------
    text : str
        The raw cell text.
    decimal : str
        The decimal separator used in the file (``"."`` or ``","``).

    Returns
    -------
    Decimal or None
        The parsed amount, or ``None`` for an empty cell.
    """
    s = (text or "").strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")") or s.endswith("-")
    s = re.sub(r"[^\d,.\-+]", "", s.strip("()").rstrip("-"))
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    if not s or s in "+-":
        return None
    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"'{text}' is not a number") from exc
    return -abs(value) if negative else value


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def fingerprint(account_id: int, day: date, amount: Decimal,
                description: str, occurrence: int) -> str:
    """Return the de-duplication hash of an imported row."""
    key = (f"{account_id}|{day.isoformat()}|{amount:.2f}|"
           f"{_normalise(description)}|{occurrence}")
    return hashlib.sha256(key.encode()).hexdigest()


class Categorizer:
    """Assign categories with user rules, highest priority first.

    Parameters
    ----------
    db : Session
        The open database session used to load rules and categories.
    """

    def __init__(self, db: Session) -> None:
        self.rules = list(db.scalars(select(CategoryRule).order_by(
            CategoryRule.priority.desc(), CategoryRule.id)))
        self.kinds = dict(db.execute(
            select(Category.id, Category.kind)).all())
        self._regex = {r.id: re.compile(r.pattern, re.IGNORECASE)
                       for r in self.rules if r.is_regex}

    def match(self, description: str, merchant: str | None) -> int | None:
        """Return the category id of the first matching rule, if any."""
        for rule in self.rules:
            fields = {"description": [description],
                      "merchant": [merchant or ""],
                      "any": [description, merchant or ""]}
            for value in fields[rule.match_field]:
                if rule.is_regex:
                    if self._regex[rule.id].search(value):
                        return rule.category_id
                elif rule.pattern.lower() in value.lower():
                    return rule.category_id
        return None

    def kind_for(self, category_id: int | None, amount: Decimal) -> str:
        """Return the transaction kind implied by category and sign."""
        if category_id is not None and category_id in self.kinds:
            return self.kinds[category_id]
        return "income" if amount > 0 else "expense"


@dataclass
class ParsedRows:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_rows(df: pd.DataFrame, m: ImportMapping) -> ParsedRows:
    """Convert raw CSV rows into dated, signed amounts using ``m``.

    Parameters
    ----------
    df : DataFrame
        The raw table returned by ``read_csv``.
    m : ImportMapping
        The column mapping and parsing options.

    Returns
    -------
    ParsedRows
        The parsed rows and one message per row that failed.
    """
    needed = [m.date_column, m.description_column, m.amount_column,
              m.debit_column, m.credit_column, m.merchant_column]
    missing = [c for c in needed if c and c not in df.columns]
    if missing:
        raise ImportError_(
            f"Columns {missing} are not in the file. Re-run the preview "
            "and pick columns from the detected list.")
    if not m.amount_column and not (m.debit_column or m.credit_column):
        raise ImportError_(
            "No amount column was chosen. Select either an amount column "
            "or debit/credit columns.")
    out = ParsedRows()
    for idx, row in df.iterrows():
        line = int(idx) + 2 + m.skip_rows
        try:
            raw_date = row[m.date_column].strip()
            day = (pd.to_datetime(raw_date, format=m.date_format)
                   if m.date_format else
                   pd.to_datetime(raw_date, dayfirst=m.dayfirst))
            if pd.isna(day):
                raise ValueError(f"empty date '{raw_date}'")
            if m.amount_column:
                amount = parse_amount(row[m.amount_column], m.decimal)
            else:
                debit = parse_amount(row[m.debit_column], m.decimal) \
                    if m.debit_column else None
                credit = parse_amount(row[m.credit_column], m.decimal) \
                    if m.credit_column else None
                if debit is None and credit is None:
                    amount = None
                else:
                    amount = (credit or Decimal(0)) - abs(debit or 0)
            if amount is None or amount == 0:
                raise ValueError("amount is empty or zero")
            if m.invert_sign:
                amount = -amount
            out.rows.append({
                "line": line, "txn_date": day.date(),
                "amount": amount.quantize(Decimal("0.01")),
                "description": row[m.description_column].strip()[:500],
                "merchant": (row[m.merchant_column].strip()[:200] or None)
                if m.merchant_column else None})
        except (ValueError, TypeError) as exc:
            out.errors.append(f"Line {line}: {exc}")
    return out


def archive_original(raw: bytes, filename: str, sha256: str,
                     folder: Path) -> Path:
    """Store an unmodified, read-only copy of the uploaded file.

    Parameters
    ----------
    raw : bytes
        The uploaded file content.
    filename : str
        The original file name.
    sha256 : str
        The hex digest of ``raw``.
    folder : Path
        The archive directory.

    Returns
    -------
    Path
        The path of the archived copy.
    """
    safe = re.sub(r"[^\w.\-]+", "_", Path(filename).name)[:120]
    path = folder / f"{sha256[:16]}_{safe}"
    if not path.exists():
        path.write_bytes(raw)
        path.chmod(stat.S_IREAD | stat.S_IRGRP)
    return path


def commit_import(db: Session, raw: bytes, filename: str,
                  m: ImportMapping, archive_dir: Path,
                  skip_lines: set[int] | None = None) -> dict:
    """Import parsed rows as transactions and record an import batch.

    Parameters
    ----------
    db : Session
        The open database session.
    raw : bytes
        The uploaded file content.
    filename : str
        The original file name.
    m : ImportMapping
        The column mapping and parsing options.
    archive_dir : Path
        The directory for the read-only archived original.
    skip_lines : set of int, optional
        The file lines the user marked as duplicates in the review.

    Returns
    -------
    dict
        The counts of imported, duplicate and failed rows and messages.
    """
    sha = hashlib.sha256(raw).hexdigest()
    df = read_statement(raw, m.skip_rows)[0]
    parsed = parse_rows(df, m)
    archived = archive_original(raw, filename, sha, archive_dir)
    batch = ImportBatch(
        account_id=m.account_id, filename=filename[:260], sha256=sha,
        archived_path=str(archived), mapping_json=m.model_dump_json(),
        rows_total=len(df), rows_imported=0, rows_duplicate=0,
        rows_failed=len(parsed.errors))
    db.add(batch)
    db.flush()
    existing = set(db.scalars(select(Transaction.fingerprint).where(
        Transaction.account_id == m.account_id,
        Transaction.fingerprint.is_not(None))))
    categorizer = Categorizer(db)
    seen: dict[tuple, int] = {}
    categorized = 0
    skipped = 0
    for r in parsed.rows:
        key = (r["txn_date"], r["amount"], _normalise(r["description"]))
        seen[key] = seen.get(key, 0) + 1
        fp = fingerprint(m.account_id, r["txn_date"], r["amount"],
                         r["description"], seen[key])
        if fp in existing:
            batch.rows_duplicate += 1
            continue
        if skip_lines and r["line"] in skip_lines:
            batch.rows_duplicate += 1
            skipped += 1
            continue
        existing.add(fp)
        cat = categorizer.match(r["description"], r["merchant"])
        categorized += cat is not None
        db.add(Transaction(
            account_id=m.account_id, txn_date=r["txn_date"],
            amount=r["amount"], kind=categorizer.kind_for(cat, r["amount"]),
            description=r["description"], merchant=r["merchant"],
            category_id=cat, import_batch_id=batch.id, fingerprint=fp,
            category_source="rule" if cat is not None else None))
        batch.rows_imported += 1
    db.commit()
    return {"batch_id": batch.id, "rows_total": batch.rows_total,
            "rows_imported": batch.rows_imported,
            "rows_duplicate": batch.rows_duplicate,
            "rows_failed": batch.rows_failed, "errors": parsed.errors[:200],
            "rows_skipped": skipped, "categorized": categorized,
            "mapping": json.loads(batch.mapping_json)}


def check_import(db: Session, raw: bytes, m: ImportMapping) -> dict:
    """Sort the rows of a statement into new, duplicate and possible.

    *Duplicates* have the same fingerprint as an existing transaction and
    are always skipped. *Possible duplicates* share account, date and
    amount with an existing transaction but have a different description
    (banks sometimes change the text between exports); they are imported
    unless the user skips them.

    Parameters
    ----------
    db : Session
        The open database session.
    raw : bytes
        The uploaded file content.
    m : ImportMapping
        The confirmed column mapping.

    Returns
    -------
    dict
        Counts per group, the parse errors and one entry per possible
        duplicate with the incoming row next to the existing transaction.
    """
    parsed = parse_rows(read_statement(raw, m.skip_rows)[0], m)
    existing = {t.fingerprint: t for t in db.scalars(select(Transaction).where(
        Transaction.account_id == m.account_id,
        Transaction.fingerprint.is_not(None)))}
    seen: dict[tuple, int] = {}
    incoming, duplicates = [], 0
    matched: set[int] = set()
    for r in parsed.rows:
        key = (r["txn_date"], r["amount"], _normalise(r["description"]))
        seen[key] = seen.get(key, 0) + 1
        fp = fingerprint(m.account_id, r["txn_date"], r["amount"],
                         r["description"], seen[key])
        if fp in existing:
            duplicates += 1
            matched.add(existing[fp].id)
        else:
            incoming.append(r)
    candidates: dict[tuple, list[Transaction]] = {}
    if incoming:
        days = {r["txn_date"] for r in incoming}
        for t in db.scalars(select(Transaction).where(
                Transaction.account_id == m.account_id,
                Transaction.txn_date.in_(days)).order_by(Transaction.id)):
            if t.id not in matched:
                candidates.setdefault((t.txn_date, t.amount), []).append(t)
    possible = []
    for r in incoming:
        pool = candidates.get((r["txn_date"], r["amount"]))
        if not pool:
            continue
        t = pool.pop(0)
        possible.append({
            "line": r["line"], "txn_date": r["txn_date"].isoformat(),
            "amount": float(r["amount"]), "description": r["description"],
            "merchant": r["merchant"],
            "existing": {"id": t.id, "txn_date": t.txn_date.isoformat(),
                         "description": t.description,
                         "merchant": t.merchant}})
    return {"rows_total": len(parsed.rows) + len(parsed.errors),
            "rows_new": len(incoming) - len(possible),
            "rows_duplicate": duplicates, "rows_failed": len(parsed.errors),
            "errors": parsed.errors[:50], "possible": possible}
