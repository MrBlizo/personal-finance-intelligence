"""Investment performance: XIRR, time-weighted return, income, allocation.

Definitions (all in the base currency, flows converted at the rate of
their own date):

* **XIRR** is the annualised money-weighted return: the rate ``r`` with
  ``sum(CF_i / (1 + r) ** (t_i / 365)) = 0`` over buys (negative), sells,
  dividends (positive), fees (negative) and today's market value
  (positive). It reflects the timing and size of your own contributions.
* **Time-weighted return (TWR)** removes the effect of contributions: it
  chains monthly Modified Dietz returns
  ``R_m = (V_end - V_start - F + D) / (V_start + sum(w_i F_i))`` where
  ``F`` are net purchases, ``D`` dividends and ``w_i`` the fraction of the
  month remaining after each flow. It is the figure to compare with a
  benchmark index.

Both depend on the price history entered or downloaded: between two price
dates the last known price is used, so sparse prices smooth the result.
"""
import calendar
import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ASSET_CLASSES, Holding, InvestmentTrade
from . import prefs
from .fx import FxConverter
from .ledger import holding_valuations


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Solve the annualised internal rate of return of dated cash flows.

    Parameters
    ----------
    flows : list of tuple of (date, float)
        The dated flows: investments negative, proceeds positive.

    Returns
    -------
    float or None
        The annual rate (0.07 = 7 %), or None when the flows do not change
        sign or span less than one day.
    """
    flows = [(d, v) for d, v in flows if v]
    if len(flows) < 2 or all(v > 0 for _, v in flows) \
            or all(v < 0 for _, v in flows):
        return None
    t0 = min(d for d, _ in flows)
    span = [((d - t0).days / 365.0, v) for d, v in flows]
    if max(t for t, _ in span) <= 0:
        return None

    def npv(r: float) -> float:
        return sum(v / (1.0 + r) ** t for t, v in span)

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7 or hi - lo < 1e-10:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def _flows(db: Session, fx: FxConverter, base: str,
           holding_ids: list[int] | None = None
           ) -> list[tuple[date, float, str, int]]:
    """Return (date, amount_in_base, type, holding_id) investor flows."""
    stmt = select(InvestmentTrade, Holding).join(Holding)
    if holding_ids is not None:
        stmt = stmt.where(Holding.id.in_(holding_ids))
    out = []
    for t, h in db.execute(stmt):
        rate = fx.try_rate(h.currency, base, t.trade_date)
        if rate is None:
            continue
        qty, price, fees = float(t.quantity), float(t.price), float(t.fees)
        if t.trade_type == "buy":
            v = -(qty * price + fees)
        elif t.trade_type == "sell":
            v = qty * price - fees
        elif t.trade_type == "dividend":
            v = float(t.cash_amount or 0)
        else:
            v = -float(t.cash_amount or t.fees)
        out.append((t.trade_date, v * rate, t.trade_type, h.id))
    return out


def _month_ends(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        last = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        out.append(min(last, end))
        d = last + timedelta(days=1)
    return out


def _value(db: Session, fx: FxConverter, base: str, day: date,
           ids: set[int] | None) -> float:
    return sum(h["market_value_base"] or 0.0
               for h in holding_valuations(db, fx, base, day)
               if ids is None or h["id"] in ids)


def time_weighted(db: Session, fx: FxConverter, base: str,
                  holding_ids: list[int] | None = None,
                  today: date | None = None) -> dict:
    """Chain monthly Modified Dietz returns since the first trade.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The reporting currency.
    holding_ids : list of int, optional
        The holdings to include; all when omitted.
    today : date, optional
        The end of the evaluation period; defaults to today.

    Returns
    -------
    dict
        ``cumulative`` and ``annualised`` returns (None if undefined) and
        the monthly series used to compute them.
    """
    today = today or date.today()
    flows = _flows(db, fx, base, holding_ids)
    if not flows:
        return {"cumulative": None, "annualised": None, "months": []}
    ids = set(holding_ids) if holding_ids is not None else None
    start = min(d for d, *_ in flows)
    growth, months, prev_end = 1.0, [], start - timedelta(days=1)
    v_start = 0.0
    for end in _month_ends(start, today):
        v_end = _value(db, fx, base, end, ids)
        days = (end - prev_end).days or 1
        net_in = weighted = div = 0.0
        for d, v, kind, _ in flows:
            if prev_end < d <= end:
                if kind == "dividend":
                    div += v
                else:
                    contribution = -v
                    net_in += contribution
                    weighted += contribution * (end - d).days / days
        denom = v_start + weighted
        r = (v_end - v_start - net_in + div) / denom if denom > 1e-9 \
            else None
        if r is not None:
            growth *= 1 + r
        months.append({"month": end.strftime("%Y-%m"), "return": r,
                       "value": v_end})
        v_start, prev_end = v_end, end
    years = max((today - start).days, 1) / 365.0
    cumulative = growth - 1
    annual = (growth ** (1 / years) - 1) if years >= 1 and growth > 0 \
        else None
    return {"cumulative": cumulative, "annualised": annual,
            "months": months}


def portfolio(db: Session, fx: FxConverter, base: str,
              today: date | None = None) -> dict:
    """Return per-holding and total performance, income and allocation.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The reporting currency.
    today : date, optional
        The valuation date; defaults to today.

    Returns
    -------
    dict
        ``holdings`` (XIRR, trailing dividends and yield per holding),
        ``total`` (XIRR, TWR, value), ``dividends_by_year`` and
        ``allocation`` (actual vs. target per asset class with drift and
        the amount to buy or sell to rebalance).
    """
    today = today or date.today()
    vals = holding_valuations(db, fx, base, today)
    flows = _flows(db, fx, base)
    year_ago = today - timedelta(days=365)
    rows = []
    for h in vals:
        own = [(d, v) for d, v, _, hid in flows if hid == h["id"]]
        if h["market_value_base"]:
            own.append((today, h["market_value_base"]))
        div12 = sum(v for d, v, k, hid in flows
                    if hid == h["id"] and k == "dividend" and d > year_ago)
        rows.append({
            "id": h["id"], "symbol": h["symbol"], "name": h["name"],
            "asset_class": h["asset_class"],
            "value_base": h["market_value_base"], "xirr": xirr(own),
            "dividends_12m": div12,
            "yield_12m": (div12 / h["market_value_base"]
                          if h["market_value_base"] else None)})
    total_value = sum(h["market_value_base"] or 0 for h in vals)
    all_flows = [(d, v) for d, v, *_ in flows]
    if total_value:
        all_flows.append((today, total_value))
    by_year: dict[int, float] = {}
    for d, v, k, _ in flows:
        if k == "dividend":
            by_year[d.year] = by_year.get(d.year, 0.0) + v
    twr = time_weighted(db, fx, base, today=today)
    return {
        "base_currency": base, "holdings": rows,
        "total": {"value": total_value, "xirr": xirr(all_flows),
                  "twr_cumulative": twr["cumulative"],
                  "twr_annualised": twr["annualised"],
                  "dividends_12m": sum(r["dividends_12m"] for r in rows)},
        "twr_months": twr["months"],
        "dividends_by_year": [{"year": y, "amount": a}
                              for y, a in sorted(by_year.items())],
        "allocation": allocation(vals, prefs.get_targets(db)),
    }


def allocation(vals: list[dict], targets: dict[str, float]) -> list[dict]:
    """Compare the actual mix of asset classes with the targets.

    Parameters
    ----------
    vals : list of dict
        The holding valuations from ``holding_valuations``.
    targets : dict of str to float
        The target share per asset class in percent (may be empty).

    Returns
    -------
    list of dict
        Per asset class: value, actual and target percent, drift in
        percentage points and the trade (in base currency) that restores
        the target; target fields are None without targets.
    """
    by_class: dict[str, float] = {}
    for h in vals:
        if h["market_value_base"]:
            by_class[h["asset_class"]] = (by_class.get(h["asset_class"], 0)
                                          + h["market_value_base"])
    total = sum(by_class.values())
    out = []
    for cls in ASSET_CLASSES:
        value = by_class.get(cls, 0.0)
        target = targets.get(cls)
        if not value and target is None:
            continue
        actual = 100 * value / total if total else 0.0
        out.append({
            "asset_class": cls, "value": value, "actual_pct": actual,
            "target_pct": target,
            "drift_pp": (actual - target) if target is not None else None,
            "rebalance": ((target / 100) * total - value
                          if target is not None else None)})
    return out


def is_finite(x: float | None) -> bool:
    """True for a real, finite number."""
    return x is not None and math.isfinite(x)
