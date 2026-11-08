"""Unit tests for parsing, FX routing, positions and schedules."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.services.fx import FxConverter, FxRateMissing
from app.services.importer import parse_amount
from app.services.ledger import compute_position
from app.services.planning import add_months, occurrences


@pytest.mark.parametrize("text,dec,expected", [
    ("1'234.50", ".", "1234.50"), ("-12,30", ",", "-12.30"),
    ("1.234,56", ",", "1234.56"), ("(45.00)", ".", "-45.00"),
    ("CHF 9.90", ".", "9.90"), ("120.00-", ".", "-120.00"),
    ("1,234.56", ".", "1234.56"), ("", ".", None)])
def test_parse_amount(text, dec, expected):
    result = parse_amount(text, dec)
    assert result == (Decimal(expected) if expected else None)


def test_parse_amount_rejects_garbage():
    with pytest.raises(ValueError):
        parse_amount("1.2.3", ".")


def _rate(d, a, b, r):
    return NS(rate_date=d, from_currency=a, to_currency=b, rate=r)


def test_fx_direct_inverse_and_triangulation():
    fx = FxConverter([_rate(date(2026, 1, 1), "EUR", "CHF", 0.94),
                      _rate(date(2026, 6, 1), "EUR", "CHF", 0.90),
                      _rate(date(2026, 1, 1), "CHF", "MAD", 11.0)])
    assert fx.rate("EUR", "CHF", date(2026, 3, 1)) == 0.94
    assert fx.rate("EUR", "CHF", date(2026, 7, 1)) == 0.90
    assert fx.rate("CHF", "EUR", date(2026, 7, 1)) == pytest.approx(1 / 0.9)
    assert fx.rate("EUR", "MAD", date(2026, 7, 1)) == pytest.approx(9.9)
    fx.rate("EUR", "CHF", date(2025, 1, 1))
    assert ("EUR", "CHF") in fx.approximate_pairs
    with pytest.raises(FxRateMissing):
        fx.rate("USD", "CHF")


def _trade(i, d, kind, qty=0, price=0, fees=0, cash=None):
    return NS(id=i, trade_date=d, trade_type=kind, quantity=qty,
              price=price, fees=fees, cash_amount=cash)


def test_average_cost_position():
    trades = [_trade(1, date(2026, 1, 1), "buy", 10, 100, 5),
              _trade(2, date(2026, 2, 1), "buy", 10, 120, 5),
              _trade(3, date(2026, 3, 1), "sell", 5, 130, 2),
              _trade(4, date(2026, 3, 5), "dividend", cash=12)]
    pos = compute_position(trades)
    assert pos.quantity == 15
    assert pos.avg_cost == pytest.approx(2210 / 20)
    assert pos.realized_pl == pytest.approx(5 * (130 - 110.5) - 2)
    assert pos.dividends == 12
    with pytest.raises(ValueError):
        compute_position(trades + [_trade(5, date(2026, 4, 1), "sell",
                                          99, 1)])


def test_monthly_occurrences_clamp_to_month_end():
    item = NS(frequency="monthly", start_date=date(2026, 1, 31),
              end_date=None)
    got = occurrences(item, date(2026, 1, 1), date(2026, 4, 30))
    assert got == [date(2026, 1, 31), date(2026, 2, 28),
                   date(2026, 3, 31), date(2026, 4, 30)]
    assert add_months(date(2026, 1, 15), -2) == date(2025, 11, 15)
