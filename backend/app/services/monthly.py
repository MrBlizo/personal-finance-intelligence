"""Month by month: what came in, what was spent and what was paid.

"Spent" is everything booked as an expense (consumption). "Paid" is the
part of the month that went to obligations: bills (expenses linked to a
recurring item) and payments into credit-card and loan accounts (transfers,
so they are not counted as spending twice). Money moved to savings or
investment accounts is reported as "Saved".
"""
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RecurringItem, Transaction
from .frame import expenses, incomes, load_transactions
from .fx import FxConverter
from .planning import add_months

DEBT_TYPES = ("credit_card", "loan")
SAVING_TYPES = ("savings", "investment")


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return add_months(_month_start(day), 1) - timedelta(days=1)


def _totals(df: pd.DataFrame, bills_ids: set[int]) -> dict:
    """Income, spent, paid and saved for the rows in ``df``."""
    exp = expenses(df)
    inc = float(incomes(df)["amount_base"].sum())
    spent = float(exp["spend"].sum())
    bills = float(exp[exp["id"].isin(bills_ids)]["spend"].sum())
    tr = df[(df["kind"] == "transfer") & df["amount_base"].notna()
            & (df["amount_base"] > 0)]
    debt = float(tr[tr["account_type"].isin(DEBT_TYPES)]["amount_base"].sum())
    saved = float(
        tr[tr["account_type"].isin(SAVING_TYPES)]["amount_base"].sum())
    return {"income": inc, "spent": spent, "bills": bills,
            "debt_payments": debt, "paid": bills + debt, "saved": saved,
            "net": inc - spent}


def _bill_ids(db: Session, start: date, end: date) -> dict[int, str]:
    """Transaction id -> recurring item name for bills in the period."""
    rows = db.execute(
        select(Transaction.id, RecurringItem.name)
        .join(RecurringItem, Transaction.recurring_id == RecurringItem.id)
        .where(Transaction.txn_date >= start, Transaction.txn_date <= end))
    return {tid: name for tid, name in rows}


def months_timeline(db: Session, fx: FxConverter, base: str,
                    months: int = 24, end: date | None = None) -> dict:
    """Totals for each of the last ``months`` months.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    months : int
        The number of months to return, oldest first.
    end : date, optional
        The day inside the last month to include (defaults to today).

    Returns
    -------
    dict
        ``currency`` and ``months``: one entry per month with ``month``
        (``YYYY-MM``), ``income``, ``spent``, ``bills``, ``debt_payments``,
        ``paid``, ``saved``, ``net`` and ``transactions``. Months before the
        first transaction are left out.
    """
    end = end or date.today()
    first = add_months(_month_start(end), -(months - 1))
    last = _month_end(end)
    df = load_transactions(db, fx, base, first, last, include_transfers=True)
    bills = set(_bill_ids(db, first, last))
    out = []
    if not df.empty:
        df["month"] = df["txn_date"].dt.strftime("%Y-%m")
        oldest = df["month"].min()
        for i in range(months):
            m = add_months(first, i).strftime("%Y-%m")
            if m < oldest:
                continue
            part = df[df["month"] == m]
            row = _totals(part, bills)
            row["month"] = m
            row["transactions"] = int(
                part[part["kind"] != "transfer"]["id"].nunique())
            out.append(row)
    return {"currency": base, "months": out,
            "missing_fx": df.attrs.get("missing_fx", [])}


def month_detail(db: Session, fx: FxConverter, base: str,
                 month: date) -> dict:
    """Everything about one month, compared with the month before.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    month : date
        Any day in the month to describe.

    Returns
    -------
    dict
        ``month`` (``YYYY-MM``), ``currency``, ``totals`` and
        ``previous`` (the same totals for the month before),
        ``categories`` (spending per top-level category with its share and
        the previous month's amount), ``bills`` (bills paid, with date and
        amount), ``debt_payments`` (payments per card or loan account),
        ``biggest`` (the five largest expenses) and ``daily`` (cumulative
        spending per day for this and the previous month; this month stops
        at today while it is still running) and ``days`` (days in the
        month).
    """
    start, end = _month_start(month), _month_end(month)
    pstart = add_months(start, -1)
    df = load_transactions(db, fx, base, pstart, end, include_transfers=True)
    names = _bill_ids(db, pstart, end)
    bills = set(names)
    if df.empty:
        df = df.assign(month=pd.Series(dtype=str))
    else:
        df["month"] = df["txn_date"].dt.strftime("%Y-%m")
    this = df[df["month"] == start.strftime("%Y-%m")]
    prev = df[df["month"] == pstart.strftime("%Y-%m")]

    exp, pexp = expenses(this), expenses(prev)
    total = float(exp["spend"].sum())
    by_cat = exp.groupby("top_category")["spend"].sum()
    p_cat = pexp.groupby("top_category")["spend"].sum()
    categories = [
        {"category": str(name), "amount": float(v),
         "share": float(v) / total if total > 0 else 0.0,
         "previous": float(p_cat.get(name, 0.0))}
        for name, v in by_cat.sort_values(ascending=False).items()
        if v > 0.005]

    bill_rows = exp[exp["id"].isin(bills)].sort_values("txn_date")
    bill_list = [
        {"name": names.get(int(r.id)) or r.description,
         "date": r.txn_date.date(), "amount": float(r.spend),
         "account": r.account_name}
        for r in bill_rows.itertuples()]

    tr = this[(this["kind"] == "transfer") & this["amount_base"].notna()
              & (this["amount_base"] > 0)
              & this["account_type"].isin(DEBT_TYPES)]
    debt = (tr.groupby("account_name")["amount_base"].sum()
            .sort_values(ascending=False))
    debt_list = [{"account": str(k), "amount": float(v)}
                 for k, v in debt.items()]

    big = exp.sort_values("spend", ascending=False).head(5)
    biggest = [
        {"id": int(r.id), "date": r.txn_date.date(),
         "description": r.merchant or r.description,
         "category": r.category, "amount": float(r.spend)}
        for r in big.itertuples() if r.spend > 0]

    def daily(part: pd.DataFrame, first: date) -> list[float]:
        days = (_month_end(first) - first).days + 1
        if part.empty:
            return [0.0] * days
        per_day = part.groupby(part["txn_date"].dt.day)["spend"].sum()
        run, out = 0.0, []
        for d in range(1, days + 1):
            run += float(per_day.get(d, 0.0))
            out.append(round(run, 2))
        return out

    this_daily = daily(exp, start)
    today = date.today()
    if start <= today <= end:
        this_daily = this_daily[:today.day]
    return {
        "month": start.strftime("%Y-%m"), "currency": base,
        "days": (end - start).days + 1,
        "totals": _totals(this, bills), "previous": _totals(prev, bills),
        "categories": categories, "bills": bill_list,
        "debt_payments": debt_list, "biggest": biggest,
        "daily": {"this": this_daily, "previous": daily(pexp, pstart)},
        "missing_fx": df.attrs.get("missing_fx", []),
    }
