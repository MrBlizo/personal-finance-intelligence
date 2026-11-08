"""Holdings, trades, prices and portfolio summary.

A buy/sell with ``affects_cash`` books a matching cash transaction (kind
``transfer``) on the holding's account, so cash and holdings stay
consistent. Dividends book income, fees book an expense.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as s
from ..db import get_db
from ..models import (
    Account, AssetPrice, Category, Holding, InvestmentTrade, Transaction)
from ..services import performance as perf
from ..services import prices
from ..services.fx import FxConverter
from ..services.ledger import base_currency, compute_position, \
    holding_valuations
from .common import commit_or_409, get_or_404

router = APIRouter(prefix="/api")
CENT = Decimal("0.01")


def _category(db: Session, name: str, kind: str) -> int | None:
    return db.scalar(select(Category.id).where(Category.name == name,
                                               Category.kind == kind))


def _cash_leg(db: Session, h: Holding, t: InvestmentTrade
              ) -> Transaction | None:
    gross = t.quantity * t.price
    if t.trade_type == "buy":
        amount, kind, cat = -(gross + t.fees), "transfer", None
        text = f"Buy {t.quantity.normalize()} {h.symbol}"
    elif t.trade_type == "sell":
        amount, kind, cat = gross - t.fees, "transfer", None
        text = f"Sell {t.quantity.normalize()} {h.symbol}"
    elif t.trade_type == "dividend":
        amount = t.cash_amount or Decimal(0)
        kind, cat = "income", _category(db, "Dividends", "income")
        text = f"Dividend {h.symbol}"
    else:
        amount = -(t.cash_amount or t.fees)
        kind, cat = "expense", _category(db, "Bank Fees", "expense")
        text = f"Fee {h.symbol}"
    if amount == 0:
        return None
    acc = h.account
    if acc.currency != h.currency:
        rate = FxConverter.from_db(db).try_rate(h.currency, acc.currency,
                                                t.trade_date)
        if rate is None:
            raise HTTPException(
                422, f"The holding is priced in {h.currency} but the "
                f"account uses {acc.currency}, and no rate exists. Add an "
                "exchange rate or untick 'affects cash'.")
        amount = amount * Decimal(str(rate))
    return Transaction(account_id=acc.id, txn_date=t.trade_date,
                       amount=amount.quantize(CENT), kind=kind,
                       category_id=cat, description=text, trade_id=t.id)


@router.get("/holdings")
def list_holdings(db: Session = Depends(get_db)):
    return holding_valuations(db, FxConverter.from_db(db),
                              base_currency(db))


def _check_holding(db: Session, body: s.HoldingIn) -> None:
    acc = get_or_404(db, Account, body.account_id)
    if acc.type != "investment":
        raise HTTPException(
            422, f"'{acc.name}' is a {acc.type} account. Holdings belong "
            "to an account of type 'investment'.")


@router.post("/holdings", status_code=201)
def create_holding(body: s.HoldingIn, db: Session = Depends(get_db)):
    _check_holding(db, body)
    h = Holding(**{**body.model_dump(), "symbol": body.symbol.upper()})
    db.add(h)
    commit_or_409(db, "holding")
    return {"id": h.id}


@router.put("/holdings/{holding_id}")
def update_holding(holding_id: int, body: s.HoldingIn,
                   db: Session = Depends(get_db)):
    h = get_or_404(db, Holding, holding_id)
    _check_holding(db, body)
    for key, value in body.model_dump().items():
        setattr(h, key, value)
    h.symbol = h.symbol.upper()
    commit_or_409(db, "holding")
    return {"id": h.id}


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Holding, holding_id))
    db.commit()
    return Response(status_code=204)


@router.get("/holdings/{holding_id}/trades",
            response_model=list[s.TradeOut])
def list_trades(holding_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(InvestmentTrade).where(
        InvestmentTrade.holding_id == holding_id).order_by(
        InvestmentTrade.trade_date.desc(), InvestmentTrade.id.desc())).all()


@router.post("/holdings/{holding_id}/trades", response_model=s.TradeOut,
             status_code=201)
def create_trade(holding_id: int, body: s.TradeIn,
                 db: Session = Depends(get_db)):
    h = get_or_404(db, Holding, holding_id)
    data = body.model_dump(exclude={"affects_cash"})
    if body.trade_type in ("buy", "sell") and body.quantity <= 0:
        raise HTTPException(422, "Buys and sells need a quantity above 0.")
    if body.trade_type in ("dividend", "fee") and not (
            body.cash_amount or body.fees):
        raise HTTPException(
            422, "Dividends and fees need a cash amount above 0.")
    trade = InvestmentTrade(holding_id=h.id, **data)
    db.add(trade)
    db.flush()
    existing = list(db.scalars(select(InvestmentTrade).where(
        InvestmentTrade.holding_id == h.id)))
    try:
        compute_position(existing)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    if body.affects_cash:
        leg = _cash_leg(db, h, trade)
        if leg is not None:
            db.add(leg)
    if body.trade_type in ("buy", "sell") and body.price > 0:
        price = db.scalar(select(AssetPrice).where(
            AssetPrice.holding_id == h.id,
            AssetPrice.price_date == body.trade_date))
        if price is None:
            db.add(AssetPrice(holding_id=h.id, price_date=body.trade_date,
                              price=body.price, source="trade"))
    db.commit()
    return trade


@router.delete("/trades/{trade_id}", status_code=204)
def delete_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = get_or_404(db, InvestmentTrade, trade_id)
    remaining = [t for t in db.scalars(select(InvestmentTrade).where(
        InvestmentTrade.holding_id == trade.holding_id))
        if t.id != trade.id]
    try:
        compute_position(remaining)
    except ValueError as exc:
        raise HTTPException(
            409, f"Deleting this trade would leave an invalid history: "
            f"{exc}") from exc
    db.delete(trade)
    db.commit()
    return Response(status_code=204)


@router.get("/holdings/{holding_id}/prices",
            response_model=list[s.PriceOut])
def list_prices(holding_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(AssetPrice).where(
        AssetPrice.holding_id == holding_id).order_by(
        AssetPrice.price_date.desc())).all()


@router.post("/holdings/{holding_id}/prices", response_model=s.PriceOut,
             status_code=201)
def upsert_price(holding_id: int, body: s.PriceIn,
                 db: Session = Depends(get_db)):
    get_or_404(db, Holding, holding_id)
    row = db.scalar(select(AssetPrice).where(
        AssetPrice.holding_id == holding_id,
        AssetPrice.price_date == body.price_date))
    if row is None:
        row = AssetPrice(holding_id=holding_id, **body.model_dump())
        db.add(row)
    else:
        row.price, row.source = body.price, body.source
    db.commit()
    return row


@router.delete("/prices/{price_id}", status_code=204)
def delete_price(price_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, AssetPrice, price_id))
    db.commit()
    return Response(status_code=204)


@router.get("/investments/performance")
def performance(db: Session = Depends(get_db)):
    """XIRR, time-weighted return, dividend income and allocation drift."""
    return perf.portfolio(db, FxConverter.from_db(db), base_currency(db))


@router.post("/prices/update")
def update_all_prices(db: Session = Depends(get_db)):
    """Download prices for all holdings with an online price source."""
    return prices.update_prices(db)


@router.post("/holdings/{holding_id}/prices/update")
def update_one_price(holding_id: int, db: Session = Depends(get_db)):
    """Download prices for one holding."""
    h = get_or_404(db, Holding, holding_id)
    if h.price_source == "manual":
        raise HTTPException(
            422, f"{h.symbol} uses manual prices. Edit the holding and "
            "choose an online price source (stooq or CoinGecko) first.")
    try:
        added = prices.update_holding(db, h)
    except prices.PriceFetchError as exc:
        db.rollback()
        raise HTTPException(502, str(exc)) from exc
    db.commit()
    return {"new_prices": added}
