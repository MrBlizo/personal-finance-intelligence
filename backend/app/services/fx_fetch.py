"""Download exchange rates from the free, keyless Exchange API.

Source: https://github.com/fawazahmed0/exchange-api (daily rates for 200+
currencies, history from 2024-03-02). Each request contains only a currency
code. Rates are stored with ``source = SOURCE`` so they can be told apart
from manually entered ones; a manual rate for the same day is never
overwritten.
"""
import json
import logging
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account, ExchangeRate, Holding, SavingsGoal, Setting, Transaction)
from ..seed import get_setting
from .planning import add_months

log = logging.getLogger(__name__)
SOURCE = "exchange-api"
EARLIEST = date(2024, 3, 2)
URLS = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{day}"
    "/v1/currencies/{base}.min.json",
    "https://{day}.currency-api.pages.dev/v1/currencies/{base}.min.json",
)
MAX_BACKFILL_MONTHS = 36


class FxFetchError(RuntimeError):
    """Raised when no rate source could be reached."""


def _get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "PFI/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_table(base: str, day: date | None = None) -> tuple[date, dict]:
    """Return the publication date and rates (1 ``base`` = x currency).

    Parameters
    ----------
    base : str
        The ISO code of the base currency, e.g. ``"CHF"``.
    day : date, optional
        The date of historical rates; the latest table if omitted.

    Returns
    -------
    tuple of (date, dict)
        The table date and a mapping of upper-case codes to rates.

    Raises
    ------
    FxFetchError
        If neither the primary nor the fallback host answered.
    """
    tag = day.isoformat() if day else "latest"
    errors = []
    for template in URLS:
        url = template.format(day=tag, base=base.lower())
        try:
            data = _get_json(url)
            rates = data[base.lower()]
            published = date.fromisoformat(data.get("date", tag)) \
                if data.get("date") else (day or date.today())
            return published, {k.upper(): float(v) for k, v in rates.items()
                               if isinstance(v, (int, float)) and v > 0}
        except Exception as exc:  # network, HTTP or format errors
            errors.append(f"{url}: {exc}")
    raise FxFetchError(
        "Exchange rates could not be downloaded (" + "; ".join(errors)
        + "). Check the internet connection, or enter rates manually in "
        "Settings.")


def currencies_in_use(db: Session) -> set[str]:
    """Return every currency used by accounts, holdings or goals."""
    found = set(db.scalars(select(Account.currency).distinct()))
    found |= set(db.scalars(select(Holding.currency).distinct()))
    found |= set(db.scalars(select(SavingsGoal.currency).distinct()))
    return found


def _store(db: Session, base: str, published: date, rates: dict,
           wanted: set[str]) -> int:
    stored = 0
    for cur in sorted(wanted - {base}):
        if cur not in rates:
            continue
        row = db.scalar(select(ExchangeRate).where(
            ExchangeRate.rate_date == published,
            ExchangeRate.from_currency == base,
            ExchangeRate.to_currency == cur))
        if row is None:
            db.add(ExchangeRate(rate_date=published, from_currency=base,
                                to_currency=cur, source=SOURCE,
                                rate=Decimal(str(round(rates[cur], 8)))))
            stored += 1
        elif row.source == SOURCE:
            row.rate = Decimal(str(round(rates[cur], 8)))
    return stored


def update_rates(db: Session, base: str, backfill: bool = True,
                 today: date | None = None) -> dict:
    """Download today's rates and, optionally, monthly history.

    History covers the first day of every month since the earliest
    transaction (at most ``MAX_BACKFILL_MONTHS`` and not before
    ``EARLIEST``); months that already have downloaded rates are skipped.

    Parameters
    ----------
    db : Session
        The open database session.
    base : str
        The reporting currency used as base.
    backfill : bool
        The flag to also download monthly historical rates.
    today : date, optional
        The reference date (defaults to today).

    Returns
    -------
    dict
        The number of stored rates, the currencies covered, the ones the
        source does not publish and the table date.
    """
    today = today or date.today()
    wanted = currencies_in_use(db) - {base}
    if not wanted:
        return {"stored": 0, "currencies": [], "missing": [],
                "date": None, "note": "Only the base currency is in use."}
    published, rates = fetch_table(base)
    stored = _store(db, base, published, rates, wanted)
    missing = sorted(c for c in wanted if c not in rates)
    if backfill:
        first_txn = db.scalar(select(Transaction.txn_date).order_by(
            Transaction.txn_date).limit(1)) or today
        start = max(first_txn.replace(day=1), EARLIEST.replace(day=1),
                    add_months(today.replace(day=1), -MAX_BACKFILL_MONTHS))
        have = set(db.scalars(select(ExchangeRate.rate_date).where(
            ExchangeRate.source == SOURCE).distinct()))
        month = start
        while month < today.replace(day=1) + timedelta(days=1):
            day = max(month, EARLIEST)
            if not any(d.year == day.year and d.month == day.month
                       for d in have):
                try:
                    pub, table = fetch_table(base, day)
                    stored += _store(db, base, pub, table, wanted)
                except FxFetchError as exc:
                    log.warning("History for %s not available: %s", day, exc)
            month = add_months(month, 1)
    _set(db, "fx_last_update", today.isoformat())
    db.commit()
    return {"stored": stored, "currencies": sorted(wanted - set(missing)),
            "missing": missing, "date": published.isoformat()}


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def auto_update_due(db: Session, today: date | None = None) -> bool:
    """Return whether the daily automatic update should run now."""
    today = today or date.today()
    if get_setting(db, "fx_auto_update", "1") != "1":
        return False
    return get_setting(db, "fx_last_update", "") != today.isoformat()
