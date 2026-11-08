"""Currency conversion using manually entered exchange rates.

Lookup order for a pair (A -> B) on a date: the latest direct rate on or
before that date, otherwise the inverse rate, otherwise a two-step route
through any intermediate currency. If only later rates exist, the earliest
one is used and the conversion is reported as approximate.
"""
import bisect
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExchangeRate


class FxRateMissing(LookupError):
    """Raised when no route exists between two currencies."""

    def __init__(self, from_currency: str, to_currency: str) -> None:
        self.from_currency = from_currency
        self.to_currency = to_currency
        super().__init__(
            f"No exchange rate available for {from_currency} -> "
            f"{to_currency}. Amounts in {from_currency} cannot be shown in "
            f"{to_currency}. Add a rate under Settings > Exchange rates.")


class FxConverter:
    """Convert amounts between currencies with in-memory rate tables.

    Parameters
    ----------
    rates : list of ExchangeRate
        The exchange-rate rows to use.
    """

    def __init__(self, rates: list[ExchangeRate]) -> None:
        series: dict[tuple[str, str], list[tuple[date, float]]] = (
            defaultdict(list))
        for r in rates:
            series[(r.from_currency, r.to_currency)].append(
                (r.rate_date, float(r.rate)))
        self._dates: dict[tuple[str, str], list[date]] = {}
        self._values: dict[tuple[str, str], list[float]] = {}
        for pair, points in series.items():
            points.sort()
            self._dates[pair] = [d for d, _ in points]
            self._values[pair] = [v for _, v in points]
        self.currencies = {c for pair in series for c in pair}
        self.approximate_pairs: set[tuple[str, str]] = set()
        self._cache: dict[tuple[str, str, date | None], float] = {}

    @classmethod
    def from_db(cls, db: Session) -> "FxConverter":
        """Build a converter from all rates stored in the database.

        Parameters
        ----------
        db : Session
            The open database session.

        Returns
        -------
        FxConverter
            The converter holding every stored rate.
        """
        return cls(list(db.scalars(select(ExchangeRate))))

    def _direct(self, frm: str, to: str, on: date | None) -> float | None:
        pair = (frm, to)
        if pair not in self._dates:
            return None
        dates, values = self._dates[pair], self._values[pair]
        if on is None:
            return values[-1]
        idx = bisect.bisect_right(dates, on) - 1
        if idx < 0:
            self.approximate_pairs.add(pair)
            return values[0]
        return values[idx]

    def _one_hop(self, frm: str, to: str, on: date | None) -> float | None:
        direct = self._direct(frm, to, on)
        if direct is not None:
            return direct
        inverse = self._direct(to, frm, on)
        return 1.0 / inverse if inverse else None

    def rate(self, frm: str, to: str, on: date | None = None) -> float:
        """Return how many units of ``to`` one unit of ``frm`` buys.

        Parameters
        ----------
        frm : str
            The source currency code.
        to : str
            The target currency code.
        on : date, optional
            The valuation date; the latest available rate if omitted.

        Returns
        -------
        float
            The conversion factor.

        Raises
        ------
        FxRateMissing
            If no direct, inverse or two-step route exists.
        """
        if frm == to:
            return 1.0
        key = (frm, to, on)
        if key in self._cache:
            return self._cache[key]
        value = self._one_hop(frm, to, on)
        if value is None:
            for mid in self.currencies - {frm, to}:
                a = self._one_hop(frm, mid, on)
                b = self._one_hop(mid, to, on) if a else None
                if a and b:
                    value = a * b
                    break
        if value is None:
            raise FxRateMissing(frm, to)
        self._cache[key] = value
        return value

    def convert(self, amount: Decimal | float, frm: str, to: str,
                on: date | None = None) -> float:
        """Convert ``amount`` from ``frm`` to ``to``.

        Parameters
        ----------
        amount : Decimal or float
            The amount in the source currency.
        frm : str
            The source currency code.
        to : str
            The target currency code.
        on : date, optional
            The valuation date; the latest available rate if omitted.

        Returns
        -------
        float
            The converted amount.
        """
        return float(amount) * self.rate(frm, to, on)

    def try_rate(self, frm: str, to: str, on: date | None = None,
                 missing: set[str] | None = None) -> float | None:
        """Return the rate, or ``None`` (recording ``frm``) if missing.

        Parameters
        ----------
        frm : str
            The source currency code.
        to : str
            The target currency code.
        on : date, optional
            The valuation date.
        missing : set of str, optional
            The set that collects currencies without a route.

        Returns
        -------
        float or None
            The conversion factor, or ``None`` if unavailable.
        """
        try:
            return self.rate(frm, to, on)
        except FxRateMissing:
            if missing is not None:
                missing.add(frm)
            return None
