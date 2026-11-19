"""Envelope (zero-based) budgeting: assign money, carry it over, cover gaps.

Only everyday accounts (checking, savings, cash, credit cards) take part.
For every month and expense category::

    available = carried over + assigned + activity

``activity`` is the category's spending (negative) and refunds (positive)
in the base currency. A positive ``available`` carries into the next month;
overspending (negative) does not: it is taken from Ready to Assign at the
start of the next month. With ``cash`` the balance of the everyday
accounts at the end of the month::

    ready to assign = cash - sum(available) - assigned in later months

so every unit of money is either in an envelope or waiting to be assigned.
Uncategorized spending is an envelope that can never receive money, which
makes it count as overspending. Amounts are exact decimals: each
transaction is converted at the rate of its date and rounded to cents.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import BigInteger, func, select, type_coerce
from sqlalchemy.orm import Session

from ..models import (
    LIQUID_TYPES, Account, BudgetAssignment, BudgetTarget, Category,
    Transaction, TransactionSplit)
from .fx import FxConverter
from .planning import add_months

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
#: The key used for spending without a category.
UNCATEGORIZED = 0


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _dec(cents) -> Decimal:
    return Decimal(int(cents or 0)).scaleb(-2)


def _month(text: str) -> date:
    return date(int(text[:4]), int(text[5:7]), 1)


def month_start(day: date) -> date:
    """Return the first day of the month of ``day``."""
    return day.replace(day=1)


@dataclass
class Ledger:
    """Monthly assigned and activity amounts per category, in base money."""

    cash: dict[date, Decimal] = field(default_factory=dict)
    activity: dict[tuple[int, date], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: ZERO))
    assigned: dict[tuple[int, date], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: ZERO))
    first_month: date | None = None
    missing_fx: set[str] = field(default_factory=set)


def _rate(fx: FxConverter, cur: str, base: str, on: date,
          missing: set[str]) -> Decimal | None:
    if cur == base:
        return Decimal(1)
    rate = fx.try_rate(cur, base, on, missing)
    return None if rate is None else Decimal(str(rate))


def build_ledger(db: Session, fx: FxConverter, base: str) -> Ledger:
    """Read assignments and everyday-account money flows from the database.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The budget currency.

    Returns
    -------
    Ledger
        Activity per (category, month), assignments per (category, month)
        and the net cash change per month (opening balances in the month
        of their opening date).
    """
    led = Ledger()
    cats = {c.id: c for c in db.scalars(select(Category))}
    flow: dict[date, Decimal] = defaultdict(lambda: ZERO)
    accounts = {a.id: a for a in db.scalars(
        select(Account).where(Account.type.in_(LIQUID_TYPES)))}
    for a in accounts.values():
        rate = _rate(fx, a.currency, base, a.opening_date, led.missing_fx)
        if rate is not None and a.opening_balance:
            flow[month_start(a.opening_date)] += _cents(
                a.opening_balance * rate)
    parts: dict[int, list[TransactionSplit]] = defaultdict(list)
    for sp in db.scalars(select(TransactionSplit)):
        parts[sp.transaction_id].append(sp)

    def add_activity(month, kind, cat_id, amount):
        cat = cats.get(cat_id) if cat_id else None
        if cat is not None and cat.kind != "expense":
            return
        if cat is None and kind != "expense":
            return
        key = cat.id if cat is not None else UNCATEGORIZED
        led.activity[(key, month)] += amount

    # Same-currency accounts need no conversion or rounding, so their
    # money is summed per month (and category) by the database. Splits and
    # other currencies keep the per-transaction conversion below.
    T = Transaction
    raw = type_coerce(T.amount, BigInteger)
    same = [a for a, acc in accounts.items() if acc.currency == base]
    other = [a for a in accounts if a not in same]
    if same:
        ym = func.substr(T.txn_date, 1, 7)
        for m, cents in db.execute(select(ym, func.sum(raw)).where(
                T.account_id.in_(same)).group_by(ym)):
            flow[_month(m)] += _dec(cents)
        for m, kind, cat_id, cents in db.execute(
                select(ym, T.kind, T.category_id, func.sum(raw)).where(
                    T.account_id.in_(same), T.kind != "transfer",
                    T.id.not_in(list(parts)))
                .group_by(ym, T.kind, T.category_id)):
            add_activity(_month(m), kind, cat_id, _dec(cents))
    split_same = [i for i in parts] if same else []
    rows = db.execute(select(
        T.id, T.account_id, T.txn_date, T.kind, T.category_id, raw).where(
        (T.account_id.in_(other)) | (T.account_id.in_(same)
                                     & T.id.in_(split_same))))
    for tid, acc_id, day, kind, cat_id, cents in rows:
        acc = accounts[acc_id]
        rate = _rate(fx, acc.currency, base, day, led.missing_fx)
        if rate is None:
            continue
        month = month_start(day)
        if acc.currency != base:
            flow[month] += _cents(_dec(cents) * rate)
        if kind == "transfer":
            continue
        for p_cat, amount in ([(p.category_id, p.amount) for p in
                               parts[tid]] or [(cat_id, _dec(cents))]):
            add_activity(month, kind, p_cat, _cents(amount * rate))
    for a in db.scalars(select(BudgetAssignment)):
        led.assigned[(a.category_id, a.month)] += a.amount
    months = [m for m in flow] + [m for _, m in led.assigned]
    led.first_month = min(months) if months else None
    running = ZERO
    for m in sorted(flow):
        running += flow[m]
        led.cash[m] = running
    return led


def _cash_at(led: Ledger, month: date) -> Decimal:
    best = ZERO
    for m in sorted(led.cash):
        if m > month:
            break
        best = led.cash[m]
    return best


def target_need(target: BudgetTarget | None, month: date,
                carry_in: Decimal) -> Decimal:
    """Return how much a category should receive in ``month``.

    Parameters
    ----------
    target : BudgetTarget or None
        The category's target; no target means no need.
    month : date
        The first day of the month.
    carry_in : Decimal
        The money carried into the month (used by ``by_date`` targets).

    Returns
    -------
    Decimal
        The amount to assign this month to stay on track (>= 0).
    """
    if target is None:
        return ZERO
    if target.kind == "monthly":
        return target.amount
    if target.kind == "yearly":
        return _cents(target.amount / 12)
    if target.kind == "weekly":
        weekday = target.due_date.weekday() if target.due_date else 0
        nxt = add_months(month, 1)
        days = (nxt - month).days
        count = sum(1 for d in range(days)
                    if (month.toordinal() + d) % 7 == (weekday + 1) % 7)
        return target.amount * count
    due = month_start(target.due_date) if target.due_date else month
    left = max((due.year - month.year) * 12 + due.month - month.month + 1, 1)
    remaining = max(target.amount - carry_in, ZERO)
    return _cents(remaining / left)


def month_view(db: Session, fx: FxConverter, base: str, month: date) -> dict:
    """Return the envelope budget of ``month``.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The budget currency.
    month : date
        Any day of the month to show.

    Returns
    -------
    dict
        ``ready_to_assign``, ``assigned_in_future``, totals and the
        categories grouped by parent, each with assigned, activity,
        available, carry-in, target need and status.
    """
    month = month_start(month)
    led = build_ledger(db, fx, base)
    cats = {c.id: c for c in db.scalars(
        select(Category).where(Category.kind == "expense"))}
    targets = {t.category_id: t for t in db.scalars(select(BudgetTarget))}
    keys = sorted(set(cats) | {UNCATEGORIZED})
    carry = {k: ZERO for k in keys}
    available = dict(carry)
    start = led.first_month or month
    m = min(start, month)
    while m <= month:
        for k in keys:
            available[k] = (carry[k] + led.assigned[(k, m)]
                            + led.activity[(k, m)])
        if m < month:
            carry = {k: max(v, ZERO) for k, v in available.items()}
        m = add_months(m, 1)
    future = sum((v for (k, mm), v in led.assigned.items() if mm > month),
                 ZERO)
    ready = _cash_at(led, month) - sum(available.values(), ZERO) - future

    def row(k: int) -> dict:
        cat = cats.get(k)
        tgt = targets.get(k)
        assigned = led.assigned[(k, month)]
        need = target_need(tgt, month, carry[k])
        status = ("overspent" if available[k] < 0 else
                  "underfunded" if tgt and assigned < need else
                  "funded" if tgt else "ok")
        return {
            "category_id": k or None,
            "name": cat.name if cat else "Uncategorized",
            "parent_id": cat.parent_id if cat else None,
            "icon": cat.icon if cat else None,
            "color": cat.color if cat else None,
            "carry_in": carry[k], "assigned": assigned,
            "activity": led.activity[(k, month)], "available": available[k],
            "target": None if tgt is None else {
                "kind": tgt.kind, "amount": tgt.amount,
                "due_date": tgt.due_date},
            "need": need, "shortfall": max(need - assigned, ZERO),
            "status": status}

    children: dict[int, list[Category]] = defaultdict(list)
    tops = []
    for c in cats.values():
        if c.parent_id in cats:
            children[c.parent_id].append(c)
        else:
            tops.append(c)
    groups = []
    for top in sorted(tops, key=lambda c: c.name.lower()):
        kids = sorted(children[top.id], key=lambda c: c.name.lower())
        groups.append({"id": top.id, "name": top.name,
                       "items": [row(top.id)] + [row(c.id) for c in kids]})
    if led.activity[(UNCATEGORIZED, month)] or available[UNCATEGORIZED]:
        groups.append({"id": None, "name": None,
                       "items": [row(UNCATEGORIZED)]})
    rows = [i for g in groups for i in g["items"]]
    return {
        "month": month.isoformat()[:7], "currency": base,
        "ready_to_assign": ready, "assigned_in_future": future,
        "total_assigned": sum((i["assigned"] for i in rows), ZERO),
        "total_activity": sum((i["activity"] for i in rows), ZERO),
        "total_available": sum((i["available"] for i in rows), ZERO),
        "overspent": sum((-i["available"] for i in rows
                          if i["available"] < 0), ZERO),
        "underfunded": sum((i["shortfall"] for i in rows), ZERO),
        "groups": groups, "missing_fx": sorted(led.missing_fx)}


def set_assigned(db: Session, category_id: int, month: date,
                 amount: Decimal) -> None:
    """Set the money assigned to a category in a month (caller commits).

    Parameters
    ----------
    db : Session
        The open database session.
    category_id : int
        The expense category.
    month : date
        Any day of the month.
    amount : Decimal
        The new assigned amount (may be negative after moving money out).
    """
    month = month_start(month)
    row = db.scalar(select(BudgetAssignment).where(
        BudgetAssignment.category_id == category_id,
        BudgetAssignment.month == month))
    if row is None:
        db.add(BudgetAssignment(category_id=category_id, month=month,
                                amount=amount))
    else:
        row.amount = amount


def assigned_of(db: Session, category_id: int, month: date) -> Decimal:
    """Return the amount assigned to a category in a month."""
    row = db.scalar(select(BudgetAssignment.amount).where(
        BudgetAssignment.category_id == category_id,
        BudgetAssignment.month == month_start(month)))
    return row if row is not None else ZERO


def move(db: Session, month: date, amount: Decimal,
         from_id: int | None, to_id: int | None) -> None:
    """Move money between categories, or to/from Ready to Assign (None).

    Parameters
    ----------
    db : Session
        The open database session.
    month : date
        Any day of the month.
    amount : Decimal
        The positive amount to move.
    from_id : int or None
        The category giving money, or None for Ready to Assign.
    to_id : int or None
        The category receiving money, or None for Ready to Assign.
    """
    if from_id is not None:
        set_assigned(db, from_id, month,
                     assigned_of(db, from_id, month) - amount)
    if to_id is not None:
        set_assigned(db, to_id, month, assigned_of(db, to_id, month) + amount)


def quick_assign(db: Session, fx: FxConverter, base: str, month: date,
                 mode: str) -> list[dict]:
    """Propose assignments for a month without saving them.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The budget currency.
    month : date
        Any day of the month.
    mode : str
        ``"underfunded"`` gives each category with a target what it still
        needs this month, in category order, while Ready to Assign lasts;
        ``"last_month"`` repeats last month's assignments where this month
        has none.

    Returns
    -------
    list of dict
        One change per category: ``category_id``, ``name``, ``old`` and
        ``new`` assigned amounts.
    """
    month = month_start(month)
    view = month_view(db, fx, base, month)
    rows = [i for g in view["groups"] for i in g["items"]
            if i["category_id"] is not None]
    changes = []
    if mode == "underfunded":
        budget = max(view["ready_to_assign"], ZERO)
        for i in rows:
            give = min(i["shortfall"], budget)
            if give > 0:
                budget -= give
                changes.append({"category_id": i["category_id"],
                                "name": i["name"], "old": i["assigned"],
                                "new": i["assigned"] + give})
    elif mode == "last_month":
        prev = add_months(month, -1)
        for i in rows:
            before = assigned_of(db, i["category_id"], prev)
            if i["assigned"] == 0 and before != 0:
                changes.append({"category_id": i["category_id"],
                                "name": i["name"], "old": ZERO,
                                "new": before})
    else:
        raise ValueError(
            f"Unknown quick-assign mode {mode!r}. Use 'underfunded' or "
            "'last_month'.")
    return changes
