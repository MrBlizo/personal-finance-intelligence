"""Dashboard summary, Plotly charts, insights and forecast."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import charts
from ..services.forecast import cash_flow_forecast
from ..services.frame import expenses, incomes, load_transactions
from ..services.fx import FxConverter
from ..services.insights import build_insights
from ..services.ledger import base_currency, holding_valuations, net_worth
from ..services.planning import add_months, budget_status

router = APIRouter(prefix="/api")
CHARTS = ("monthly_cashflow", "savings_rate", "category_breakdown",
          "category_trend", "weekday_heatmap", "top_merchants",
          "budget_vs_actual", "net_worth", "allocation")


def _period(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or date.today()
    start = start or add_months(end.replace(day=1), -11)
    if start > end:
        raise HTTPException(422, "Start date must be before end date.")
    return start, end


def _summary(db: Session, fx: FxConverter, base: str, start: date,
             end: date) -> dict:
    df = load_transactions(db, fx, base, start, end)
    inc = float(incomes(df)["amount_base"].sum())
    spend = float(expenses(df)["spend"].sum())
    months = max((end - start).days / 30.4375, 1.0)
    nw = net_worth(db, fx, base)
    return {
        "currency": base, "start": start, "end": end,
        "income": inc, "expenses": spend, "net": inc - spend,
        "savings_rate": (inc - spend) / inc if inc > 0 else None,
        "avg_monthly_income": inc / months,
        "avg_monthly_expenses": spend / months,
        "transactions": int(len(df)),
        "net_worth": nw.total, "liquid": nw.liquid,
        "investments": nw.holdings + nw.investment_cash,
        "liabilities": nw.liabilities,
        "missing_fx": sorted(set(df.attrs["missing_fx"])
                             | nw.missing_fx),
        "unpriced_holdings": nw.unpriced_holdings}


@router.get("/analytics/summary")
def summary(start: date | None = None, end: date | None = None,
            db: Session = Depends(get_db)):
    start, end = _period(start, end)
    return _summary(db, FxConverter.from_db(db), base_currency(db),
                    start, end)


def _net_worth_points(db: Session, fx: FxConverter, base: str,
                      end: date, months: int) -> list[dict]:
    points = []
    for day in charts.month_range(end, months):
        nw = net_worth(db, fx, base, day)
        points.append({"date": day, "total": nw.total, "liquid": nw.liquid,
                       "investments": nw.holdings + nw.investment_cash})
    return points


def _chart(name: str, db: Session, fx: FxConverter, base: str,
           start: date, end: date, month: date | None,
           cache: dict) -> dict:
    if "df" not in cache:
        cache["df"] = load_transactions(db, fx, base, start, end)
        cache["exp"] = expenses(cache["df"])
    df, exp = cache["df"], cache["exp"]
    if name == "monthly_cashflow":
        return charts.monthly_cashflow(df, base)
    if name == "savings_rate":
        return charts.savings_rate(df)
    if name == "category_breakdown":
        return charts.category_breakdown(exp, base)
    if name == "category_trend":
        return charts.category_trend(exp, base)
    if name == "weekday_heatmap":
        return charts.weekday_heatmap(exp, base)
    if name == "top_merchants":
        return charts.top_merchants(exp, base)
    if name == "budget_vs_actual":
        return charts.budget_vs_actual(
            budget_status(db, fx, base, month or end))
    if name == "net_worth":
        months = max(2, min(36, round((end - start).days / 30.4) + 1))
        return charts.net_worth_history(
            _net_worth_points(db, fx, base, end, months), base)
    if name == "allocation":
        return charts.allocation(holding_valuations(db, fx, base), base)
    raise HTTPException(
        404, f"Unknown chart '{name}'. Available: {', '.join(CHARTS)}.")


@router.get("/analytics/charts/{name}")
def chart(name: str, start: date | None = None, end: date | None = None,
          month: date | None = None, db: Session = Depends(get_db)):
    start, end = _period(start, end)
    return _chart(name, db, FxConverter.from_db(db), base_currency(db),
                  start, end, month, {})


@router.get("/analytics/dashboard")
def dashboard(start: date | None = None, end: date | None = None,
              charts_: list[str] = Query(
                  ["monthly_cashflow", "category_breakdown", "net_worth",
                   "budget_vs_actual"], alias="charts"),
              db: Session = Depends(get_db)):
    """Summary plus several charts in one request."""
    start, end = _period(start, end)
    fx, base = FxConverter.from_db(db), base_currency(db)
    cache: dict = {}
    return {"summary": _summary(db, fx, base, start, end),
            "charts": {n: _chart(n, db, fx, base, start, end, None, cache)
                       for n in charts_}}


@router.get("/insights")
def insights(db: Session = Depends(get_db)):
    return build_insights(db, FxConverter.from_db(db), base_currency(db))


@router.get("/forecast")
def forecast(horizon_days: int = Query(90, ge=7, le=730),
             lookback_days: int = Query(180, ge=28, le=1095),
             simulations: int = Query(1000, ge=100, le=10000),
             threshold: float = 0.0, seed: int = 42,
             db: Session = Depends(get_db)):
    fx, base = FxConverter.from_db(db), base_currency(db)
    fc = cash_flow_forecast(db, fx, base, horizon_days, lookback_days,
                            simulations, threshold, seed)
    fc["figure"] = charts.forecast_fan(fc)
    return fc


@router.get("/analytics/periods")
def periods():
    """Quick-select ranges for the UI date picker."""
    today = date.today()
    first = today.replace(day=1)
    return {
        "this_month": [first, today],
        "last_month": [add_months(first, -1), first - timedelta(days=1)],
        "last_3_months": [add_months(first, -2), today],
        "last_12_months": [add_months(first, -11), today],
        "year_to_date": [today.replace(month=1, day=1), today],
    }
