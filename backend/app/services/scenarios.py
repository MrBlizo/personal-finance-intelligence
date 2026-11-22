"""What-if scenarios on the cash-flow forecast, and financial independence.

Both are projections built on assumptions, not observations; the screens
say so next to every figure.
"""
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, RecurringItem
from .forecast import cash_flow_forecast
from .frame import expenses, incomes, load_transactions
from .fx import FxConverter
from .ledger import net_worth
from .planning import add_months, occurrences


def _adjustments(db: Session, fx: FxConverter, base: str, changes: list,
                 today: date, horizon: int) -> tuple[np.ndarray, list]:
    """Daily base-currency flows added by the scenario's changes."""
    adj = np.zeros(horizon)
    end = today + timedelta(days=horizon)
    labels = []

    def put(day: date, value: float) -> None:
        i = (day - today).days - 1
        if 0 <= i < horizon:
            adj[i] += value

    for ch in changes:
        kind = ch.get("kind")
        start = date.fromisoformat(ch["start"]) if ch.get("start") else (
            today + timedelta(days=1))
        if kind == "monthly":
            amount, i = float(ch["amount"]), 0
            while (day := add_months(start, i)) <= end:
                put(day, amount)
                i += 1
            labels.append(ch.get("label") or "Monthly change")
        elif kind == "once":
            put(start, float(ch["amount"]))
            labels.append(ch.get("label") or "One-off")
        elif kind == "recurring_pct":
            item = db.get(RecurringItem, int(ch["recurring_id"]))
            if item is None:
                raise ValueError(
                    f"Bill or income {ch['recurring_id']} no longer "
                    "exists. Pick another one from the list.")
            acc = db.get(Account, item.account_id)
            rate = fx.try_rate(acc.currency, base) if acc else None
            if rate is None:
                raise ValueError(
                    f"No exchange rate from the currency of {item.name} to "
                    f"{base}. Add one under Settings › Exchange rates.")
            extra = float(item.amount) * rate * float(ch["pct"]) / 100
            for day in occurrences(item, max(start, today + timedelta(1)),
                                   end):
                put(day, extra)
            labels.append(ch.get("label") or item.name)
        else:
            raise ValueError(
                f"Unknown change '{kind}'. Use monthly, once or "
                "recurring_pct.")
    return adj, labels


def what_if(db: Session, fx: FxConverter, base: str, changes: list,
            horizon_days: int = 365, lookback_days: int = 180,
            threshold: float = 0.0, today: date | None = None) -> dict:
    """Compare the forecast with and without some changes.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    changes : list of dict
        Each change is ``{"kind": "monthly", "amount": 300}`` (every month,
        positive = more money), ``{"kind": "once", "amount": -25000,
        "start": "2027-03-01"}`` (a one-off purchase) or
        ``{"kind": "recurring_pct", "recurring_id": 4, "pct": 10}`` (a bill
        or income changes by a percentage). ``start`` and ``label`` are
        optional.
    horizon_days : int
        The number of days to project.
    lookback_days : int
        The number of past days used to learn spending.
    threshold : float
        The balance that should not be crossed.
    today : date, optional
        The forecast origin.

    Returns
    -------
    dict
        ``dates``, the ``baseline`` and ``scenario`` bands (p5, p50, p95),
        end values, the lowest likely balance (5th percentile) of each and
        a plain ``verdict``: ``affordable`` (even the unlucky paths stay
        above ``threshold``), ``tight`` (the typical path stays above, the
        unlucky ones don't) or ``not_affordable``.
    """
    today = today or date.today()
    fc = cash_flow_forecast(db, fx, base, horizon_days, lookback_days,
                            1000, threshold, today=today)
    adj, labels = _adjustments(db, fx, base, changes, today, horizon_days)
    shift = np.cumsum(adj)
    p5 = np.array(fc["p5"])
    scenario = {k: (np.array(fc[k]) + shift).tolist()
                for k in ("p5", "p50", "p95")}
    low_base, low_scn = float(p5.min()), float((p5 + shift).min())
    if low_scn >= threshold:
        verdict = "affordable"
    elif float((np.array(fc["p50"]) + shift).min()) >= threshold:
        verdict = "tight"
    else:
        verdict = "not_affordable"
    return {
        "currency": base, "dates": fc["dates"], "changes": labels,
        "baseline": {k: fc[k] for k in ("p5", "p50", "p95")},
        "scenario": scenario,
        "end": {"baseline": fc["p50"][-1], "scenario": scenario["p50"][-1]},
        "lowest": {"baseline": low_base, "scenario": low_scn},
        "threshold": threshold, "verdict": verdict, "notes": fc["notes"],
        "method": "The forecast's simulated paths, shifted by the "
                  "scenario's changes. A projection, not a promise.",
    }


def financial_independence(db: Session, fx: FxConverter, base: str,
                           return_pct: float = 5.0,
                           withdrawal_pct: float = 4.0,
                           extra_monthly: float = 0.0,
                           today: date | None = None) -> dict:
    """Years until investments could pay for your spending.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    return_pct : float
        The assumed yearly return after inflation, in percent.
    withdrawal_pct : float
        The share of the portfolio taken out each year once independent,
        in percent (4 % is the common rule of thumb).
    extra_monthly : float
        The extra amount saved each month on top of today's savings.
    today : date, optional
        The reference date (defaults to today).

    Returns
    -------
    dict
        Spending and savings of the last 12 months, the ``target``
        portfolio, ``invested`` today, ``years`` to independence (None if
        never within 80 years), the yearly ``path`` and the assumptions.
    """
    today = today or date.today()
    start = add_months(today.replace(day=1), -12)
    end = today.replace(day=1) - timedelta(days=1)
    df = load_transactions(db, fx, base, start, end)
    income = float(incomes(df)["amount_base"].sum())
    spend = float(expenses(df)["spend"].sum())
    nw = net_worth(db, fx, base)
    savings_accounts = sum(a["balance_base"] or 0.0 for a in nw.by_account
                           if a.get("type") == "savings")
    invested = float(nw.holdings + nw.investment_cash + savings_accounts)
    yearly_saving = max(income - spend, 0.0) + 12 * extra_monthly
    r, w = return_pct / 100, withdrawal_pct / 100
    target = spend / w if w > 0 and spend > 0 else None
    path, value, years = [], invested, None
    for year in range(0, 81):
        path.append({"year": today.year + year, "value": round(value, 2)})
        if target is not None and years is None and value >= target:
            years = year
        value = value * (1 + r) + yearly_saving
    return {
        "currency": base, "annual_income": income, "annual_spending": spend,
        "annual_saving": yearly_saving,
        "savings_rate": (income - spend) / income if income > 0 else None,
        "invested": invested, "target": target, "years": years,
        "year_reached": today.year + years if years is not None else None,
        "path": path[: (years or 40) + 6],
        "assumptions": {"return_pct": return_pct,
                        "withdrawal_pct": withdrawal_pct,
                        "extra_monthly": extra_monthly},
        "method": "Last 12 full months of income and spending; investments,"
                  " investment cash and savings accounts count as invested."
                  " Returns are after inflation and constant. A projection,"
                  " not advice.",
    }


def recurring_choices(db: Session) -> list[dict]:
    """Active bills and incomes a scenario can change."""
    return [{"id": r.id, "name": r.name, "amount": float(r.amount)}
            for r in db.scalars(select(RecurringItem).where(
                RecurringItem.is_active.is_(True)).order_by(
                RecurringItem.name))]
