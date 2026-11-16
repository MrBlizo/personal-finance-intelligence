"""Import a YNAB plan export (Register and Plan files, or their zip).

YNAB's web app exports two CSV (or TSV) files: the register, one row per
transaction or split part, and the plan, one row per month and category.
Accounts and categories are created by name; category groups become parent
categories. "Transfer : X" payees become transfers, split parts become one
split transaction, "Inflow: Ready to Assign" becomes income, and the plan's
assigned amounts become envelope assignments. Credit-card payment
categories are skipped (card payments are transfers here).
"""
import csv
import hashlib
import io
import re
import uuid
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account, Category, Transaction, TransactionSplit)
from . import envelope as env
from .fx import FxConverter
from .ledger import base_currency
from .prefs import put as put_pref

REGISTER_COLS = ("Account", "Date", "Payee", "Category Group", "Category",
                 "Memo", "Outflow", "Inflow")
INCOME_GROUPS = ("Inflow",)
SKIP_GROUPS = ("Credit Card Payments", "Hidden Categories",
               "Internal Master Category")
INCOME_CATEGORY = "Income"
_SPLIT = re.compile(r"^Split \((\d+)/(\d+)\)\s*", re.I)
_TRANSFER = re.compile(r"^Transfer\s*:\s*(.+)$", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
     "nov", "dec"), start=1)}


class YnabError(ValueError):
    """The files are not a YNAB export this importer understands."""


@dataclass
class Report:
    """What an import did (or would do in a dry run)."""

    accounts_created: list[str] = field(default_factory=list)
    categories_created: list[str] = field(default_factory=list)
    transactions: int = 0
    transfers: int = 0
    splits: int = 0
    duplicates: int = 0
    assignments: int = 0
    skipped: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)
    checked_month: str | None = None

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def read_files(data: bytes, name: str) -> dict[str, list[dict]]:
    """Return the register and plan rows from a zip or a single file.

    Parameters
    ----------
    data : bytes
        The uploaded file.
    name : str
        The uploaded file name (used to tell a zip from a table).

    Returns
    -------
    dict
        ``register`` and/or ``plan`` lists of rows keyed by column name.
    """
    tables: dict[str, list[dict]] = {}
    if name.lower().endswith(".zip") or data[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise YnabError(
                "The zip file is damaged. Export the plan from YNAB again "
                "and upload the new zip.") from exc
        for info in zf.infolist():
            if info.filename.lower().endswith((".csv", ".tsv", ".txt")):
                rows = _table(zf.read(info))
                kind = _kind(rows)
                if kind:
                    tables[kind] = rows
    else:
        rows = _table(data)
        kind = _kind(rows)
        if kind:
            tables[kind] = rows
    if "register" not in tables and "plan" not in tables:
        raise YnabError(
            "No YNAB register or plan was found. In YNAB's web app choose "
            "Export Plan, then upload the zip it downloads (or the "
            "'Register' and 'Plan' files inside it).")
    return tables


def _table(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in reader]


def _kind(rows: list[dict]) -> str | None:
    if not rows:
        return None
    cols = set(rows[0])
    if {"Account", "Outflow", "Inflow"} <= cols:
        return "register"
    if "Month" in cols and "Available" in cols:
        return "plan"
    return None


def parse_amount(text: str) -> Decimal:
    """Parse a YNAB money cell such as "$1,234.56", "1.234,56 €" or "0"."""
    s = re.sub(r"[^\d,.\-()]", "", text or "")
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if not s:
        return Decimal(0)
    last = max(s.rfind("."), s.rfind(","))
    if last != -1 and len(s) - last - 1 in (1, 2):
        whole, frac = s[:last], s[last + 1:]
    else:
        whole, frac = s, ""
    whole = re.sub(r"[.,]", "", whole)
    try:
        value = Decimal(f"{whole or 0}.{frac or 0}")
    except InvalidOperation as exc:
        raise YnabError(f"'{text}' is not an amount.") from exc
    return -value if neg else value


def _date_order(values: list[str]) -> str:
    firsts, seconds = [], []
    for v in values:
        parts = re.split(r"[./-]", v)
        if len(parts) == 3 and len(parts[0]) != 4:
            firsts.append(int(parts[0]))
            seconds.append(int(parts[1]))
    if any(f > 12 for f in firsts):
        return "dmy"
    if any(s > 12 for s in seconds):
        return "mdy"
    return "mdy"


def parse_date(text: str, order: str) -> date:
    """Parse a register date in YNAB's ISO, day-first or month-first form."""
    parts = re.split(r"[./-]", text.strip())
    try:
        if len(parts[0]) == 4:
            y, m, d = (int(p) for p in parts)
        elif order == "dmy":
            d, m, y = (int(p) for p in parts)
        else:
            m, d, y = (int(p) for p in parts)
        return date(y if y > 99 else 2000 + y, m, d)
    except (ValueError, IndexError) as exc:
        raise YnabError(
            f"'{text}' is not a date. Check the date format of the export "
            "(YNAB settings) and try again.") from exc


def parse_month(text: str) -> date:
    """Parse a plan month such as "Jan 2026", "January 2026" or "2026-01"."""
    t = text.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})", t)
    if m:
        return date(int(m[1]), int(m[2]), 1)
    m = re.match(r"^([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{4})$", t)
    if m and m[1].lower() in _MONTHS:
        return date(int(m[2]), _MONTHS[m[1].lower()], 1)
    m = re.match(r"^(\d{1,2})[./](\d{4})$", t)
    if m:
        return date(int(m[2]), int(m[1]), 1)
    raise YnabError(f"'{text}' is not a month this importer understands.")


class _Names:
    """Find or create accounts and categories by name."""

    def __init__(self, db: Session, currency: str, report: Report) -> None:
        self.db, self.currency, self.report = db, currency, report
        self.accounts = {a.name.lower(): a for a in db.scalars(
            select(Account))}
        self.cats = {(c.name.lower(), c.kind, c.parent_id): c
                     for c in db.scalars(select(Category))}
        self.by_name = {(c.name.lower(), c.kind): c
                        for c in db.scalars(select(Category))}

    def account(self, name: str, first_day: date) -> Account:
        acc = self.accounts.get(name.lower())
        if acc is None:
            acc = Account(name=name[:120], type="checking",
                          currency=self.currency, opening_balance=0,
                          opening_date=first_day,
                          notes="Imported from YNAB.")
            self.db.add(acc)
            self.db.flush()
            self.accounts[name.lower()] = acc
            self.report.accounts_created.append(name)
        return acc

    def category(self, group: str, name: str, kind: str = "expense"
                 ) -> Category:
        parent = None
        if group and group.lower() != name.lower():
            parent = self.by_name.get((group.lower(), kind))
            if parent is None:
                parent = self._make(group, kind, None)
        found = self.cats.get((name.lower(), kind,
                               parent.id if parent else None))
        if found is None:
            found = self.by_name.get((name.lower(), kind))
        return found or self._make(name, kind, parent)

    def _make(self, name: str, kind: str, parent: Category | None
              ) -> Category:
        cat = Category(name=name[:80], kind=kind,
                       parent_id=parent.id if parent else None)
        self.db.add(cat)
        self.db.flush()
        self.cats[(name.lower(), kind, cat.parent_id)] = cat
        self.by_name.setdefault((name.lower(), kind), cat)
        self.report.categories_created.append(
            f"{parent.name} › {name}" if parent else name)
        return cat


def _fingerprint(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return "ynab:" + hashlib.sha256(raw.encode()).hexdigest()[:59]


def import_export(db: Session, tables: dict[str, list[dict]],
                  currency: str, dry_run: bool = False) -> dict:
    """Import YNAB rows into the database.

    Parameters
    ----------
    db : Session
        The open database session.
    tables : dict
        The ``register`` and/or ``plan`` rows from ``read_files``.
    currency : str
        The currency of the accounts created.
    dry_run : bool
        The flag to roll everything back and only report what would
        happen.

    Returns
    -------
    dict
        The import report: what was created, skipped and, for the last
        month of the plan, categories whose available amount differs from
        YNAB's.
    """
    report = Report()
    names = _Names(db, currency, report)
    register = tables.get("register", [])
    if register:
        missing = [c for c in REGISTER_COLS if c not in register[0]]
        if missing:
            raise YnabError(
                "The register is missing the columns " + ", ".join(missing)
                + ". Upload the file from YNAB's Export Plan unchanged.")
        _import_register(db, names, register, report)
    plan = tables.get("plan", [])
    if plan:
        _import_plan(db, names, plan, report)
        put_pref(db, "budget_mode", "envelope")
    db.flush()
    if plan and report.checked_month:
        _compare(db, plan, report)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report.as_dict()


def _import_register(db: Session, names: _Names, rows: list[dict],
                     report: Report) -> None:
    order = _date_order([r["Date"] for r in rows])
    days = [parse_date(r["Date"], order) for r in rows]
    first_day = min(days) if days else date.today()
    existing = set(db.scalars(select(Transaction.fingerprint).where(
        Transaction.fingerprint.like("ynab:%"))))
    pending_transfers: dict[tuple, list[Transaction]] = defaultdict(list)
    i = 0
    while i < len(rows):
        row, day = rows[i], days[i]
        group = [(row, day)]
        m = _SPLIT.match(row.get("Memo", ""))
        if m and m[1] == "1":
            total = int(m[2])
            while len(group) < total and i + len(group) < len(rows):
                nxt = rows[i + len(group)]
                if not _SPLIT.match(nxt.get("Memo", "")) or \
                        nxt["Account"] != row["Account"]:
                    break
                group.append((nxt, days[i + len(group)]))
        i += len(group)
        acc = names.account(row["Account"], first_day)
        amounts = [parse_amount(r["Inflow"]) - parse_amount(r["Outflow"])
                   for r, _ in group]
        amount = sum(amounts, Decimal(0))
        if amount == 0:
            report.skipped.append(
                f"{row['Date']} {row['Payee']}: amount is zero")
            continue
        fp = _fingerprint(row["Account"], row["Date"], row["Payee"],
                          amount, row.get("Memo", ""), i)
        if fp in existing:
            report.duplicates += 1
            continue
        existing.add(fp)
        memo = _SPLIT.sub("", row.get("Memo", "")).strip()
        cleared = (row.get("Cleared", "").lower()
                   in ("cleared", "reconciled"))
        transfer = _TRANSFER.match(row["Payee"] or "")
        txn = Transaction(
            account_id=acc.id, txn_date=day, amount=amount,
            description=(row["Payee"] or memo or "YNAB")[:500],
            merchant=None if transfer else (row["Payee"] or None),
            notes=memo or None, fingerprint=fp, cleared=cleared,
            reviewed=True, kind="expense")
        if transfer and len(group) == 1:
            txn.kind = "transfer"
            other = transfer[1].strip().lower()
            key = (day, abs(amount),
                   tuple(sorted((row["Account"].lower(), other))))
            partners = pending_transfers[key]
            match = next((p for p in partners if p.amount == -amount), None)
            if match is not None:
                partners.remove(match)
                txn.transfer_group = match.transfer_group = uuid.uuid4()
                report.transfers += 1
            else:
                partners.append(txn)
            db.add(txn)
            report.transactions += 1
            continue
        parts = []
        for (r, _), part in zip(group, amounts):
            cat_group, cat_name = r["Category Group"], r["Category"]
            if cat_group in INCOME_GROUPS or (not cat_name and part > 0):
                parts.append((names.category("", INCOME_CATEGORY, "income"),
                              part))
            elif not cat_name or cat_group in SKIP_GROUPS:
                parts.append((None, part))
            else:
                parts.append((names.category(cat_group, cat_name), part))
        cats = {c.id if c else None for c, _ in parts}
        income = all(c is not None and c.kind == "income" for c, _ in parts)
        txn.kind = "income" if income else "expense"
        if len(parts) == 1 or len(cats) == 1:
            txn.category_id = parts[0][0].id if parts[0][0] else None
            db.add(txn)
        else:
            db.add(txn)
            db.flush()
            for cat, part in parts:
                if part:
                    db.add(TransactionSplit(
                        transaction_id=txn.id, amount=part,
                        category_id=cat.id if cat else None))
            report.splits += 1
        report.transactions += 1
    unpaired = sum(len(v) for v in pending_transfers.values())
    if unpaired:
        report.skipped.append(
            f"{unpaired} transfer(s) to accounts not in the export were "
            "kept as one-sided transfers.")


def _import_plan(db: Session, names: _Names, rows: list[dict],
                 report: Report) -> None:
    col = "Assigned" if "Assigned" in rows[0] else "Budgeted"
    if col not in rows[0]:
        raise YnabError(
            "The plan has no 'Assigned' (or 'Budgeted') column. Upload the "
            "Plan file from YNAB's Export Plan unchanged.")
    latest = None
    for r in rows:
        group, name = r.get("Category Group", ""), r.get("Category", "")
        if not name or group in INCOME_GROUPS or group in SKIP_GROUPS:
            continue
        month = parse_month(r["Month"])
        latest = max(latest, month) if latest else month
        amount = parse_amount(r[col])
        cat = names.category(group, name)
        if amount:
            env.set_assigned(db, cat.id, month, amount)
            report.assignments += 1
    report.checked_month = latest.isoformat()[:7] if latest else None


def _compare(db: Session, rows: list[dict], report: Report) -> None:
    month = date.fromisoformat(report.checked_month + "-01")
    view = env.month_view(db, FxConverter.from_db(db), base_currency(db),
                          month)
    ours = {i["name"].lower(): i["available"]
            for g in view["groups"] for i in g["items"]}
    for r in rows:
        group, name = r.get("Category Group", ""), r.get("Category", "")
        if not name or group in INCOME_GROUPS or group in SKIP_GROUPS:
            continue
        if parse_month(r["Month"]) != month:
            continue
        theirs = parse_amount(r.get("Available", "0"))
        mine = ours.get(name.lower(), Decimal(0))
        if abs(mine - theirs) >= Decimal("0.01"):
            report.differences.append({
                "category": f"{group} › {name}", "ynab": theirs,
                "pfi": mine, "difference": mine - theirs})
