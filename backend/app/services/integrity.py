"""Check my data: find inconsistencies that would make figures wrong.

Every finding says what is wrong, why it matters and how to fix it, and
lists the affected transaction ids so the screen can link to them. Only
one kind of problem is repaired automatically (a category of the wrong kind,
which is cleared so the transaction shows up as uncategorised); everything
else is left for the user to decide.
"""
from collections import defaultdict

from sqlalchemy import BigInteger, func, select, type_coerce
from sqlalchemy.orm import Session

from ..models import (
    Account, Category, RecurringItem, Transaction, TransactionSplit)


def _issue(code: str, level: str, title: str, detail: str, fix: str,
           ids: list[int], fixable: bool = False) -> dict:
    return {"code": code, "level": level, "title": title, "detail": detail,
            "fix": fix, "transaction_ids": ids[:200], "count": len(ids),
            "fixable": fixable}


def check(db: Session) -> dict:
    """Run every check and return the findings.

    Parameters
    ----------
    db : Session
        The open database session.

    Returns
    -------
    dict
        ``ok`` (True when nothing was found), ``issues`` (a list of
        findings with ``code``, ``level`` ("error" or "warning"),
        ``title``, ``detail``, ``fix``, ``transaction_ids``, ``count`` and
        ``fixable``) and ``checked`` (how many transactions were checked).
    """
    issues: list[dict] = []
    conn = db.connection()
    integrity = conn.exec_driver_sql("PRAGMA integrity_check").scalar()
    if integrity != "ok":
        issues.append(_issue(
            "file", "error", "The database file is damaged",
            f"SQLite reported: {integrity}.",
            "Restore the latest backup (Settings › Backups), then import "
            "anything added since.", []))
    broken_fk = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if broken_fk:
        tables = sorted({row[0] for row in broken_fk})
        issues.append(_issue(
            "links", "error", "Records point to rows that no longer exist",
            f"{len(broken_fk)} rows in {', '.join(tables)} reference "
            "deleted records.",
            "Restore a backup, or contact support with this message.", []))

    T = Transaction
    cents = type_coerce(T.amount, BigInteger)
    # Transfers: two legs per group that cancel out (same currency).
    legs: dict = defaultdict(list)
    for tid, group, amount, cur in db.execute(
            select(T.id, T.transfer_group, cents, Account.currency)
            .join(Account).where(T.transfer_group.is_not(None))):
        legs[group].append((tid, amount, cur))
    lonely, unequal = [], []
    for parts in legs.values():
        if len(parts) != 2:
            lonely += [p[0] for p in parts]
        elif parts[0][2] == parts[1][2] and parts[0][1] + parts[1][1] != 0:
            unequal += [p[0] for p in parts]
    if lonely:
        issues.append(_issue(
            "transfer_legs", "error", "Transfers with a missing side",
            "A transfer moves money between two of your accounts, so it "
            "needs a matching transaction in the other account. These "
            "transfers have only one side, so one account balance is off.",
            "Open each one and either delete it or change it to an expense "
            "or income.", lonely))
    if unequal:
        issues.append(_issue(
            "transfer_amounts", "error", "Transfers whose sides don't match",
            "Both sides of a transfer in the same currency should be the "
            "same amount with opposite signs.",
            "Edit one side so the amounts match.", unequal))
    orphans = list(db.scalars(select(T.id).where(
        T.kind == "transfer", T.transfer_group.is_(None))))
    if orphans:
        issues.append(_issue(
            "transfer_orphan", "warning",
            "Transfers not linked to any account",
            "These are marked as transfers but have no other side, so they "
            "are left out of income and spending.",
            "Change them to an expense or income, or delete them.", orphans))

    # Splits must add up to the transaction.
    split_sum = (select(TransactionSplit.transaction_id,
                        func.sum(type_coerce(TransactionSplit.amount,
                                             BigInteger)).label("s"))
                 .group_by(TransactionSplit.transaction_id).subquery())
    bad_splits = list(db.scalars(
        select(T.id).join(split_sum, split_sum.c.transaction_id == T.id)
        .where(split_sum.c.s != cents)))
    if bad_splits:
        issues.append(_issue(
            "splits", "error", "Splits that don't add up",
            "The parts of a split transaction should add up to its amount; "
            "the difference is missing from your category totals.",
            "Open the transaction and adjust the split parts.", bad_splits))

    # Category of the wrong kind (an expense filed under an income category).
    kinds = {c.id: c.kind for c in db.scalars(select(Category))}
    wrong = [tid for tid, kind, cat in db.execute(
        select(T.id, T.kind, T.category_id)
        .where(T.category_id.is_not(None), T.kind != "transfer"))
        if kinds.get(cat) and kinds[cat] != kind]
    if wrong:
        issues.append(_issue(
            "category_kind", "warning",
            "Categories of the wrong kind",
            "These expenses are filed under an income category (or the "
            "other way round), so they count in the wrong total.",
            "Fix clears the category so the transactions appear in "
            "Transactions › To review.", wrong, fixable=True))

    # Recurring items on archived accounts keep reminding you.
    archived = {a.id for a in db.scalars(
        select(Account).where(Account.is_archived.is_(True)))}
    stale = [r.name for r in db.scalars(select(RecurringItem).where(
        RecurringItem.is_active.is_(True))) if r.account_id in archived]
    if stale:
        issues.append(_issue(
            "recurring_archived", "warning",
            "Bills linked to archived accounts",
            "Still active: " + ", ".join(sorted(stale)[:10]) + ".",
            "Move them to an open account or pause them in Bills & "
            "recurring.", []))

    checked = db.scalar(select(func.count(T.id))) or 0
    return {"ok": not issues, "issues": issues, "checked": int(checked)}


def fix(db: Session, code: str) -> int:
    """Repair one automatically fixable finding.

    Parameters
    ----------
    db : Session
        The open database session.
    code : str
        The finding's ``code``; only ``category_kind`` can be repaired.

    Returns
    -------
    int
        The number of transactions changed.

    Raises
    ------
    ValueError
        If the finding cannot be repaired automatically.
    """
    if code != "category_kind":
        raise ValueError(
            f"'{code}' can't be fixed automatically because it needs your "
            "decision. Open the listed transactions and correct them.")
    ids = next((i["transaction_ids"] for i in check(db)["issues"]
                if i["code"] == code), [])
    changed = 0
    for txn in db.scalars(select(Transaction).where(Transaction.id.in_(ids))):
        txn.category_id = None
        txn.category_source = None
        txn.reviewed = False
        changed += 1
    db.commit()
    return changed
