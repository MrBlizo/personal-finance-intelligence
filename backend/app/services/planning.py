"""Recurring schedules, budget status and savings-goal progress."""
import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account, Budget, Category, RecurringItem, SavingsGoal, Transaction)
from .frame import expenses, load_transactions
from .fx import FxConverter
from .ledger import account_balances

STEP_DAYS = {"weekly": 7, "biweekly": 14}
STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


def add_months(day: date, months: int, anchor_day: int | None = None
               ) -> date:
    """Add calendar months, clamping the day to the month length.

    Parameters
    ----------
    day : date
        The starting date.
    months : int
        The number of months to add (may be negative).
    anchor_day : int, optional
        The preferred day of month (defaults to ``day.day``).

    Returns
    -------
    date
        The shifted date.
    """
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(anchor_day or day.day, last))


def occurrences(item: RecurringItem, start: date, end: date) -> list[date]:
    """Return the dates of ``item`` within ``[start, end]``.

    Parameters
    ----------
    item : RecurringItem
        The recurring income or expense.
    start : date
        The first date (inclusive).
    end : date
        The last date (inclusive).

    Returns
    -------
    list of date
        The occurrence dates in ascending order.
    """
    last = min(end, item.end_date) if item.end_date else end
    out: list[date] = []
    n = 0
    while True:
        if item.frequency in STEP_DAYS:
            day = item.start_date + timedelta(
                days=n * STEP_DAYS[item.frequency])
        else:
            day = add_months(item.start_date,
                             n * STEP_MONTHS[item.frequency],
                             item.start_date.day)
        if day > last:
            return out
        if day >= start:
            out.append(day)
        n += 1


def next_occurrence(item: RecurringItem, today: date) -> date | None:
    """Return the next date on or after ``today``, if any."""
    found = occurrences(item, today, today + timedelta(days=400))
    return found[0] if found else None


def month_bounds(month: date) -> tuple[date, date]:
    """Return the first and last day of the month containing ``month``."""
    first = month.replace(day=1)
    return first, add_months(first, 1) - timedelta(days=1)


def budget_status(db: Session, fx: FxConverter, base: str, month: date,
                  today: date | None = None) -> dict:
    """Compare each budget with actual spending in ``month``.

    Spending of child categories counts toward a parent's budget. For the
    current month, a linear end-of-month projection is added.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting (and budget) currency.
    month : date
        Any date in the month to evaluate.
    today : date, optional
        The reference date for the projection (defaults to today).

    Returns
    -------
    dict
        The month, totals and one entry per budget.
    """
    today = today or date.today()
    first, last = month_bounds(month)
    df = expenses(load_transactions(db, fx, base, first, last))
    by_cat = df.groupby("category_id")["spend"].sum().to_dict()
    by_top = df.groupby("top_category_id")["spend"].sum().to_dict()
    elapsed = (min(today, last) - first).days + 1 if today >= first else 0
    span = (last - first).days + 1
    items = []
    for b in db.scalars(select(Budget).join(Category).order_by(
            Category.name)):
        is_parent = b.category.parent_id is None
        spent = float(by_top.get(b.category_id, 0.0) if is_parent
                      else by_cat.get(b.category_id, 0.0))
        limit = float(b.monthly_amount)
        running = first <= today <= last and elapsed
        projected = max(spent / elapsed * span if running else spent, 0.0)
        items.append({
            "id": b.id, "category_id": b.category_id,
            "category": b.category.name, "budget": limit,
            "spent": spent, "remaining": limit - spent,
            # Net refunds can make "spent" negative; progress starts at 0.
            "pct": max(spent, 0.0) / limit if limit else None,
            "projected": projected,
            "status": ("over" if spent > limit else
                       "at_risk" if projected > limit else "ok")})
    return {"month": first.isoformat()[:7], "currency": base,
            "days_elapsed": elapsed, "days_in_month": span,
            "total_budget": sum(i["budget"] for i in items),
            "total_spent": sum(i["spent"] for i in items),
            "items": items, "missing_fx": df.attrs.get("missing_fx", [])}


def goal_progress(db: Session, fx: FxConverter, goal: SavingsGoal,
                  today: date | None = None) -> dict:
    """Return progress, required monthly saving and projected finish.

    If the goal is linked to an account, the account balance is the
    amount saved and the average net inflow of the last 90 days is the
    saving rate. Otherwise ``saved_amount`` is used and no rate is known.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter between account and goal currencies.
    goal : SavingsGoal
        The goal to evaluate.
    today : date, optional
        The reference date (defaults to today).

    Returns
    -------
    dict
        The goal fields plus computed progress indicators.
    """
    today = today or date.today()
    saved, monthly_rate, note = float(goal.saved_amount), None, None
    if goal.account_id:
        acc = db.get(Account, goal.account_id)
        bal = account_balances(db).get(acc.id, 0)
        rate = fx.try_rate(acc.currency, goal.currency)
        if rate is None:
            note = (f"No {acc.currency}->{goal.currency} rate; showing the "
                    "manual saved amount.")
        else:
            saved = float(bal) * rate
            since = today - timedelta(days=90)
            flows = db.scalars(select(Transaction.amount).where(
                Transaction.account_id == acc.id,
                Transaction.txn_date > since,
                Transaction.txn_date <= today)).all()
            monthly_rate = float(sum(flows)) * rate / 3.0
    target = float(goal.target_amount)
    remaining = max(target - saved, 0.0)
    months_left = ((goal.target_date - today).days / 30.4375
                   if goal.target_date else None)
    required = (remaining / months_left if months_left and months_left > 0
                else (remaining if months_left is not None else None))
    projected = None
    if remaining == 0:
        projected = today
    elif monthly_rate and monthly_rate > 0:
        projected = today + timedelta(days=remaining / monthly_rate
                                      * 30.4375)
    if remaining == 0:
        status = "completed"
    elif goal.target_date is None:
        status = "no_deadline"
    elif goal.target_date < today:
        status = "overdue"
    elif monthly_rate is None:
        status = "manual"
    else:
        status = "on_track" if monthly_rate >= (required or 0) else "behind"
    return {
        "id": goal.id, "name": goal.name, "currency": goal.currency,
        "target_amount": target, "target_date": goal.target_date,
        "account_id": goal.account_id, "saved_amount": saved,
        "manual_saved_amount": float(goal.saved_amount),
        "priority": goal.priority, "notes": goal.notes,
        "progress": min(saved / target, 1.0) if target else 0.0,
        "remaining": remaining, "months_left": months_left,
        "required_monthly": required, "recent_monthly_saving": monthly_rate,
        "projected_completion": projected, "status": status, "note": note}
