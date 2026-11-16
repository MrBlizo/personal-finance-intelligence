"""Period budgets, IOUs and loan schedules."""
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Category, Iou, IouPayment, PeriodBudget, PeriodBudgetCategory, Tag)
from .frame import expenses, load_transactions
from .fx import FxConverter
from .planning import add_months

#: Past periods shown under each weekly or monthly budget.
HISTORY = 6


def period_window(pb: PeriodBudget, k: int) -> tuple[date, date]:
    """Return the first and last day of the ``k``-th period of a budget.

    Parameters
    ----------
    pb : PeriodBudget
        The budget.
    k : int
        The period index; 0 starts on ``start_date``.

    Returns
    -------
    tuple of date
        The inclusive bounds of the period.
    """
    if pb.period == "custom":
        return pb.start_date, pb.end_date
    if pb.period == "weekly":
        first = pb.start_date + timedelta(days=7 * k)
        return first, first + timedelta(days=6)
    day = pb.start_date.day
    first = add_months(pb.start_date, k, anchor_day=day)
    return first, add_months(pb.start_date, k + 1, anchor_day=day) \
        - timedelta(days=1)


def current_index(pb: PeriodBudget, today: date) -> int:
    """Return the index of the period containing ``today`` (0 if before)."""
    if pb.period == "custom" or today <= pb.start_date:
        return 0
    if pb.period == "weekly":
        return (today - pb.start_date).days // 7
    k = (today.year - pb.start_date.year) * 12 + today.month \
        - pb.start_date.month
    while k > 0 and period_window(pb, k)[0] > today:
        k -= 1
    while period_window(pb, k)[1] < today:
        k += 1
    return k


def _spent(df: pd.DataFrame, cat_ids: set[int], tag: str | None,
           first: date, last: date) -> float:
    rows = df[(df["txn_date"] >= pd.Timestamp(first))
              & (df["txn_date"] <= pd.Timestamp(last))]
    if cat_ids:
        rows = rows[rows["category_id"].isin(cat_ids)
                    | rows["top_category_id"].isin(cat_ids)]
    if tag:
        rows = rows[rows["tags"].apply(lambda names: tag in names)]
    return float(rows["spend"].sum())


def period_budgets(db: Session, fx: FxConverter, base: str,
                   today: date | None = None) -> list[dict]:
    """Return every period budget with its current and past periods.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The budget currency.
    today : date, optional
        The reference day (defaults to today).

    Returns
    -------
    list of dict
        Per budget: its settings, the current period (spent, remaining,
        percentage, days left and what can still be spent per day) and up
        to ``HISTORY`` earlier periods.
    """
    today = today or date.today()
    budgets = list(db.scalars(select(PeriodBudget).order_by(
        PeriodBudget.name)))
    if not budgets:
        return []
    links: dict[int, set[int]] = defaultdict(set)
    for link in db.scalars(select(PeriodBudgetCategory)):
        links[link.period_budget_id].add(link.category_id)
    tags = {t.id: t.name for t in db.scalars(select(Tag))}
    names = {c.id: c.name for c in db.scalars(select(Category))}
    first_day = min(b.start_date for b in budgets)
    df = expenses(load_transactions(db, fx, base, first_day, None))
    out = []
    for b in budgets:
        cats = links[b.id]
        tag = tags.get(b.tag_id) if b.tag_id else None
        k = current_index(b, today)
        first, last = period_window(b, k)
        spent = _spent(df, cats, tag, first, last)
        limit = float(b.amount)
        days_left = max((last - max(today, first)).days + 1, 0) \
            if today <= last else 0
        history = []
        for j in range(max(k - HISTORY, 0), k):
            f, la = period_window(b, j)
            history.append({"start": f, "end": la,
                            "spent": _spent(df, cats, tag, f, la)})
        out.append({
            "id": b.id, "name": b.name, "amount": limit,
            "period": b.period, "start_date": b.start_date,
            "end_date": b.end_date, "tag_id": b.tag_id, "tag": tag,
            "category_ids": sorted(cats),
            "categories": sorted(names[c] for c in cats if c in names),
            "notes": b.notes, "currency": base,
            "current": {
                "start": first, "end": last, "spent": spent,
                "remaining": limit - spent,
                "pct": max(spent, 0.0) / limit if limit else None,
                "days_left": days_left,
                "per_day": ((limit - spent) / days_left
                            if days_left and spent < limit else 0.0),
                "upcoming": today < first, "ended": today > last},
            "history": history})
    return out


def iou_summary(db: Session, fx: FxConverter, base: str) -> dict:
    """Return all IOUs with what is still open, and totals per person.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for the totals in the base currency.
    base : str
        The reporting currency.

    Returns
    -------
    dict
        ``items`` (each IOU with its payments and ``open`` amount),
        ``people`` (net balance per person in base money; positive means
        they owe you) and the totals owed to you and by you.
    """
    paid: dict[int, list[IouPayment]] = defaultdict(list)
    for p in db.scalars(select(IouPayment).order_by(IouPayment.paid_on)):
        paid[p.iou_id].append(p)
    items, people = [], defaultdict(float)
    owed_to_me = owed_by_me = 0.0
    missing: set[str] = set()
    for i in db.scalars(select(Iou).order_by(Iou.settled_on.is_not(None),
                                             Iou.iou_date.desc())):
        repaid = sum((p.amount for p in paid[i.id]), Decimal(0))
        left = max(i.amount - repaid, Decimal(0))
        rate = fx.try_rate(i.currency, base, date.today(), missing)
        left_base = float(left) * rate if rate is not None else None
        sign = 1 if i.direction == "lent" else -1
        if left_base is not None and i.settled_on is None:
            people[i.person] += sign * left_base
            if sign > 0:
                owed_to_me += left_base
            else:
                owed_by_me += left_base
        items.append({
            "id": i.id, "person": i.person, "direction": i.direction,
            "amount": float(i.amount), "currency": i.currency,
            "iou_date": i.iou_date, "due_date": i.due_date, "note": i.note,
            "settled_on": i.settled_on, "repaid": float(repaid),
            "open": float(left) if i.settled_on is None else 0.0,
            "overdue": (i.settled_on is None and i.due_date is not None
                        and i.due_date < date.today()),
            "payments": [{"id": p.id, "paid_on": p.paid_on,
                          "amount": float(p.amount), "note": p.note}
                         for p in paid[i.id]]})
    return {"currency": base, "items": items,
            "people": [{"person": k, "balance": v} for k, v in
                       sorted(people.items(), key=lambda kv: -abs(kv[1]))
                       if abs(v) >= 0.005],
            "owed_to_me": owed_to_me, "owed_by_me": owed_by_me,
            "missing_fx": sorted(missing)}


def amortization(balance: float, apr: float, payment: float,
                 start: date, max_months: int = 600) -> dict:
    """Return the month-by-month schedule of paying off one loan.

    Interest is charged monthly at ``apr / 12``.

    Parameters
    ----------
    balance : float
        The amount owed now (positive).
    apr : float
        The annual interest rate in percent.
    payment : float
        The fixed monthly payment.
    start : date
        The month of the first payment.
    max_months : int
        The longest schedule computed before giving up.

    Returns
    -------
    dict
        ``rows`` (date, payment, interest, principal, balance),
        ``months``, ``total_interest`` and ``payoff_date``;
        ``never`` is True when the payment does not cover the interest.
    """
    rate = apr / 100 / 12
    rows, left, total_interest = [], balance, 0.0
    if balance <= 0:
        return {"rows": [], "months": 0, "total_interest": 0.0,
                "payoff_date": start, "never": False}
    if payment <= left * rate + 1e-9:
        return {"rows": [], "months": None, "total_interest": None,
                "payoff_date": None, "never": True}
    for n in range(max_months):
        interest = round(left * rate, 2)
        pay = min(payment, left + interest)
        principal = pay - interest
        left = round(left - principal, 2)
        total_interest += interest
        rows.append({"date": add_months(start, n), "payment": round(pay, 2),
                     "interest": interest,
                     "principal": round(principal, 2), "balance": left})
        if left <= 0.005:
            break
    return {"rows": rows, "months": len(rows),
            "total_interest": round(total_interest, 2),
            "payoff_date": rows[-1]["date"] if rows else start,
            "never": left > 0.005}


def payment_to_finish(balance: float, apr: float, months: int) -> float:
    """Return the fixed monthly payment that clears a loan in ``months``.

    Parameters
    ----------
    balance : float
        The amount owed now (positive).
    apr : float
        The annual interest rate in percent.
    months : int
        The number of monthly payments (at least 1).

    Returns
    -------
    float
        The payment, rounded up to the cent.
    """
    months = max(months, 1)
    rate = apr / 100 / 12
    if rate == 0:
        pay = balance / months
    else:
        pay = balance * rate / (1 - (1 + rate) ** -months)
    return math.ceil(pay * 100 - 1e-6) / 100
