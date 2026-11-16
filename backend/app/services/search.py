"""Search syntax for the transaction list.

Words are matched against description, payee and notes. Filters narrow the
list further; values with spaces go in quotes::

    payee:migros  category:food  account:"UBS card"  tag:holiday
    amount:>50  amount:<20  amount:12.50  amount:10..20
    before:2026-06-01  after:2026-01-01
    is:cleared  is:reconciled  is:uncategorized  is:unreviewed  is:split
    is:transfer  is:income  is:expense

``amount`` compares the size of the amount, so ``amount:>50`` finds both
spending and income above 50. Unknown filters are searched as text.
"""
import re
import shlex
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import Select, and_, func, or_, select, type_coerce

from ..models import (
    Account, Category, Money, Tag, Transaction, TransactionSplit,
    TransactionTag)

_NUM = r"\d+(?:[.,]\d+)?"
_AMOUNT = re.compile(
    rf"^(?P<op>[<>]=?|=)?(?P<a>{_NUM})(?:\.\.(?P<b>{_NUM}))?$")


@dataclass
class Query:
    """A parsed search: free words plus filters, and what could not be
    understood (reported back to the user)."""

    words: list[str] = field(default_factory=list)
    conditions: list = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _dec(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def _amount(value: str, q: Query) -> None:
    m = _AMOUNT.match(value.replace(" ", ""))
    if not m:
        q.problems.append(
            f"'amount:{value}' is not understood. Write amount:>50, "
            "amount:<20, amount:12.50 or amount:10..20.")
        return
    size = type_coerce(func.abs(Transaction.amount), Money)
    try:
        a = _dec(m["a"])
        if m["b"]:
            lo, hi = sorted((a, _dec(m["b"])))
            q.conditions.append(size.between(lo, hi))
            return
    except InvalidOperation:
        q.problems.append(f"'amount:{value}' is not a number.")
        return
    op = m["op"] or "="
    q.conditions.append({"<": size < a, "<=": size <= a, ">": size > a,
                         ">=": size >= a, "=": size == a}[op])


def _day(key: str, value: str, q: Query) -> None:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        q.problems.append(
            f"'{key}:{value}' needs a date like 2026-01-31.")
        return
    q.conditions.append(Transaction.txn_date < day if key == "before"
                        else Transaction.txn_date >= day)


_FLAGS = {
    "cleared": lambda: Transaction.cleared.is_(True),
    "reconciled": lambda: Transaction.reconciliation_id.is_not(None),
    "unreviewed": lambda: Transaction.reviewed.is_(False),
    "reviewed": lambda: Transaction.reviewed.is_(True),
    "transfer": lambda: Transaction.kind == "transfer",
    "income": lambda: Transaction.kind == "income",
    "expense": lambda: Transaction.kind == "expense",
    "split": lambda: Transaction.id.in_(
        select(TransactionSplit.transaction_id)),
    "uncategorized": lambda: and_(
        Transaction.category_id.is_(None), Transaction.kind != "transfer",
        Transaction.id.not_in(select(TransactionSplit.transaction_id))),
}


def parse(text: str) -> Query:
    """Split ``text`` into free words and filter conditions.

    Parameters
    ----------
    text : str
        The search typed by the user.

    Returns
    -------
    Query
        The words, SQL conditions and any parts that were not understood.
    """
    q = Query()
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.replace('"', " ").split()
    for tok in tokens:
        key, sep, value = tok.partition(":")
        key = key.lower()
        if not sep or not value:
            q.words.append(tok)
            continue
        like = f"%{value}%"
        if key == "payee":
            q.conditions.append(or_(Transaction.merchant.ilike(like),
                                    Transaction.description.ilike(like)))
        elif key == "category":
            ids = select(Category.id).where(Category.name.ilike(like))
            q.conditions.append(or_(
                Transaction.category_id.in_(ids),
                Transaction.category_id.in_(select(Category.id).where(
                    Category.parent_id.in_(ids))),
                Transaction.id.in_(select(TransactionSplit.transaction_id)
                                   .where(TransactionSplit.category_id
                                          .in_(ids)))))
        elif key == "account":
            q.conditions.append(Transaction.account_id.in_(
                select(Account.id).where(Account.name.ilike(like))))
        elif key == "tag":
            q.conditions.append(Transaction.id.in_(
                select(TransactionTag.transaction_id).join(Tag)
                .where(Tag.name.ilike(like))))
        elif key == "amount":
            _amount(value, q)
        elif key in ("before", "after"):
            _day(key, value, q)
        elif key == "is" and value.lower() in _FLAGS:
            q.conditions.append(_FLAGS[value.lower()]())
        elif key == "is":
            q.problems.append(
                f"'is:{value}' is not a known filter. Use one of: "
                + ", ".join(f"is:{k}" for k in _FLAGS) + ".")
        else:
            q.words.append(tok)
    return q


def apply(stmt: Select, text: str) -> tuple[Select, list[str]]:
    """Return ``stmt`` narrowed by the search, and the problems found.

    Parameters
    ----------
    stmt : Select
        The transaction query to narrow.
    text : str
        The search typed by the user.

    Returns
    -------
    tuple
        The narrowed statement and a list of messages about filters that
        were not understood.
    """
    q = parse(text)
    for word in q.words:
        like = f"%{word}%"
        stmt = stmt.where(or_(Transaction.description.ilike(like),
                              Transaction.merchant.ilike(like),
                              Transaction.notes.ilike(like)))
    for cond in q.conditions:
        stmt = stmt.where(cond)
    return stmt, q.problems
