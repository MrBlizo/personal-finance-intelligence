"""Money flow, balances over time, age of money and payee totals."""
from collections import deque
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import BigInteger, select, type_coerce
from sqlalchemy.orm import Session

from ..models import LIQUID_TYPES, Account, Transaction
from . import charts
from .fx import FxConverter
from .ledger import balances_on


def money_flow(df: pd.DataFrame, currency: str, top_n: int = 10) -> dict:
    """Sankey diagram: income sources → budget → spending and savings.

    Parameters
    ----------
    df : DataFrame
        Transactions from ``load_transactions`` (transfers excluded).
    currency : str
        The base currency.
    top_n : int
        The number of spending categories shown on their own; the rest
        are grouped as "Other spending".

    Returns
    -------
    dict
        The Plotly figure as JSON.
    """
    ok = df[df["amount_base"].notna()]
    inc = ok[ok["kind"] == "income"].groupby("top_category")[
        "amount_base"].sum()
    inc = inc[inc > 0].sort_values(ascending=False)
    exp = (-ok[ok["kind"] == "expense"].groupby("top_category")[
        "amount_base"].sum())
    exp = exp[exp > 0].sort_values(ascending=False)
    if inc.empty and exp.empty:
        return charts.empty("No income or spending in this period")
    if len(exp) > top_n:
        rest = pd.Series({"Other spending": exp.iloc[top_n:].sum()})
        exp = pd.concat([exp.iloc[:top_n], rest])
    total_in, total_out = float(inc.sum()), float(exp.sum())
    labels = [*inc.index, "Budget", *exp.index]
    hub = len(inc)
    src, dst, val, col = [], [], [], []
    for i, v in enumerate(inc):
        src.append(i), dst.append(hub), val.append(float(v))
        col.append("rgba(0,158,115,0.45)")
    for j, v in enumerate(exp):
        src.append(hub), dst.append(hub + 1 + j), val.append(float(v))
        col.append("rgba(213,94,0,0.40)")
    if total_in > total_out:
        labels.append("Saved")
        src.append(hub), dst.append(len(labels) - 1)
        val.append(total_in - total_out), col.append("rgba(0,114,178,0.45)")
    elif total_out > total_in:
        labels.append("From savings")
        src.append(len(labels) - 1), dst.append(hub)
        val.append(total_out - total_in), col.append("rgba(138,143,152,0.5)")
    node_col = ([charts.GREEN] * len(inc) + [charts.BLUE]
                + [charts.VERM] * len(exp)
                + ([charts.SKYBLUE] if len(labels) > hub + 1 + len(exp)
                   else []))
    fig = go.Figure(go.Sankey(
        arrangement="snap", valueformat=",.2f", valuesuffix=f" {currency}",
        node={"label": labels, "pad": 14, "thickness": 14,
              "color": node_col},
        link={"source": src, "target": dst, "value": val, "color": col}))
    return charts.to_json(charts._layout(fig, margin={
        "l": 8, "r": 8, "t": 8, "b": 8}))


def balance_history(db: Session, fx: FxConverter, base: str,
                    months: list[date]) -> dict:
    """Lines of each everyday account's balance at the end of each month.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The base currency.
    months : list of date
        The month-end dates to plot.

    Returns
    -------
    dict
        The Plotly figure as JSON (balances in the base currency).
    """
    accounts = list(db.scalars(select(Account).where(
        Account.type.in_(LIQUID_TYPES), Account.is_archived.is_(False))
        .order_by(Account.name)))
    if not accounts or not months:
        return charts.empty("Add an everyday account to see its balance")
    series: dict[int, list[float | None]] = {a.id: [] for a in accounts}
    for day, bal in zip(months, balances_on(db, months)):
        for a in accounts:
            rate = fx.try_rate(a.currency, base, day)
            opened = a.opening_date <= day
            series[a.id].append(float(bal[a.id]) * rate
                                if rate is not None and opened else None)
    fig = go.Figure([
        go.Scatter(x=months, y=series[a.id], name=a.name,
                   mode="lines+markers",
                   line={"color": charts.SERIES[i % len(charts.SERIES)]},
                   hovertemplate="%{y:,.2f}<extra>" + a.name + "</extra>")
        for i, a in enumerate(accounts)])
    fig.update_xaxes(tickformat="%b %Y")
    return charts.to_json(charts._layout(fig, base))


def age_of_money(db: Session, fx: FxConverter, base: str,
                 months: list[date], window: int = 10) -> dict:
    """How many days money sits in the everyday accounts before it is spent.

    Inflows (opening balances, income, refunds and transfers in) are
    queued in date order; each outflow uses the oldest money first. A
    spending's age is the number of days between the day that money came
    in and the day it went out, weighted by amount when one outflow uses
    several inflows. The age of money on a day is the average age of the
    last ``window`` outflows up to that day (YNAB's definition).

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The base currency.
    months : list of date
        The days on which to report the age.
    window : int
        The number of recent outflows averaged.

    Returns
    -------
    dict
        ``points`` (date and age in days, None before enough data), the
        latest ``age`` and the Plotly figure.
    """
    accounts = {a.id: a for a in db.scalars(select(Account).where(
        Account.type.in_(LIQUID_TYPES)))}
    events: list[tuple[date, int, float]] = []
    for a in accounts.values():
        rate = fx.try_rate(a.currency, base, a.opening_date)
        if rate is not None and a.opening_balance > 0:
            events.append((a.opening_date, 0, float(a.opening_balance)
                           * rate))
    # Plain columns: building 10,000s of ORM objects costs far more than
    # the walk below.
    T = Transaction
    txns = db.execute(select(
        T.txn_date, T.account_id, T.transfer_group,
        type_coerce(T.amount, BigInteger))
        .where(T.account_id.in_(list(accounts)))
        .order_by(T.txn_date, T.id)).all()
    legs: dict = {}
    for _, _, group, _ in txns:
        if group is not None:
            legs[group] = legs.get(group, 0) + 1
    for day, acc_id, group, cents in txns:
        # Moving money between two everyday accounts does not spend it.
        if group is not None and legs[group] > 1:
            continue
        rate = fx.try_rate(accounts[acc_id].currency, base, day)
        if rate is not None:
            # Inflows sort before outflows of the same day.
            amt = cents / 100 * rate
            events.append((day, 0 if amt > 0 else 1, amt))
    events.sort(key=lambda e: (e[0], e[1]))
    pool: deque[list] = deque()
    ages: list[tuple[date, float]] = []
    for day, _, amt in events:
        if amt > 0:
            pool.append([day, amt])
            continue
        need, weighted, used = -amt, 0.0, 0.0
        while need > 1e-9 and pool:
            first = pool[0]
            take = min(first[1], need)
            weighted += take * (day - first[0]).days
            used += take
            first[1] -= take
            need -= take
            if first[1] <= 1e-9:
                pool.popleft()
        if used > 0:
            ages.append((day, weighted / used))
    points = []
    for m in months:
        recent = [a for d, a in ages if d <= m][-window:]
        points.append({"date": m, "age": (round(sum(recent) / len(recent))
                                          if len(recent) >= window
                                          else None)})
    shown = [p for p in points if p["age"] is not None]
    if not shown:
        fig = charts.empty(
            f"Needs at least {window} payments from everyday accounts")
    else:
        fig = charts.to_json(charts._layout(go.Figure(go.Scatter(
            x=[p["date"] for p in shown], y=[p["age"] for p in shown],
            mode="lines+markers", line={"color": charts.BLUE, "width": 3},
            hovertemplate="%{y} days<extra>Age of money</extra>")),
            yaxis={"title": {"text": "Age of money / days"},
                   "rangemode": "tozero"},
            xaxis={"tickformat": "%b %Y"}))
    return {"points": points, "age": shown[-1]["age"] if shown else None,
            "figure": fig}


def payee_totals(exp: pd.DataFrame) -> list[dict]:
    """Return spending per payee: total, number of payments and average.

    The payee is the merchant, or the first 60 characters of the
    description when there is no merchant.
    """
    data = exp[exp["amount_base"].notna()]
    if data.empty:
        return []
    merchant = data["merchant"].fillna("")
    payee = merchant.where(merchant != "", data["description"].str[:60])
    g = data.groupby(payee).agg(total=("spend", "sum"),
                                count=("id", "nunique"),
                                last=("txn_date", "max"))
    g = g[g["total"] != 0].sort_values("total", ascending=False)
    return [{"payee": name, "total": float(r["total"]),
             "count": int(r["count"]),
             "average": float(r["total"]) / int(r["count"]),
             "last_date": r["last"].date()} for name, r in g.iterrows()]
