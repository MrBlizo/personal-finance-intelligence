"""Cash-flow forecast for liquid accounts (checking, savings, cash, cards).

Model (a prediction, not an observation):

1. Scheduled flows: every active recurring item on a liquid account is
   placed on its exact future dates (deterministic).
2. Discretionary flows: daily net non-transfer flows of the look-back
   window are resampled with a 7-day block bootstrap to keep weekly
   patterns. Past transactions that realise a recurring item are reduced
   to their deviation from the scheduled amount (e.g. a bonus), so the
   scheduled part is not counted twice.
3. Balance paths = current liquid balance + cumulative scheduled +
   simulated discretionary flows. Percentiles across simulations give the
   uncertainty band; the share of paths dipping below the threshold gives
   the shortfall probability.

Assumptions: future behaviour resembles the look-back window; FX rates
stay at their latest values; no flows from investment or loan accounts.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LIQUID_TYPES, Account, RecurringItem
from .frame import load_transactions
from .fx import FxConverter
from .ledger import net_worth
from .planning import occurrences

MATCH_TOL = 0.15
MATCH_DAYS = 7
BLOCK = 7
MIN_HISTORY_DAYS = 28


def _remove_scheduled(df: pd.DataFrame, items: list[RecurringItem],
                      acc_currency: dict[int, str], fx: FxConverter,
                      base: str, start: date, end: date) -> pd.DataFrame:
    """Replace transactions that realise a recurring item by residuals.

    For each past occurrence of an item, the nearest unused transaction on
    the same account with the same sign (and category, if set) within
    ``MATCH_DAYS`` is taken as its realisation. Its amount is replaced by
    ``actual - scheduled`` (e.g. a bonus on top of the regular salary), so
    the scheduled part is not counted twice in the simulation.
    """
    out = df.copy()
    used: set[int] = set()
    for it in items:
        rate = fx.try_rate(acc_currency[it.account_id], base)
        if rate is None:
            continue
        target = float(it.amount) * rate
        cand = out[(out["account_id"] == it.account_id)
                   & (np.sign(out["amount_base"]) == np.sign(target))]
        if it.category_id is not None:
            cand = cand[cand["category_id"] == it.category_id]
        else:
            cand = cand[(cand["amount_base"] - target).abs()
                        <= abs(target) * MATCH_TOL]
        for day in occurrences(it, start - timedelta(days=MATCH_DAYS),
                               end):
            gap = (cand["txn_date"] - pd.Timestamp(day)).dt.days.abs()
            gap = gap[(gap <= MATCH_DAYS) & ~gap.index.isin(used)]
            if gap.empty:
                continue
            idx = gap.idxmin()
            used.add(idx)
            out.loc[idx, "amount_base"] -= target
    return out


def cash_flow_forecast(db: Session, fx: FxConverter, base: str,
                       horizon_days: int = 90, lookback_days: int = 180,
                       simulations: int = 1000, threshold: float = 0.0,
                       seed: int = 42, today: date | None = None) -> dict:
    """Simulate future liquid balances in the base currency.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    horizon_days : int
        The number of days to project.
    lookback_days : int
        The number of past days used to learn discretionary spending.
    simulations : int
        The number of Monte Carlo paths.
    threshold : float
        The balance level whose breach probability is reported.
    seed : int
        The random seed, so identical inputs give identical outputs.
    today : date, optional
        The forecast origin (defaults to today).

    Returns
    -------
    dict
        Dates, percentile bands (p5, p25, p50, p75, p95), the scheduled
        path, shortfall probability, scheduled items and model notes.
    """
    today = today or date.today()
    rng = np.random.default_rng(seed)
    days = pd.date_range(today + timedelta(days=1), periods=horizon_days)
    accounts = {a.id: a for a in db.scalars(select(Account).where(
        Account.type.in_(LIQUID_TYPES), Account.is_archived.is_(False)))}
    acc_currency = {a.id: a.currency for a in accounts.values()}
    nw = net_worth(db, fx, base)
    start_balance = sum(a["balance_base"] or 0.0 for a in nw.by_account
                        if a["id"] in accounts)
    items = [i for i in db.scalars(select(RecurringItem).where(
        RecurringItem.is_active.is_(True))) if i.account_id in accounts]
    scheduled = np.zeros(horizon_days)
    upcoming = []
    end = today + timedelta(days=horizon_days)
    for it in items:
        rate = fx.try_rate(acc_currency[it.account_id], base)
        if rate is None:
            continue
        value = float(it.amount) * rate
        for day in occurrences(it, today + timedelta(days=1), end):
            scheduled[(day - today).days - 1] += value
            upcoming.append({"date": day, "name": it.name,
                             "amount_base": value})
    upcoming.sort(key=lambda u: u["date"])

    hist = load_transactions(db, fx, base,
                             today - timedelta(days=lookback_days), today)
    hist = hist[hist["account_id"].isin(accounts)
                & hist["amount_base"].notna()]
    notes = []
    history_days = 0
    if len(hist):
        first = max(hist["txn_date"].min().date(),
                    today - timedelta(days=lookback_days - 1))
        history_days = (today - first).days + 1
        hist = _remove_scheduled(hist, items, acc_currency, fx, base,
                                 first, today)
    if history_days >= MIN_HISTORY_DAYS:
        idx = pd.date_range(today - timedelta(days=history_days - 1),
                            today)
        daily = (hist.groupby("txn_date")["amount_base"].sum()
                 .reindex(idx, fill_value=0.0).to_numpy())
        n_blocks = len(daily) - BLOCK + 1
        needed = -(-horizon_days // BLOCK)
        starts = rng.integers(0, n_blocks, size=(simulations, needed))
        offsets = np.arange(BLOCK)
        paths = daily[(starts[:, :, None] + offsets).reshape(
            simulations, -1)][:, :horizon_days]
        discretionary_mean = float(daily.mean())
    else:
        paths = np.zeros((simulations, horizon_days))
        discretionary_mean = 0.0
        notes.append(
            f"Only {history_days} days of history (need "
            f"{MIN_HISTORY_DAYS}); the forecast includes scheduled "
            "recurring items only.")
    balances = start_balance + np.cumsum(scheduled + paths, axis=1)
    pct = np.percentile(balances, [5, 25, 50, 75, 95], axis=0)
    below = (balances.min(axis=1) < threshold).mean()
    if nw.missing_fx:
        notes.append("Accounts in " + ", ".join(sorted(nw.missing_fx))
                     + " were left out: no exchange rate to " + base + ".")
    return {
        "base_currency": base, "origin": today,
        "horizon_days": horizon_days, "simulations": simulations,
        "lookback_days_used": history_days,
        "start_balance": start_balance,
        "dates": [d.date() for d in days],
        "p5": pct[0].tolist(), "p25": pct[1].tolist(),
        "p50": pct[2].tolist(), "p75": pct[3].tolist(),
        "p95": pct[4].tolist(),
        "scheduled_only": (start_balance + np.cumsum(scheduled)).tolist(),
        "expected_end": float(balances[:, -1].mean()),
        "threshold": threshold, "prob_below_threshold": float(below),
        "discretionary_daily_mean": discretionary_mean,
        "scheduled_total": float(scheduled.sum()),
        "upcoming": upcoming[:50], "notes": notes,
        "method": "Scheduled recurring items + 7-day block bootstrap of "
                  "historical discretionary daily flows (Monte Carlo).",
    }
