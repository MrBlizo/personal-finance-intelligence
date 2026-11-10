"""Debt payoff simulation and the spending calendar.

The payoff plan is an estimate in the reporting currency: interest is
charged monthly at ``apr / 12`` on the remaining balance, every debt gets
its minimum payment, and in the avalanche and snowball strategies the rest
of the monthly budget (minimums of all debts plus the extra amount) goes to
one target debt at a time. Minimums of paid-off debts roll over to the next
target. "minimum" pays only each debt's own minimum.
"""
import calendar as cal
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

MAX_MONTHS = 600
CENT = 0.005


@dataclass
class Debt:
    """One debt for the payoff simulation (amounts in reporting currency).

    Attributes
    ----------
    account_id : int
        The account the debt belongs to.
    name : str
        The account name shown in the plan.
    owed : float
        The amount owed today.
    apr : float
        The annual interest rate in percent.
    min_payment : float
        The minimum monthly payment.
    """

    account_id: int
    name: str
    owed: float
    apr: float
    min_payment: float


@dataclass
class Plan:
    """Result of ``payoff_plan``."""

    strategy: str
    months: int | None
    interest: float
    paid: float
    debts: list[dict] = field(default_factory=list)
    schedule: list[float] = field(default_factory=list)

    def to_dict(self, start: date) -> dict:
        """Return the plan with payoff dates counted from ``start``.

        Parameters
        ----------
        start : date
            The month the payments start in.
        """
        def when(months):
            if months is None:
                return None
            index = start.year * 12 + start.month - 1 + months
            return date(index // 12, index % 12 + 1, 1)
        return {
            "strategy": self.strategy, "months": self.months,
            "payoff_date": when(self.months),
            "interest": round(self.interest, 2), "paid": round(self.paid, 2),
            "debts": [{**d, "payoff_date": when(d["payoff_month"])}
                      for d in self.debts],
            "schedule": [round(x, 2) for x in self.schedule],
        }


def _order(strategy: str, debts: list[Debt], left: dict[int, float]):
    open_ = [d for d in debts if left[d.account_id] > CENT]
    if strategy == "avalanche":
        return sorted(open_, key=lambda d: (-d.apr, left[d.account_id]))
    return sorted(open_, key=lambda d: (left[d.account_id], -d.apr))


def payoff_plan(debts: list[Debt], extra: float, strategy: str) -> Plan:
    """Simulate paying off ``debts`` month by month.

    Parameters
    ----------
    debts : list of Debt
        The debts with a positive amount owed.
    extra : float
        The amount paid each month on top of all minimum payments.
    strategy : {"avalanche", "snowball", "minimum"}
        The order in which extra money is applied: highest interest first,
        smallest balance first, or no extra money at all.

    Returns
    -------
    Plan
        ``months`` is ``None`` when a debt is never paid off within
        50 years (the payments do not cover the interest).
    """
    left = {d.account_id: d.owed for d in debts}
    interest = {d.account_id: 0.0 for d in debts}
    done: dict[int, int | None] = {d.account_id: None for d in debts}
    budget = sum(d.min_payment for d in debts)
    if strategy != "minimum":
        budget += extra
    paid_total, schedule, month = 0.0, [], 0
    while any(v > CENT for v in left.values()) and month < MAX_MONTHS:
        month += 1
        spent = 0.0
        for d in debts:
            if left[d.account_id] <= CENT:
                continue
            charge = left[d.account_id] * d.apr / 1200
            left[d.account_id] += charge
            interest[d.account_id] += charge
            pay = min(left[d.account_id], d.min_payment)
            left[d.account_id] -= pay
            spent += pay
        if strategy != "minimum":
            pool = budget - spent
            for d in _order(strategy, debts, left):
                if pool <= CENT:
                    break
                pay = min(left[d.account_id], pool)
                left[d.account_id] -= pay
                pool -= pay
                spent += pay
        paid_total += spent
        for d in debts:
            if done[d.account_id] is None and left[d.account_id] <= CENT:
                done[d.account_id] = month
                left[d.account_id] = 0.0
        schedule.append(sum(left.values()))
    finished = all(v is not None for v in done.values())
    rows = sorted(({"account_id": d.account_id, "name": d.name,
                    "payoff_month": done[d.account_id],
                    "interest": round(interest[d.account_id], 2)}
                   for d in debts),
                  key=lambda r: (r["payoff_month"] is None,
                                 r["payoff_month"] or 0))
    return Plan(strategy, month if finished and debts else
                (0 if not debts else None),
                sum(interest.values()), paid_total, rows, schedule)


def calendar(exp: pd.DataFrame, inc: pd.DataFrame, year: int,
             today: date | None = None) -> dict:
    """Return daily spending of ``year`` and a year-in-review summary.

    Parameters
    ----------
    exp : DataFrame
        Expense rows from ``frame.expenses`` (column ``spend``), covering
        ``year`` and the year before.
    inc : DataFrame
        Income rows from ``frame.incomes``, same period.
    year : int
        The calendar year shown.
    today : date, optional
        The reference day (defaults to today); a running year is only
        counted up to it.

    Returns
    -------
    dict
        ``days`` (date, spend, income per active day), ``max_spend`` and
        ``review`` with totals, averages, the top categories, the largest
        expense, monthly totals and the change against the previous year.
    """
    today = today or date.today()

    def of(df, y):
        if df.empty:
            return df
        d = pd.to_datetime(df["txn_date"])
        out = df[d.dt.year == y].copy()
        out["txn_date"] = d[d.dt.year == y].dt.date
        return out

    e, i = of(exp, year), of(inc, year)
    e_prev, i_prev = of(exp, year - 1), of(inc, year - 1)
    spend_day = (e.groupby("txn_date")["spend"].sum() if not e.empty
                 else pd.Series(dtype=float))
    income_day = (i.groupby("txn_date")["amount_base"].sum() if not i.empty
                  else pd.Series(dtype=float))
    days = sorted(set(spend_day.index) | set(income_day.index))
    out_days = [{"date": d, "spend": round(float(spend_day.get(d, 0)), 2),
                 "income": round(float(income_day.get(d, 0)), 2)}
                for d in days]
    end = min(date(year, 12, 31), today) if year >= today.year \
        else date(year, 12, 31)
    elapsed = max((end - date(year, 1, 1)).days + 1, 0) \
        if year <= today.year else 0
    spend, income = float(e["spend"].sum()), float(i["amount_base"].sum())
    spend_prev = float(e_prev["spend"].sum())
    income_prev = float(i_prev["amount_base"].sum())
    months = []
    for m in range(1, 13):
        em = e[pd.to_datetime(e["txn_date"]).dt.month == m] \
            if not e.empty else e
        im = i[pd.to_datetime(i["txn_date"]).dt.month == m] \
            if not i.empty else i
        months.append({"month": m, "name": cal.month_abbr[m],
                       "spend": round(float(em["spend"].sum()), 2)
                       if not em.empty else 0.0,
                       "income": round(float(im["amount_base"].sum()), 2)
                       if not im.empty else 0.0})
    active = [m for m in months if m["spend"] or m["income"]]
    top, biggest, weekday = [], None, None
    if not e.empty:
        by_cat = e.groupby(e["top_category"].fillna("Uncategorized"))[
            "spend"].sum().sort_values(ascending=False)
        top = [{"category": k, "spend": round(float(v), 2),
                "share": round(float(v) / spend, 4) if spend else 0.0}
               for k, v in by_cat.head(5).items() if v > 0]
        per_txn = e.groupby("id").agg(
            spend=("spend", "sum"), txn_date=("txn_date", "first"),
            description=("description", "first"),
            merchant=("merchant", "first"))
        row = per_txn.sort_values("spend", ascending=False).iloc[0]
        if row["spend"] > 0:
            biggest = {"date": row["txn_date"],
                       "description": row["merchant"] or row["description"],
                       "spend": round(float(row["spend"]), 2)}
        wd = spend_day.groupby(
            pd.to_datetime(pd.Series(spend_day.index)).dt.dayofweek.values
        ).sum()
        if not wd.empty and wd.max() > 0:
            weekday = int(wd.idxmax())
    spend_days = int((spend_day > 0).sum())

    def change(now, before):
        return round((now - before) / before, 4) if before else None

    return {
        "days": out_days,
        "max_spend": round(float(spend_day.max()), 2)
        if not spend_day.empty else 0.0,
        "review": {
            "spend": round(spend, 2), "income": round(income, 2),
            "net": round(income - spend, 2),
            "savings_rate": round((income - spend) / income, 4)
            if income > 0 else None,
            "days": elapsed, "spend_days": spend_days,
            "no_spend_days": max(elapsed - spend_days, 0),
            "daily_average": round(spend / elapsed, 2) if elapsed else 0.0,
            "top_categories": top, "biggest": biggest,
            "busiest_weekday": weekday,
            "months": months,
            "highest_month": max(active, key=lambda m: m["spend"])["month"]
            if active else None,
            "lowest_month": min(active, key=lambda m: m["spend"])["month"]
            if active else None,
            "previous": {"spend": round(spend_prev, 2),
                         "income": round(income_prev, 2),
                         "spend_change": change(spend, spend_prev),
                         "income_change": change(income, income_prev)},
        },
    }
