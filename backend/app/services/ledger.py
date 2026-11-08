"""Balances, investment positions and net worth."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    LIQUID_TYPES, Account, AssetPrice, Holding, InvestmentTrade,
    Transaction)
from ..seed import get_setting
from .fx import FxConverter

ZERO = Decimal("0")


def base_currency(db: Session) -> str:
    """Return the reporting currency stored in settings."""
    return get_setting(db, "base_currency", "CHF")


def account_balances(db: Session, as_of: date | None = None
                     ) -> dict[int, Decimal]:
    """Return the cash balance of every account in its own currency.

    Parameters
    ----------
    db : Session
        The open database session.
    as_of : date, optional
        The date (inclusive) up to which transactions are counted.

    Returns
    -------
    dict of int to Decimal
        The balance keyed by account id.
    """
    stmt = select(Transaction.account_id, func.sum(Transaction.amount))
    if as_of is not None:
        stmt = stmt.where(Transaction.txn_date <= as_of)
    sums = dict(db.execute(stmt.group_by(Transaction.account_id)).all())
    out = {}
    for acc in db.scalars(select(Account)):
        opening = (acc.opening_balance
                   if as_of is None or acc.opening_date <= as_of else ZERO)
        out[acc.id] = opening + (sums.get(acc.id) or ZERO)
    return out


@dataclass
class Position:
    """Average-cost position derived from a holding's trades."""

    quantity: float = 0.0
    cost_basis: float = 0.0
    realized_pl: float = 0.0
    dividends: float = 0.0
    fees: float = 0.0

    @property
    def avg_cost(self) -> float:
        return self.cost_basis / self.quantity if self.quantity else 0.0


def compute_position(trades: list[InvestmentTrade],
                     as_of: date | None = None) -> Position:
    """Replay trades with the average-cost method.

    Parameters
    ----------
    trades : list of InvestmentTrade
        The trades of a single holding, in any order.
    as_of : date, optional
        The date (inclusive) up to which trades are replayed.

    Returns
    -------
    Position
        The quantity, cost basis and income of the holding.

    Raises
    ------
    ValueError
        If a sell exceeds the quantity held at that time.
    """
    pos = Position()
    ordered = sorted(trades, key=lambda t: (t.trade_date, t.id or 0))
    for t in ordered:
        if as_of is not None and t.trade_date > as_of:
            break
        qty, price, fees = float(t.quantity), float(t.price), float(t.fees)
        if t.trade_type == "buy":
            pos.quantity += qty
            pos.cost_basis += qty * price + fees
            pos.fees += fees
        elif t.trade_type == "sell":
            if qty > pos.quantity + 1e-9:
                raise ValueError(
                    f"Sell of {qty} on {t.trade_date} exceeds the "
                    f"{pos.quantity} units held. Check the trade history "
                    "for a missing buy or a wrong quantity.")
            avg = pos.avg_cost
            pos.realized_pl += qty * (price - avg) - fees
            pos.cost_basis -= qty * avg
            pos.quantity -= qty
            pos.fees += fees
        elif t.trade_type == "dividend":
            pos.dividends += float(t.cash_amount or 0)
        elif t.trade_type == "fee":
            fee = float(t.cash_amount or t.fees)
            pos.fees += fee
            pos.realized_pl -= fee
    if abs(pos.quantity) < 1e-9:
        pos.quantity, pos.cost_basis = 0.0, 0.0
    return pos


def latest_price(db: Session, holding_id: int,
                 as_of: date | None = None) -> AssetPrice | None:
    """Return the most recent price row on or before ``as_of``."""
    stmt = select(AssetPrice).where(AssetPrice.holding_id == holding_id)
    if as_of is not None:
        stmt = stmt.where(AssetPrice.price_date <= as_of)
    return db.scalar(stmt.order_by(AssetPrice.price_date.desc()).limit(1))


def holding_valuations(db: Session, fx: FxConverter, base: str,
                       as_of: date | None = None) -> list[dict]:
    """Value every holding in its own currency and in ``base``.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The reporting currency.
    as_of : date, optional
        The valuation date; today's data if omitted.

    Returns
    -------
    list of dict
        One entry per holding with position, price and value fields.
        ``market_value`` is ``None`` when no price has been entered.
    """
    out = []
    for h in db.scalars(select(Holding).order_by(Holding.symbol)):
        trades = list(db.scalars(select(InvestmentTrade).where(
            InvestmentTrade.holding_id == h.id)))
        pos = compute_position(trades, as_of)
        price = latest_price(db, h.id, as_of)
        value = pos.quantity * float(price.price) if price else None
        rate = fx.try_rate(h.currency, base, as_of)
        unrealized = value - pos.cost_basis if value is not None else None
        out.append({
            "id": h.id, "account_id": h.account_id, "symbol": h.symbol,
            "name": h.name, "asset_class": h.asset_class,
            "currency": h.currency, "quantity": pos.quantity,
            "price_source": h.price_source, "price_symbol": h.price_symbol,
            "notes": h.notes,
            "avg_cost": pos.avg_cost, "cost_basis": pos.cost_basis,
            "last_price": float(price.price) if price else None,
            "price_date": price.price_date if price else None,
            "market_value": value, "unrealized_pl": unrealized,
            "unrealized_pl_pct": (unrealized / pos.cost_basis
                                  if unrealized is not None
                                  and pos.cost_basis else None),
            "realized_pl": pos.realized_pl, "dividends": pos.dividends,
            "market_value_base": (value * rate if value is not None
                                  and rate is not None else None),
            "cost_basis_base": (pos.cost_basis * rate
                                if rate is not None else None),
        })
    return out


@dataclass
class NetWorth:
    """Net worth snapshot in the base currency."""

    total: float = 0.0
    liquid: float = 0.0
    investment_cash: float = 0.0
    holdings: float = 0.0
    liabilities: float = 0.0
    by_account: list[dict] = field(default_factory=list)
    missing_fx: set[str] = field(default_factory=set)
    unpriced_holdings: list[str] = field(default_factory=list)


def net_worth(db: Session, fx: FxConverter, base: str,
              as_of: date | None = None) -> NetWorth:
    """Compute net worth (cash balances plus holdings) in ``base``.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency values.
    base : str
        The reporting currency.
    as_of : date, optional
        The valuation date; latest data if omitted.

    Returns
    -------
    NetWorth
        The totals, per-account breakdown and data-quality warnings.
    """
    nw = NetWorth()
    balances = account_balances(db, as_of)
    holdings = holding_valuations(db, fx, base, as_of)
    held_by_acc: dict[int, float] = {}
    for h in holdings:
        if h["quantity"] and h["market_value_base"] is None:
            nw.unpriced_holdings.append(h["symbol"])
        held_by_acc[h["account_id"]] = (held_by_acc.get(h["account_id"], 0)
                                        + (h["market_value_base"] or 0))
    for acc in db.scalars(select(Account).order_by(Account.name)):
        bal = balances.get(acc.id, ZERO)
        rate = fx.try_rate(acc.currency, base, as_of, nw.missing_fx)
        cash_base = float(bal) * rate if rate is not None else None
        held = held_by_acc.get(acc.id, 0.0)
        total_acc = (cash_base or 0.0) + held
        nw.by_account.append({
            "id": acc.id, "name": acc.name, "type": acc.type,
            "currency": acc.currency, "balance": float(bal),
            "balance_base": cash_base, "holdings_base": held,
            "total_base": total_acc if cash_base is not None else None})
        if cash_base is None:
            continue
        if acc.type in LIQUID_TYPES:
            nw.liquid += cash_base
        elif acc.type == "investment":
            nw.investment_cash += cash_base
        if acc.type == "loan" or (acc.type == "credit_card"
                                  and cash_base < 0):
            nw.liabilities += min(cash_base, 0.0)
        nw.holdings += held
        nw.total += total_acc
    return nw
