"""Rule-based spending insights computed from transaction history.

All insights are statistical observations, not explanations:

- unusual transactions: robust z-score (median/MAD) within a category;
- subscription candidates: same payee, stable amount, regular interval;
- category shifts: last full month vs. the mean of the 3 months before.
"""
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from .frame import expenses, load_transactions
from .fx import FxConverter
from .planning import add_months

Z_LIMIT = 3.5
MIN_CAT_TXNS = 8
CADENCES = {"weekly": (6, 8), "monthly": (26, 35), "quarterly": (85, 97),
            "yearly": (355, 375)}


def payee_key(description: str, merchant: str | None) -> str:
    """Normalise a payee by dropping digits, dates and punctuation."""
    text = (merchant or description or "").lower()
    text = re.sub(r"[\d/.\-:#*]+", " ", text)
    return " ".join(text.split()[:4])


def unusual_transactions(df: pd.DataFrame, recent_days: int,
                         today: date) -> list[dict]:
    """Flag recent expenses far above their category's typical size.

    Parameters
    ----------
    df : DataFrame
        The expense rows (with ``spend``) of the analysis window.
    recent_days : int
        The number of most recent days in which flags are reported.
    today : date
        The reference date.

    Returns
    -------
    list of dict
        One insight per flagged transaction.
    """
    out = []
    cutoff = pd.Timestamp(today - timedelta(days=recent_days))
    for cat, grp in df[df["spend"] > 0].groupby("category"):
        if len(grp) < MIN_CAT_TXNS:
            continue
        med = grp["spend"].median()
        mad = (grp["spend"] - med).abs().median()
        if mad == 0:
            continue
        z = 0.6745 * (grp["spend"] - med) / mad
        for idx in grp.index[(z > Z_LIMIT) & (grp["txn_date"] >= cutoff)]:
            row = grp.loc[idx]
            out.append({
                "type": "unusual_transaction", "severity": "warning",
                "title": f"Unusually large {cat} expense",
                "detail": (f"{row['description'][:60]} on "
                           f"{row['txn_date'].date()}: {row['spend']:.2f} "
                           f"vs. a typical {med:.2f} (robust z = "
                           f"{z[idx]:.1f})."),
                "data": {"transaction_id": int(row["id"]),
                         "amount": float(row["spend"]),
                         "median": float(med), "z": float(z[idx])}})
    return out


def subscription_candidates(df: pd.DataFrame) -> list[dict]:
    """Detect payees charged at a regular cadence with stable amounts.

    Parameters
    ----------
    df : DataFrame
        The expense rows (with ``spend``) of the analysis window.

    Returns
    -------
    list of dict
        One insight per detected recurring payee.
    """
    out = []
    data = df[df["spend"] > 0].copy()
    data["payee"] = [payee_key(d, m) for d, m in
                     zip(data["description"], data["merchant"])]
    for payee, grp in data.groupby("payee"):
        if not payee or len(grp) < 3:
            continue
        grp = grp.sort_values("txn_date")
        gaps = grp["txn_date"].diff().dt.days.dropna()
        median_gap = gaps.median()
        cv = grp["spend"].std(ddof=0) / grp["spend"].mean()
        for cadence, (lo, hi) in CADENCES.items():
            if lo <= median_gap <= hi and cv < 0.1 and (
                    (gaps.between(lo, hi)).mean() >= 0.6):
                monthly = grp["spend"].iloc[-3:].mean() * {
                    "weekly": 4.345, "monthly": 1, "quarterly": 1 / 3,
                    "yearly": 1 / 12}[cadence]
                out.append({
                    "type": "subscription", "severity": "info",
                    "title": f"Recurring payment: {payee}",
                    "detail": (f"{len(grp)} {cadence} charges of about "
                               f"{grp['spend'].iloc[-1]:.2f}, last on "
                               f"{grp['txn_date'].iloc[-1].date()} "
                               f"(≈ {monthly:.2f} per month). Add it as a "
                               "recurring item to improve the forecast."),
                    "data": {"payee": payee, "cadence": cadence,
                             "count": int(len(grp)),
                             "last_amount": float(grp["spend"].iloc[-1]),
                             "monthly_equivalent": float(monthly),
                             "category_id": (
                                 None if pd.isna(grp["category_id"].iloc[-1])
                                 else int(grp["category_id"].iloc[-1])),
                             "account_id": int(grp["account_id"].iloc[-1]),
                             "last_date": grp["txn_date"].iloc[-1].date()}})
                break
    return sorted(out, key=lambda i: -i["data"]["monthly_equivalent"])


def category_shifts(df: pd.DataFrame, today: date,
                    min_change: float = 0.3,
                    min_abs: float = 50.0) -> list[dict]:
    """Compare last full month's category spending with the prior 3.

    Parameters
    ----------
    df : DataFrame
        The expense rows (with ``spend``) of the analysis window.
    today : date
        The reference date.
    min_change : float
        The minimum relative change reported (0.3 = 30 %).
    min_abs : float
        The minimum absolute change reported, in base currency.

    Returns
    -------
    list of dict
        One insight per category with a notable change.
    """
    last_start = add_months(today.replace(day=1), -1)
    prev_start = add_months(last_start, -3)
    monthly = (df.assign(month=df["txn_date"].dt.to_period("M"))
               .groupby(["top_category", "month"])["spend"].sum()
               .unstack(fill_value=0.0))
    last_p = pd.Period(last_start, "M")
    prev_ps = [pd.Period(add_months(prev_start, i), "M") for i in range(3)]
    out = []
    for cat, row in monthly.iterrows():
        last = float(row.get(last_p, 0.0))
        prev = float(np.mean([row.get(p, 0.0) for p in prev_ps]))
        diff = last - prev
        if prev <= 0 or abs(diff) < min_abs or abs(diff) / prev < min_change:
            continue
        up = diff > 0
        out.append({
            "type": "category_shift",
            "severity": "warning" if up else "positive",
            "title": f"{cat} {'up' if up else 'down'} "
                     f"{abs(diff) / prev:.0%} in {last_p.strftime('%B')}",
            "detail": (f"{last:.2f} vs. a 3-month average of {prev:.2f} "
                       f"({diff:+.2f})."),
            "data": {"category": cat, "last_month": last,
                     "previous_avg": prev, "change": diff}})
    return sorted(out, key=lambda i: -abs(i["data"]["change"]))


def build_insights(db: Session, fx: FxConverter, base: str,
                   today: date | None = None) -> dict:
    """Collect all insights from the last 12 months of history.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    today : date, optional
        The reference date (defaults to today).

    Returns
    -------
    dict
        The insights list and the analysed date window.
    """
    today = today or date.today()
    start = today - timedelta(days=365)
    df = load_transactions(db, fx, base, start, today)
    exp = expenses(df)
    items: list[dict] = []
    if len(exp):
        items += category_shifts(exp, today)
        items += unusual_transactions(exp, 60, today)
        items += subscription_candidates(exp)
    missing = df.attrs.get("missing_fx", [])
    if missing:
        items.insert(0, {
            "type": "data_quality", "severity": "warning",
            "title": "Exchange rates missing",
            "detail": (f"Transactions in {', '.join(missing)} are excluded "
                       f"from analysis until a rate to {base} is added."),
            "data": {"currencies": missing}})
    uncategorized = int((exp["category"] == "Uncategorized").sum()) \
        if len(exp) else 0
    if uncategorized:
        items.append({
            "type": "data_quality", "severity": "info",
            "title": f"{uncategorized} uncategorized expenses",
            "detail": "Categorize them or add rules so the breakdown and "
                      "budgets are complete.",
            "data": {"count": uncategorized}})
    return {"start": start, "end": today, "currency": base,
            "insights": items}
