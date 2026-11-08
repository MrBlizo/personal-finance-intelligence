"""Settings, exchange rates, accounts, categories and rules."""
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import schemas as s
from ..db import get_db
from ..migrations import MIGRATIONS
from ..models import (
    Account, Category, CategoryRule, ExchangeRate, Holding, SavingsGoal,
    Setting, Transaction)
from ..services.fx import FxConverter
from ..services.fx_fetch import FxFetchError, update_rates
from ..seed import get_setting
from ..services.importer import Categorizer
from ..services.ledger import base_currency, net_worth
from .common import category_names, commit_or_409, get_or_404

router = APIRouter(prefix="/api")


# --- settings --------------------------------------------------------------
def _currencies(db: Session) -> list[str]:
    found = set(db.scalars(select(Account.currency).distinct()))
    found |= set(db.scalars(select(Holding.currency).distinct()))
    found |= set(db.scalars(select(SavingsGoal.currency).distinct()))
    return sorted(found)


@router.get("/settings", response_model=s.SettingsOut)
def get_settings_(db: Session = Depends(get_db)):
    return {"base_currency": base_currency(db),
            "currencies_in_use": _currencies(db),
            "schema_version": max(v for v, _, _ in MIGRATIONS),
            "fx_auto_update": get_setting(db, "fx_auto_update", "1") == "1",
            "fx_last_update": get_setting(db, "fx_last_update", "") or None}


def _put(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


@router.put("/settings", response_model=s.SettingsOut)
def put_settings(body: s.SettingsIn, db: Session = Depends(get_db)):
    _put(db, "base_currency", body.base_currency)
    if body.fx_auto_update is not None:
        _put(db, "fx_auto_update", "1" if body.fx_auto_update else "0")
    db.commit()
    return get_settings_(db)


@router.post("/fx-rates/fetch")
def fetch_rates(backfill: bool = True, db: Session = Depends(get_db)):
    """Download current (and monthly historical) rates from the internet."""
    try:
        return update_rates(db, base_currency(db), backfill)
    except FxFetchError as exc:
        db.rollback()
        raise HTTPException(502, str(exc)) from exc


# --- exchange rates --------------------------------------------------------
@router.get("/fx-rates", response_model=list[s.FxRateOut])
def list_rates(db: Session = Depends(get_db)):
    return db.scalars(select(ExchangeRate).order_by(
        ExchangeRate.rate_date.desc(), ExchangeRate.from_currency)).all()


@router.post("/fx-rates", response_model=s.FxRateOut, status_code=201)
def create_rate(body: s.FxRateIn, db: Session = Depends(get_db)):
    if body.from_currency == body.to_currency:
        raise HTTPException(
            422, "From and to currency are identical; a rate is only "
            "needed between two different currencies.")
    existing = db.scalar(select(ExchangeRate).where(
        ExchangeRate.rate_date == body.rate_date,
        ExchangeRate.from_currency == body.from_currency,
        ExchangeRate.to_currency == body.to_currency))
    if existing:
        existing.rate, existing.source = body.rate, body.source
        db.commit()
        return existing
    rate = ExchangeRate(**body.model_dump())
    db.add(rate)
    commit_or_409(db, "exchange rate")
    return rate


@router.delete("/fx-rates/{rate_id}", status_code=204)
def delete_rate(rate_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ExchangeRate, rate_id))
    db.commit()
    return Response(status_code=204)


@router.get("/fx-rates/missing")
def missing_rates(db: Session = Depends(get_db)):
    """List currencies in use that cannot be converted to base."""
    fx, base = FxConverter.from_db(db), base_currency(db)
    missing = [c for c in _currencies(db)
               if fx.try_rate(c, base) is None]
    return {"base_currency": base, "missing": missing}


# --- accounts --------------------------------------------------------------
@router.get("/accounts", response_model=list[s.AccountOut])
def list_accounts(include_archived: bool = True,
                  db: Session = Depends(get_db)):
    fx, base = FxConverter.from_db(db), base_currency(db)
    nw = {a["id"]: a for a in net_worth(db, fx, base).by_account}
    stmt = select(Account).order_by(Account.is_archived, Account.type,
                                    Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    out = []
    for acc in db.scalars(stmt):
        item = s.AccountOut.model_validate(acc)
        info = nw.get(acc.id, {})
        item.balance = info.get("balance", 0.0)
        item.balance_base = info.get("balance_base")
        item.holdings_base = info.get("holdings_base", 0.0)
        out.append(item)
    return out


@router.post("/accounts", response_model=s.AccountOut, status_code=201)
def create_account(body: s.AccountIn, db: Session = Depends(get_db)):
    acc = Account(**body.model_dump())
    db.add(acc)
    commit_or_409(db, "account")
    return s.AccountOut.model_validate(acc)


@router.put("/accounts/{account_id}", response_model=s.AccountOut)
def update_account(account_id: int, body: s.AccountIn,
                   db: Session = Depends(get_db)):
    acc = get_or_404(db, Account, account_id)
    if body.currency != acc.currency and db.scalar(select(
            func.count()).where(Transaction.account_id == acc.id)):
        raise HTTPException(
            409, "The currency of an account with transactions cannot be "
            "changed, because existing amounts would be misread. Create a "
            "new account in the new currency and transfer the balance.")
    for key, value in body.model_dump().items():
        setattr(acc, key, value)
    commit_or_409(db, "account")
    return s.AccountOut.model_validate(acc)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, confirm: bool = False,
                   db: Session = Depends(get_db)):
    acc = get_or_404(db, Account, account_id)
    count = db.scalar(select(func.count()).where(
        Transaction.account_id == acc.id))
    if count and not confirm:
        raise HTTPException(
            409, f"Account '{acc.name}' has {count} transactions that "
            "would be deleted too. Archive the account instead, or repeat "
            "the request with confirm=true.")
    db.delete(acc)
    db.commit()
    return Response(status_code=204)


# --- categories ------------------------------------------------------------
@router.get("/categories", response_model=list[s.CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    names = category_names(db)
    cats = db.scalars(select(Category)).all()
    out = [s.CategoryOut.model_validate(c) for c in cats]
    for item in out:
        item.full_name = names[item.id]
    return sorted(out, key=lambda c: (c.kind, c.full_name.lower()))


def _check_parent(db: Session, body: s.CategoryIn,
                  self_id: int | None = None) -> None:
    if body.parent_id is None:
        return
    parent = get_or_404(db, Category, body.parent_id)
    if parent.kind != body.kind or parent.parent_id is not None \
            or parent.id == self_id:
        raise HTTPException(
            422, "A parent category must be a top-level category of the "
            "same kind (income/expense). Choose another parent.")


@router.post("/categories", response_model=s.CategoryOut, status_code=201)
def create_category(body: s.CategoryIn, db: Session = Depends(get_db)):
    _check_parent(db, body)
    cat = Category(**body.model_dump())
    db.add(cat)
    commit_or_409(db, "category")
    return cat


@router.put("/categories/{cat_id}", response_model=s.CategoryOut)
def update_category(cat_id: int, body: s.CategoryIn,
                    db: Session = Depends(get_db)):
    cat = get_or_404(db, Category, cat_id)
    _check_parent(db, body, cat_id)
    if body.kind != cat.kind:
        raise HTTPException(
            422, "The kind of an existing category cannot change because "
            "its transactions would flip between income and expense. "
            "Create a new category instead.")
    for key, value in body.model_dump().items():
        setattr(cat, key, value)
    commit_or_409(db, "category")
    return cat


@router.delete("/categories/{cat_id}", status_code=204)
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Category, cat_id))
    db.commit()
    return Response(status_code=204)


# --- rules -----------------------------------------------------------------
@router.get("/rules", response_model=list[s.RuleOut])
def list_rules(db: Session = Depends(get_db)):
    return db.scalars(select(CategoryRule).order_by(
        CategoryRule.priority.desc(), CategoryRule.id)).all()


def _validate_rule(db: Session, body: s.RuleIn) -> None:
    get_or_404(db, Category, body.category_id)
    if body.is_regex:
        try:
            re.compile(body.pattern)
        except re.error as exc:
            raise HTTPException(
                422, f"Invalid regular expression: {exc}. Fix the pattern "
                "or untick 'regex' to match plain text.") from exc


@router.post("/rules", response_model=s.RuleOut, status_code=201)
def create_rule(body: s.RuleIn, db: Session = Depends(get_db)):
    _validate_rule(db, body)
    rule = CategoryRule(**body.model_dump())
    db.add(rule)
    db.commit()
    return rule


@router.put("/rules/{rule_id}", response_model=s.RuleOut)
def update_rule(rule_id: int, body: s.RuleIn,
                db: Session = Depends(get_db)):
    rule = get_or_404(db, CategoryRule, rule_id)
    _validate_rule(db, body)
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    db.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, CategoryRule, rule_id))
    db.commit()
    return Response(status_code=204)


@router.post("/rules/apply")
def apply_rules(only_uncategorized: bool = True,
                db: Session = Depends(get_db)):
    """Re-run the rules over existing (non-transfer) transactions."""
    cz = Categorizer(db)
    stmt = select(Transaction).where(Transaction.kind != "transfer",
                                     Transaction.trade_id.is_(None))
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    changed = 0
    for txn in db.scalars(stmt):
        cat = cz.match(txn.description, txn.merchant)
        if cat is not None and cat != txn.category_id:
            txn.category_id = cat
            txn.kind = cz.kind_for(cat, txn.amount)
            changed += 1
    db.commit()
    return {"updated": changed}


@router.post("/categories/{cat_id}/merge-into/{target_id}")
def merge_category(cat_id: int, target_id: int,
                   db: Session = Depends(get_db)):
    """Move all transactions of one category to another, then delete it."""
    src = get_or_404(db, Category, cat_id)
    dst = get_or_404(db, Category, target_id)
    if src.kind != dst.kind or src.id == dst.id:
        raise HTTPException(
            422, "Categories can only be merged into a different category "
            "of the same kind.")
    moved = db.execute(update(Transaction).where(
        Transaction.category_id == src.id).values(category_id=dst.id))
    db.delete(src)
    db.commit()
    return {"moved": moved.rowcount}
