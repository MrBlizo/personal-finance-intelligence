"""Download market prices for holdings from free, keyless sources.

* ``stooq``: end-of-day closes for stocks, ETFs and funds on many
  exchanges (symbols such as ``vt.us``, ``vwrl.uk``, ``sap.de``). The
  daily CSV download also provides history for performance figures.
  Since 2026 stooq requires a free personal API key (obtained once on
  stooq.com after a captcha); it is stored in the app's settings and
  only sent to stooq.
* ``coingecko``: crypto prices by coin id (``bitcoin``, ``ethereum``) in
  the holding's currency, with up to 365 days of daily history.

Only the symbol, the currency code and (for stooq) your stooq API key
are sent. Prices are stored with
the provider name as ``source``; a manual price for the same day is never
overwritten. Prices are delayed (end of day for stooq) and are meant for
portfolio tracking, not trading.
"""
import csv
import io
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssetPrice, Holding
from . import prefs

log = logging.getLogger(__name__)
HISTORY_DAYS = 365 * 3
STOOQ_URL = "https://stooq.com/q/d/l/?s={sym}&i=d&d1={d1}&d2={d2}"
STOOQ_KEY_PAGE = "https://stooq.com/q/d/?s=spy.us&get_apikey"
STOOQ_KEY_HELP = (
    "stooq needs a free API key. Open " + STOOQ_KEY_PAGE + ", enter the "
    "captcha, copy the value after 'apikey=' from the CSV download link and "
    "paste it in Settings > Exchange rates & prices > stooq API key.")
GECKO_URL = ("https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
             "?vs_currency={cur}&days={days}")


class PriceFetchError(RuntimeError):
    """Raised when a price provider cannot be reached or understood."""


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PFI/0.3"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_stooq(symbol: str, start: date, end: date,
                apikey: str = "") -> dict[date, float]:
    """Return daily closes from stooq.

    Parameters
    ----------
    symbol : str
        The stooq symbol including the market suffix, e.g. ``vt.us``.
    start : date
        The first day requested.
    end : date
        The last day requested.
    apikey : str
        The user's stooq API key.

    Returns
    -------
    dict of date to float
        The closing price per trading day.

    Raises
    ------
    PriceFetchError
        If the request fails or the symbol is unknown.
    """
    if not apikey:
        raise PriceFetchError(STOOQ_KEY_HELP)
    url = STOOQ_URL.format(sym=urllib.parse.quote(symbol.lower()),
                           d1=start.strftime("%Y%m%d"),
                           d2=end.strftime("%Y%m%d"))
    url += "&apikey=" + urllib.parse.quote(apikey)
    try:
        text = _get(url).decode("utf-8", "replace")
    except Exception as exc:
        raise PriceFetchError(f"stooq could not be reached for {symbol}: "
                              f"{exc}") from exc
    if "apikey" in text.lower() and "date" not in text[:40].lower():
        raise PriceFetchError("stooq did not accept the API key. "
                              + STOOQ_KEY_HELP)
    if "limit exceeded" in text.lower():
        raise PriceFetchError(
            "stooq's daily download limit was reached. Try again "
            "tomorrow.")
    rows = list(csv.DictReader(io.StringIO(text)))
    out = {}
    for r in rows:
        try:
            out[date.fromisoformat(r["Date"])] = float(r["Close"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise PriceFetchError(
            f"stooq returned no prices for '{symbol}'. Check the symbol "
            "and its market suffix on stooq.com (e.g. vt.us, vwrl.uk).")
    return out


def fetch_coingecko(coin: str, currency: str, days: int = 365
                    ) -> dict[date, float]:
    """Return daily crypto prices from CoinGecko.

    Parameters
    ----------
    coin : str
        The CoinGecko coin id, e.g. ``bitcoin``.
    currency : str
        The ISO code of the holding's currency.
    days : int
        The history length in days (the free API allows up to 365).

    Returns
    -------
    dict of date to float
        One price per day (the last quote of each UTC day).

    Raises
    ------
    PriceFetchError
        If the request fails or the coin id is unknown.
    """
    url = GECKO_URL.format(coin=urllib.parse.quote(coin.lower()),
                           cur=currency.lower(), days=min(days, 365))
    try:
        data = json.loads(_get(url).decode("utf-8"))
        points = data["prices"]
    except Exception as exc:
        raise PriceFetchError(
            f"CoinGecko returned no prices for '{coin}' in {currency}: "
            f"{exc}. Use the coin id from coingecko.com (e.g. bitcoin)."
        ) from exc
    out = {}
    for ms, price in points:
        day = datetime.fromtimestamp(ms / 1000, timezone.utc).date()
        out[day] = float(price)
    return out


def _store(db: Session, holding: Holding, prices: dict[date, float],
           source: str) -> int:
    existing = {p.price_date: p for p in db.scalars(select(AssetPrice).where(
        AssetPrice.holding_id == holding.id))}
    n = 0
    for day, value in prices.items():
        if value <= 0:
            continue
        row = existing.get(day)
        if row is None:
            db.add(AssetPrice(holding_id=holding.id, price_date=day,
                              price=Decimal(str(round(value, 6))),
                              source=source))
            n += 1
        elif row.source == source:
            row.price = Decimal(str(round(value, 6)))
    return n


def update_holding(db: Session, holding: Holding,
                   today: date | None = None) -> int:
    """Download prices for one holding and store them.

    Parameters
    ----------
    db : Session
        The open database session; the caller commits.
    holding : Holding
        The holding with ``price_source`` other than ``manual``.
    today : date, optional
        The last day requested; defaults to today.

    Returns
    -------
    int
        The number of new price rows.
    """
    today = today or date.today()
    last = db.scalar(select(AssetPrice.price_date).where(
        AssetPrice.holding_id == holding.id,
        AssetPrice.source == holding.price_source)
        .order_by(AssetPrice.price_date.desc()).limit(1))
    start = (last - timedelta(days=7)) if last else \
        today - timedelta(days=HISTORY_DAYS)
    symbol = holding.price_symbol or holding.symbol
    if holding.price_source == "stooq":
        prices = fetch_stooq(symbol, start, today,
                             prefs.get(db, "stooq_api_key"))
    elif holding.price_source == "coingecko":
        prices = fetch_coingecko(symbol, holding.currency,
                                 (today - start).days + 1)
    else:
        return 0
    return _store(db, holding, prices, holding.price_source)


def update_prices(db: Session) -> dict:
    """Update every holding that has an online price source.

    Parameters
    ----------
    db : Session
        The open database session; this function commits.

    Returns
    -------
    dict
        Counts of updated holdings and new prices, and per-symbol errors.
    """
    holdings = list(db.scalars(select(Holding).where(
        Holding.price_source != "manual")))
    added, errors, ok = 0, [], 0
    for h in holdings:
        try:
            added += update_holding(db, h)
            ok += 1
        except PriceFetchError as exc:
            errors.append({"symbol": h.symbol, "error": str(exc)})
    prefs.put(db, "price_last_update", date.today().isoformat())
    db.commit()
    return {"holdings": len(holdings), "updated": ok, "new_prices": added,
            "errors": errors}


def prices_due(db: Session) -> bool:
    """True when automatic price updates are on and none ran today."""
    if not prefs.get_bool(db, "price_auto_update"):
        return False
    if db.scalar(select(Holding.id).where(
            Holding.price_source != "manual").limit(1)) is None:
        return False
    return prefs.get(db, "price_last_update") != date.today().isoformat()
