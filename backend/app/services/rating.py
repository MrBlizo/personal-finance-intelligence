"""When to ask for a Microsoft Store rating.

PFI asks once, in the app, after it has been used for ``MIN_DAYS`` days and
holds at least ``MIN_TRANSACTIONS`` real (non-demo) transactions. The
answer is kept in the ``rating_prompt`` preference:

``""``
    Not asked yet.
``"later:<YYYY-MM-DD>"``
    Closed once with "Not now"; asked again after ``SNOOZE_DAYS`` days.
``"rated"``, ``"declined"``, ``"dismissed"``
    Final: the prompt never shows again ("dismissed" is a second
    "Not now").
"""
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, SchemaVersion, Transaction
from . import prefs

KEY = "rating_prompt"
MIN_DAYS = 14
MIN_TRANSACTIONS = 20
SNOOZE_DAYS = 30
OUTCOMES = ("rated", "declined", "later")


def first_use(db: Session) -> date | None:
    """Return the day this database was created (its first migration)."""
    first = db.scalar(select(func.min(SchemaVersion.applied_at)))
    if first is None:
        return None
    if isinstance(first, str):
        first = datetime.fromisoformat(first)
    return first.date()


def real_transactions(db: Session) -> int:
    """Return the number of transactions outside the demo accounts."""
    return int(db.scalar(
        select(func.count(Transaction.id))
        .join(Account, Account.id == Transaction.account_id)
        .where(Account.is_demo.is_(False))) or 0)


def status(db: Session, today: date | None = None) -> dict:
    """Return whether the rating prompt should show now.

    Parameters
    ----------
    db : Session
        The database session.
    today : date, optional
        The reference day (defaults to today).

    Returns
    -------
    dict
        ``due`` (bool), ``state`` (the stored answer), ``days_used`` and
        ``transactions``.
    """
    today = today or date.today()
    state = prefs.get(db, KEY)
    started = first_use(db)
    days = (today - started).days if started else 0
    count = real_transactions(db)
    due = days >= MIN_DAYS and count >= MIN_TRANSACTIONS
    if state in ("rated", "declined", "dismissed"):
        due = False
    elif state.startswith("later:"):
        try:
            asked = date.fromisoformat(state.split(":", 1)[1])
        except ValueError:
            asked = today
        due = due and (today - asked).days >= SNOOZE_DAYS
    return {"due": due, "state": state, "days_used": days,
            "transactions": count}


def record(db: Session, outcome: str, today: date | None = None) -> str:
    """Store the user's answer and return the new state.

    Parameters
    ----------
    db : Session
        The database session; committed here.
    outcome : str
        The answer: "rated", "declined" or "later".
    today : date, optional
        The reference day (defaults to today).

    Returns
    -------
    str
        The stored state.

    Raises
    ------
    ValueError
        If ``outcome`` is not one of ``OUTCOMES``.
    """
    if outcome not in OUTCOMES:
        raise ValueError(
            f"Unknown rating answer '{outcome}'. Use one of "
            f"{', '.join(OUTCOMES)}.")
    today = today or date.today()
    current = prefs.get(db, KEY)
    if outcome == "later":
        new = "dismissed" if current.startswith("later:") \
            else f"later:{today.isoformat()}"
    else:
        new = outcome
    prefs.put(db, KEY, new)
    db.commit()
    return new
