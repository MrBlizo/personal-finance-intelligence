"""Recurring auto-posting and bill reminders.

An item with ``auto_post`` books one transaction per due date, from the day
after ``last_posted`` up to today. Each posting carries a fingerprint
``rec:<item>:<date>`` so a date is never booked twice, even if
``last_posted`` is lost (e.g. after restoring an older backup).
"""
import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Category, RecurringItem, Setting, Transaction
from ..seed import get_setting
from .planning import occurrences

NOTIFIED_KEY = "notified_reminders"
NOTIFIED_KEEP = 300


def enable_auto_post(item: RecurringItem, today: date) -> None:
    """Start posting from the next due date, never backfilling history.

    Parameters
    ----------
    item : RecurringItem
        The item whose ``auto_post`` flag was just switched on.
    today : date
        The current date.
    """
    if item.last_posted is None or item.last_posted < today - timedelta(1):
        item.last_posted = max(item.start_date - timedelta(1),
                               today - timedelta(1))


def post_due(db: Session, today: date | None = None) -> list[int]:
    """Book every due occurrence of auto-posting recurring items.

    Parameters
    ----------
    db : Session
        The open database session; the caller commits.
    today : date, optional
        The posting date limit (inclusive); defaults to today.

    Returns
    -------
    list of int
        The ids of the transactions that were created.
    """
    today = today or date.today()
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    created = []
    items = db.scalars(select(RecurringItem).where(
        RecurringItem.auto_post.is_(True), RecurringItem.is_active.is_(True)))
    for item in items:
        start = (item.last_posted or item.start_date - timedelta(1)) \
            + timedelta(1)
        for day in occurrences(item, start, today):
            fp = f"rec:{item.id}:{day.isoformat()}"
            exists = db.scalar(select(Transaction.id).where(
                Transaction.account_id == item.account_id,
                Transaction.fingerprint == fp))
            if exists is None:
                kind = kinds.get(item.category_id) or (
                    "income" if item.amount > 0 else "expense")
                t = Transaction(
                    account_id=item.account_id, txn_date=day,
                    amount=item.amount, kind=kind, description=item.name,
                    category_id=item.category_id, fingerprint=fp,
                    recurring_id=item.id, category_source="recurring",
                    notes="Posted automatically from a recurring item.")
                db.add(t)
                db.flush()
                created.append(t.id)
            item.last_posted = day
    return created


def upcoming(db: Session, today: date | None = None,
             horizon: int | None = None) -> list[dict]:
    """List recurring payments due soon.

    Parameters
    ----------
    db : Session
        The open database session.
    today : date, optional
        The reference date; defaults to today.
    horizon : int, optional
        The look-ahead in days; defaults to each item's ``remind_days``.

    Returns
    -------
    list of dict
        One entry per due date, sorted by date, with a stable ``key``.
    """
    today = today or date.today()
    out = []
    items = db.scalars(select(RecurringItem).where(
        RecurringItem.is_active.is_(True)))
    accounts = {a.id: a for a in db.scalars(select(Account))}
    for item in items:
        days = horizon if horizon is not None else item.remind_days
        if days <= 0:
            continue
        for day in occurrences(item, today, today + timedelta(days)):
            acc = accounts.get(item.account_id)
            out.append({
                "key": f"{item.id}:{day.isoformat()}", "item_id": item.id,
                "name": item.name, "date": day, "amount": float(item.amount),
                "currency": acc.currency if acc else "",
                "account": acc.name if acc else "",
                "days_left": (day - today).days,
                "auto_post": item.auto_post})
    return sorted(out, key=lambda r: (r["date"], r["name"]))


def take_notifications(db: Session, today: date | None = None) -> list[dict]:
    """Return reminders not shown yet and remember them as shown.

    Parameters
    ----------
    db : Session
        The open database session; the caller commits.
    today : date, optional
        The reference date; defaults to today.

    Returns
    -------
    list of dict
        The reminders the desktop shell should show as notifications.
    """
    seen = json.loads(get_setting(db, NOTIFIED_KEY, "[]") or "[]")
    fresh = [r for r in upcoming(db, today) if r["key"] not in seen]
    if fresh:
        keep = (seen + [r["key"] for r in fresh])[-NOTIFIED_KEEP:]
        row = db.get(Setting, NOTIFIED_KEY)
        if row is None:
            db.add(Setting(key=NOTIFIED_KEY, value=json.dumps(keep)))
        else:
            row.value = json.dumps(keep)
    return fresh
