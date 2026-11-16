"""Download market prices for holdings from free price providers.

* ``yahoo``: end-of-day closes from Yahoo Finance for stocks, ETFs, funds
  and indices on most exchanges (``AAPL``, ``VWRL.L``, ``SAP.DE``,
  ``NESN.SW``); no key. Holdings set to the older keyed providers below are
  fetched from Yahoo too, with their symbol converted.
* ``twelvedata``: end-of-day closes from Twelve Data. The free plan (800
  requests a day, 8 a minute) covers US-listed stocks and ETFs; symbols
  such as ``AAPL`` or ``VT``. Needs a free personal API key.
* ``alphavantage``: end-of-day closes from Alpha Vantage for stocks and
  ETFs on many exchanges (``IBM``, ``TSCO.LON``). The free plan allows 25
  requests a day and returns the last 100 trading days. Needs a free
  personal API key.
* ``stooq``: end-of-day closes for stocks, ETFs and funds on many
  exchanges (symbols such as ``vt.us``, ``vwrl.uk``, ``sap.de``). Since
  2026 stooq requires a personal API key obtained on stooq.com.
* ``coingecko``: crypto prices by coin id (``bitcoin``, ``ethereum``) in
  the holding's currency, with up to 365 days of daily history; no key.

Only the symbol, the date range, the currency code and the provider's own
API key are sent, each key only to its provider. Prices are stored with
the provider name as ``source``; a manual price for the same day is never
overwritten. Prices are delayed (end of day) and are meant for portfolio
tracking, not trading.
"""
import csv
import io
import json
import logging
import urllib.error
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
TWELVE_URL = ("https://api.twelvedata.com/time_series?symbol={sym}"
              "&interval=1day&start_date={d1}&end_date={d2}&outputsize=5000")
TWELVE_KEY_HELP = (
    "Twelve Data needs a free API key. Sign up on https://twelvedata.com, "
    "copy the key from https://twelvedata.com/account/api-keys and paste it "
    "in Settings > Exchange rates & prices > Twelve Data API key.")
ALPHA_URL = ("https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
             "&symbol={sym}&outputsize=compact&apikey={key}")
ALPHA_KEY_HELP = (
    "Alpha Vantage needs a free API key. Get one on "
    "https://www.alphavantage.co/support/#api-key and paste it in "
    "Settings > Exchange rates & prices > Alpha Vantage API key.")
YAHOO_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
             "?period1={p1}&period2={p2}&interval=1d&events=history")
_YAHOO_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
# stooq / Alpha Vantage market suffixes -> Yahoo Finance suffixes.
_SUFFIX = {"us": "", "uk": ".L", "lon": ".L", "de": ".DE", "dex": ".DE",
           "f": ".F", "fra": ".F", "pa": ".PA", "par": ".PA", "as": ".AS",
           "ams": ".AS", "sw": ".SW", "swx": ".SW", "vx": ".SW", "jp": ".T",
           "hk": ".HK", "tsx": ".TO", "to": ".TO", "mi": ".MI", "mil": ".MI",
           "mc": ".MC", "st": ".ST", "co": ".CO", "ol": ".OL", "he": ".HE",
           "br": ".BR", "ls": ".LS", "vi": ".VI", "pl": ".WA"}
GECKO_URL = ("https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
             "?vs_currency={cur}&days={days}")


class PriceFetchError(RuntimeError):
    """Raised when a price provider cannot be reached or understood."""


def _get(url: str, timeout: float = 20.0,
         headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "PFI/0.3", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        # JSON APIs explain errors in the body (bad key, plan, rate limit).
        body = exc.read()
        if body:
            return body
        raise


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


def _json(raw: bytes, provider: str, symbol: str) -> dict:
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise PriceFetchError(
            f"{provider} sent an unreadable answer for '{symbol}'. The "
            "service may be down; try again later.") from exc
    if not isinstance(data, dict):
        raise PriceFetchError(
            f"{provider} sent an unexpected answer for '{symbol}'. Try "
            "again later.")
    return data


def fetch_twelvedata(symbol: str, start: date, end: date,
                     apikey: str = "") -> dict[date, float]:
    """Return daily closes from Twelve Data.

    Parameters
    ----------
    symbol : str
        The ticker as listed on Twelve Data, e.g. ``AAPL`` or ``VT``.
    start : date
        The first day requested.
    end : date
        The last day requested.
    apikey : str
        The user's Twelve Data API key; sent as a request header.

    Returns
    -------
    dict of date to float
        The closing price per trading day.

    Raises
    ------
    PriceFetchError
        If the key is missing or rejected, the symbol is unknown or not in
        the user's plan, the rate limit is reached, or the request fails.
    """
    if not apikey:
        raise PriceFetchError(TWELVE_KEY_HELP)
    # end_date is exclusive on Twelve Data.
    url = TWELVE_URL.format(sym=urllib.parse.quote(symbol.upper()),
                            d1=start.isoformat(),
                            d2=(end + timedelta(days=1)).isoformat())
    try:
        raw = _get(url, headers={"Authorization": "apikey " + apikey})
    except Exception as exc:
        raise PriceFetchError(f"Twelve Data could not be reached for "
                              f"{symbol}: {exc}") from exc
    data = _json(raw, "Twelve Data", symbol)
    if data.get("status") == "error":
        code, msg = data.get("code"), str(data.get("message", ""))
        if code == 401:
            raise PriceFetchError("Twelve Data did not accept the API key. "
                                  + TWELVE_KEY_HELP)
        if code == 429:
            raise PriceFetchError(
                "Twelve Data's free limit (8 requests a minute, 800 a day) "
                "was reached. Try again in a minute, or tomorrow.")
        if code == 403 or "plan" in msg.lower():
            raise PriceFetchError(
                f"'{symbol}' is not included in your Twelve Data plan (the "
                "free plan covers US listings). Use Alpha Vantage for other "
                "markets.")
        raise PriceFetchError(
            f"Twelve Data returned no prices for '{symbol}': {msg} Check the "
            "symbol on twelvedata.com.")
    out = {}
    for v in data.get("values") or []:
        try:
            out[date.fromisoformat(str(v["datetime"])[:10])] = \
                float(v["close"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise PriceFetchError(
            f"Twelve Data returned no prices for '{symbol}' in this period. "
            "Check the symbol on twelvedata.com.")
    return out


def fetch_alphavantage(symbol: str, start: date, end: date,
                       apikey: str = "") -> dict[date, float]:
    """Return daily closes from Alpha Vantage (last 100 trading days).

    Parameters
    ----------
    symbol : str
        The Alpha Vantage symbol, with an exchange suffix outside the US,
        e.g. ``IBM`` or ``TSCO.LON``.
    start : date
        The first day kept.
    end : date
        The last day kept.
    apikey : str
        The user's Alpha Vantage API key.

    Returns
    -------
    dict of date to float
        The closing price per trading day between ``start`` and ``end``.

    Raises
    ------
    PriceFetchError
        If the key is missing or rejected, the symbol is unknown, the daily
        limit is reached, or the request fails.
    """
    if not apikey:
        raise PriceFetchError(ALPHA_KEY_HELP)
    url = ALPHA_URL.format(sym=urllib.parse.quote(symbol.upper()),
                           key=urllib.parse.quote(apikey))
    try:
        raw = _get(url)
    except Exception as exc:
        raise PriceFetchError(f"Alpha Vantage could not be reached for "
                              f"{symbol}: {exc}") from exc
    data = _json(raw, "Alpha Vantage", symbol)
    series = data.get("Time Series (Daily)")
    if not series:
        note = str(data.get("Information") or data.get("Note") or "")
        if "apikey" in note.lower() and "invalid" in note.lower():
            raise PriceFetchError("Alpha Vantage did not accept the API "
                                  "key. " + ALPHA_KEY_HELP)
        if note:
            raise PriceFetchError(
                "Alpha Vantage's free limit (25 requests a day) was "
                "reached or the request was refused: " + note[:200])
        raise PriceFetchError(
            f"Alpha Vantage returned no prices for '{symbol}'. Check the "
            "symbol and its exchange suffix (e.g. TSCO.LON) with the symbol "
            "search on alphavantage.co.")
    out = {}
    for day, row in series.items():
        try:
            d = date.fromisoformat(day[:10])
            if start <= d <= end:
                out[d] = float(row["4. close"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise PriceFetchError(
            f"Alpha Vantage has no prices for '{symbol}' in this period.")
    return out


def yahoo_symbol(symbol: str, provider: str = "yahoo") -> str:
    """Return the Yahoo Finance symbol for a symbol of another provider.

    Parameters
    ----------
    symbol : str
        The symbol as entered, e.g. ``vt.us`` (stooq) or ``TSCO.LON``.
    provider : str
        The provider the symbol was written for.
    """
    sym = symbol.strip()
    if provider in ("stooq", "alphavantage") and "." in sym:
        base, suffix = sym.rsplit(".", 1)
        if suffix.lower() in _SUFFIX:
            return base.upper() + _SUFFIX[suffix.lower()]
    return sym.upper() if provider != "yahoo" else sym


def fetch_yahoo(symbol: str, start: date, end: date) -> dict[date, float]:
    """Return daily closes from Yahoo Finance (no key needed).

    Parameters
    ----------
    symbol : str
        The Yahoo Finance symbol, e.g. ``AAPL`` or ``VWRL.L``.
    start : date
        The first day requested.
    end : date
        The last day requested.

    Returns
    -------
    dict of date to float
        The closing price per trading day.

    Raises
    ------
    PriceFetchError
        If Yahoo cannot be reached or does not know the symbol.
    """
    p1 = int(datetime(start.year, start.month, start.day,
                      tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(end.year, end.month, end.day,
                      tzinfo=timezone.utc).timestamp()) + 86400
    url = YAHOO_URL.format(sym=urllib.parse.quote(symbol), p1=p1, p2=p2)
    try:
        raw = _get(url, headers={"User-Agent": _YAHOO_UA})
    except Exception as exc:
        raise PriceFetchError(f"Yahoo Finance could not be reached for "
                              f"{symbol}: {exc}. Check the internet "
                              "connection and try again.") from exc
    data = _json(raw, "Yahoo Finance", symbol).get("chart") or {}
    result = (data.get("result") or [None])[0]
    if not result:
        err = (data.get("error") or {}).get("description") or "no data"
        raise PriceFetchError(
            f"Yahoo Finance has no prices for '{symbol}' ({err}). Use the "
            "symbol shown on finance.yahoo.com, with the exchange suffix "
            "for non-US listings (e.g. VWRL.L, SAP.DE, NESN.SW).")
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    offset = int((result.get("meta") or {}).get("gmtoffset") or 0)
    out = {}
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts + offset, timezone.utc).date()
        if start <= day <= end:
            out[day] = float(close)
    if not out:
        raise PriceFetchError(
            f"Yahoo Finance has no prices for '{symbol}' in this period.")
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
    if holding.price_source in ("stooq", "twelvedata", "alphavantage"):
        # The keyed providers are gone since 0.7.1: move to Yahoo Finance.
        holding.price_symbol = yahoo_symbol(
            holding.price_symbol or holding.symbol, holding.price_source)
        holding.price_source = "yahoo"
    last = db.scalar(select(AssetPrice.price_date).where(
        AssetPrice.holding_id == holding.id,
        AssetPrice.source == holding.price_source)
        .order_by(AssetPrice.price_date.desc()).limit(1))
    start = (last - timedelta(days=7)) if last else \
        today - timedelta(days=HISTORY_DAYS)
    symbol = holding.price_symbol or holding.symbol
    if holding.price_source == "yahoo":
        prices = fetch_yahoo(symbol, start, today)
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
