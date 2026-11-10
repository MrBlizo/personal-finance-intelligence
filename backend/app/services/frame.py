"""Load transactions into a pandas DataFrame in the base currency."""
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account, Category, Tag, Transaction, TransactionSplit, TransactionTag)
from .fx import FxConverter

COLUMNS = ["id", "txn_date", "account_id", "account_name", "account_type",
           "currency", "amount", "amount_base", "kind", "category_id",
           "category", "top_category_id", "top_category", "description",
           "merchant", "transfer_group", "split", "tags"]


def load_transactions(db: Session, fx: FxConverter, base: str,
                      start: date | None = None, end: date | None = None,
                      include_transfers: bool = False) -> pd.DataFrame:
    """Return transactions with base-currency amounts and category names.

    Each amount is converted at the rate valid on its transaction date.
    Rows whose currency cannot be converted keep ``amount_base = NaN`` and
    their currency is listed in ``df.attrs["missing_fx"]``.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    start : date, optional
        The first date (inclusive) to load.
    end : date, optional
        The last date (inclusive) to load.
    include_transfers : bool
        The flag to keep transfers between own accounts.

    Returns
    -------
    DataFrame
        One row per transaction with the columns in ``COLUMNS``. A split
        transaction gives one row per part (same ``id``, ``split`` = True,
        the part's amount and category), so totals per category count each
        part where it belongs. ``tags`` holds the transaction's tag names.
    """
    stmt = (select(Transaction, Account).join(Account)
            .order_by(Transaction.txn_date, Transaction.id))
    if start:
        stmt = stmt.where(Transaction.txn_date >= start)
    if end:
        stmt = stmt.where(Transaction.txn_date <= end)
    if not include_transfers:
        stmt = stmt.where(Transaction.kind != "transfer")
    cats = {c.id: c for c in db.scalars(select(Category))}
    parts: dict[int, list[TransactionSplit]] = {}
    for sp in db.scalars(select(TransactionSplit).order_by(
            TransactionSplit.id)):
        parts.setdefault(sp.transaction_id, []).append(sp)
    tags: dict[int, list[str]] = {}
    for txn_id, name in db.execute(
            select(TransactionTag.transaction_id, Tag.name).join(Tag)
            .order_by(Tag.name)):
        tags.setdefault(txn_id, []).append(name)
    missing: set[str] = set()
    rows = []
    for t, a in db.execute(stmt):
        rate = fx.try_rate(a.currency, base, t.txn_date, missing)
        pieces = parts.get(t.id) or [None]
        for piece in pieces:
            cat_id = piece.category_id if piece else t.category_id
            amount = float(piece.amount if piece else t.amount)
            cat = cats.get(cat_id)
            top = cats.get(cat.parent_id) if cat and cat.parent_id else cat
            rows.append((
                t.id, t.txn_date, a.id, a.name, a.type, a.currency, amount,
                amount * rate if rate is not None else float("nan"),
                t.kind, cat_id,
                cat.name if cat else "Uncategorized",
                top.id if top else None,
                top.name if top else "Uncategorized",
                t.description, t.merchant, t.transfer_group,
                piece is not None, tags.get(t.id, [])))
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    # pandas 3 stores missing strings as NaN (a float); keep them as None so
    # that ``merchant or description`` style code keeps working.
    for col in ("merchant", "transfer_group"):
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    df.attrs["missing_fx"] = sorted(missing)
    return df


def expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Return expense rows with ``spend`` = positive money spent.

    Refunds booked to an expense category (positive amounts) reduce
    spending.
    """
    out = df[(df["kind"] == "expense") & df["amount_base"].notna()].copy()
    out["spend"] = -out["amount_base"]
    return out


def incomes(df: pd.DataFrame) -> pd.DataFrame:
    """Return income rows with base-currency amounts available."""
    return df[(df["kind"] == "income") & df["amount_base"].notna()].copy()
