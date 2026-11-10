"""Bulk edit, bank reconciliation, debt payoff planner, spending calendar."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (
    Account, Category, DebtTerms, Reconciliation, Tag, Transaction,
    TransactionSplit, TransactionTag)
from ..services import planning_tools as pt
from ..services.frame import expenses, incomes, load_transactions
from ..services.fx import FxConverter
from ..services.ledger import account_balances, base_currency
from .common import commit_or_409, get_or_404
from .extras import _clean_tag, sweep_orphans
from .transactions import _to_out

router = APIRouter(prefix="/api")
DEBT_TYPES = ("loan", "credit_card")


# --- bulk edit ---------------------------------------------------------------
class BulkIn(BaseModel):
    ids: Annotated[list[int], Field(min_length=1, max_length=5000)]
    action: Literal["update", "delete"] = "update"
    category_id: int | None = None
    clear_category: bool = False
    account_id: int | None = None
    add_tags: list[str] = []
    remove_tags: list[str] = []
    cleared: bool | None = None


def _skip(reasons: dict[str, int], why: str) -> None:
    reasons[why] = reasons.get(why, 0) + 1


@router.post("/transactions/bulk")
def bulk_edit(body: BulkIn, db: Session = Depends(get_db)):
    """Change or delete many transactions at once.

    Transactions that cannot take a change keep their values and are
    counted in ``skipped`` with the reason (investment trades, transfers,
    split transactions, reconciled transactions, duplicates).
    """
    txns = list(db.scalars(select(Transaction).where(
        Transaction.id.in_(body.ids))))
    reasons: dict[str, int] = {}
    if body.action == "delete":
        groups, deleted = set(), 0
        for txn in txns:
            if txn.trade_id is not None:
                _skip(reasons, "investment trade")
                continue
            if txn.transfer_group:
                if txn.transfer_group in groups:
                    continue
                groups.add(txn.transfer_group)
                legs = list(db.scalars(select(Transaction).where(
                    Transaction.transfer_group == txn.transfer_group)))
                if any(leg.reconciled for leg in legs):
                    _skip(reasons, "reconciled")
                    continue
                for leg in legs:
                    db.delete(leg)
                    deleted += 1
            elif txn.reconciled:
                _skip(reasons, "reconciled")
            else:
                db.delete(txn)
                deleted += 1
        db.commit()
        sweep_orphans(db, get_settings().subdir("attachments"))
        return {"deleted": deleted, "updated": 0,
                "skipped": sum(reasons.values()), "reasons": reasons}

    category = (get_or_404(db, Category, body.category_id)
                if body.category_id is not None else None)
    target = (get_or_404(db, Account, body.account_id)
              if body.account_id is not None else None)
    split_ids = set(db.scalars(select(TransactionSplit.transaction_id).where(
        TransactionSplit.transaction_id.in_(body.ids))))
    tag_rows = {t.name.lower(): t for t in db.scalars(select(Tag))}
    add = []
    for raw in body.add_tags:
        name = _clean_tag(raw)
        tag = tag_rows.get(name.lower())
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
            tag_rows[name.lower()] = tag
        add.append(tag)
    remove = [tag_rows[n.strip().lower()] for n in body.remove_tags
              if n.strip().lower() in tag_rows]
    have = {(a, b) for a, b in db.execute(select(
        TransactionTag.transaction_id, TransactionTag.tag_id).where(
        TransactionTag.transaction_id.in_(body.ids)))}
    updated = 0
    recategorize = category is not None or body.clear_category
    for txn in txns:
        move = target is not None and target.id != txn.account_id
        clear_change = (body.cleared is not None
                        and body.cleared != txn.cleared)
        why = None
        if txn.trade_id is not None:
            why = "investment trade"
        elif (recategorize or move) and txn.kind == "transfer":
            why = "transfer"
        elif recategorize and txn.id in split_ids:
            why = "split"
        elif (move or clear_change) and txn.reconciled:
            why = "reconciled"
        elif move and txn.fingerprint and db.scalar(
                select(Transaction.id).where(
                    Transaction.account_id == target.id,
                    Transaction.fingerprint == txn.fingerprint)):
            why = "duplicate in target account"
        if why:
            _skip(reasons, why)
            continue
        changed = False
        if recategorize:
            txn.category_id = category.id if category else None
            txn.category_source = "user" if category else None
            txn.kind = (category.kind if category else
                        "income" if txn.amount > 0 else "expense")
            changed = True
        if move:
            txn.account_id = target.id
            txn.cleared = False
            changed = True
        if clear_change:
            txn.cleared = body.cleared
            changed = True
        for tag in add:
            if (txn.id, tag.id) not in have:
                db.add(TransactionTag(transaction_id=txn.id, tag_id=tag.id))
                have.add((txn.id, tag.id))
                changed = True
        for tag in remove:
            if (txn.id, tag.id) in have:
                db.execute(delete(TransactionTag).where(
                    TransactionTag.transaction_id == txn.id,
                    TransactionTag.tag_id == tag.id))
                have.discard((txn.id, tag.id))
                changed = True
        updated += changed
    commit_or_409(db, "transaction")
    return {"updated": updated, "deleted": 0,
            "skipped": sum(reasons.values()), "reasons": reasons}


# --- reconciliation ----------------------------------------------------------
class ReconcileIn(BaseModel):
    statement_date: date
    statement_balance: Decimal
    ids: list[int] = []


def _cleared_balance(db: Session, acc: Account, as_of: date) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0))
                      .where(Transaction.account_id == acc.id,
                             Transaction.cleared.is_(True),
                             Transaction.txn_date <= as_of))
    return acc.opening_balance + Decimal(total or 0)


@router.get("/accounts/{account_id}/reconcile")
def reconcile_start(account_id: int, statement_date: date | None = None,
                    db: Session = Depends(get_db)):
    """The data for reconciling an account with a bank statement."""
    acc = get_or_404(db, Account, account_id)
    as_of = statement_date or date.today()
    last = db.scalars(select(Reconciliation).where(
        Reconciliation.account_id == acc.id).order_by(
        Reconciliation.statement_date.desc(),
        Reconciliation.id.desc())).first()
    open_txns = list(db.scalars(select(Transaction).where(
        Transaction.account_id == acc.id, Transaction.cleared.is_(False),
        Transaction.txn_date <= as_of).order_by(
        Transaction.txn_date, Transaction.id)))
    return {
        "account_id": acc.id, "account_name": acc.name,
        "currency": acc.currency, "statement_date": as_of,
        "cleared_balance": float(_cleared_balance(db, acc, as_of)),
        "balance": float(account_balances(db, as_of).get(acc.id, 0)),
        "last": ({"statement_date": last.statement_date,
                  "statement_balance": float(last.statement_balance)}
                 if last else None),
        "transactions": _to_out(db, open_txns),
    }


@router.post("/accounts/{account_id}/reconcile")
def reconcile_finish(account_id: int, body: ReconcileIn,
                     db: Session = Depends(get_db)):
    """Mark the ticked transactions cleared once the balances match."""
    acc = get_or_404(db, Account, account_id)
    picked = list(db.scalars(select(Transaction).where(
        Transaction.id.in_(body.ids))))
    if len(picked) != len(set(body.ids)) or any(
            t.account_id != acc.id or t.txn_date > body.statement_date
            or t.cleared for t in picked):
        raise HTTPException(
            422, "Some ticked transactions are not open transactions of "
            "this account up to the statement date. Reload the page and "
            "tick them again.")
    cleared = (_cleared_balance(db, acc, body.statement_date)
               + sum((t.amount for t in picked), Decimal(0)))
    diff = body.statement_balance - cleared
    if diff != 0:
        raise HTTPException(
            422, f"The ticked transactions add up to {cleared:.2f} "
            f"{acc.currency}, the statement says "
            f"{body.statement_balance:.2f}: a difference of {diff:.2f}. "
            "Look for a missing or wrong transaction before finishing.")
    for t in picked:
        t.cleared = True
    rec = Reconciliation(account_id=acc.id,
                         statement_date=body.statement_date,
                         statement_balance=body.statement_balance)
    db.add(rec)
    db.flush()
    done = 0
    for t in db.scalars(select(Transaction).where(
            Transaction.account_id == acc.id, Transaction.cleared.is_(True),
            Transaction.reconciliation_id.is_(None),
            Transaction.txn_date <= body.statement_date)):
        t.reconciliation_id = rec.id
        done += 1
    rec.transactions = done
    db.commit()
    return {"id": rec.id, "reconciled": done,
            "statement_date": body.statement_date}


@router.delete("/accounts/{account_id}/reconciliations/latest")
def undo_reconciliation(account_id: int, db: Session = Depends(get_db)):
    """Undo the newest reconciliation; its transactions stay cleared."""
    get_or_404(db, Account, account_id)
    rec = db.scalars(select(Reconciliation).where(
        Reconciliation.account_id == account_id).order_by(
        Reconciliation.statement_date.desc(),
        Reconciliation.id.desc())).first()
    if rec is None:
        raise HTTPException(404, "This account has no reconciliation.")
    for t in db.scalars(select(Transaction).where(
            Transaction.reconciliation_id == rec.id)):
        t.reconciliation_id = None
    db.delete(rec)
    db.commit()
    return {"undone": rec.statement_date}


@router.get("/accounts/{account_id}/reconciliations")
def reconciliations(account_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Account, account_id)
    return [{"id": r.id, "statement_date": r.statement_date,
             "statement_balance": float(r.statement_balance),
             "transactions": r.transactions}
            for r in db.scalars(select(Reconciliation).where(
                Reconciliation.account_id == account_id).order_by(
                Reconciliation.statement_date.desc(),
                Reconciliation.id.desc()))]


# --- debt payoff ---------------------------------------------------------
class DebtTermsIn(BaseModel):
    apr: Annotated[Decimal, Field(ge=0, le=100)]
    min_payment: Annotated[Decimal, Field(ge=0)]


class PlanIn(BaseModel):
    extra: Annotated[Decimal, Field(ge=0)] = Decimal(0)


def _debts(db: Session) -> tuple[list[dict], list[str], str]:
    base = base_currency(db)
    fx = FxConverter.from_db(db)
    balances = account_balances(db)
    terms = {t.account_id: t for t in db.scalars(select(DebtTerms))}
    out, warnings = [], []
    for acc in db.scalars(select(Account).where(
            Account.type.in_(DEBT_TYPES), Account.is_archived.is_(False))
            .order_by(Account.name)):
        owed = -balances.get(acc.id, Decimal(0))
        term = terms.get(acc.id)
        rate = fx.try_rate(acc.currency, base, date.today())
        if owed > 0 and rate is None:
            warnings.append(
                f"{acc.name}: no {acc.currency}->{base} exchange rate, "
                "so it is left out of the plan.")
        out.append({
            "account_id": acc.id, "name": acc.name, "type": acc.type,
            "currency": acc.currency, "owed": float(max(owed, 0)),
            "owed_base": (float(max(owed, 0)) * rate
                          if rate is not None else None),
            "apr": float(term.apr) if term else 0.0,
            "min_payment": float(term.min_payment) if term else 0.0,
            "min_payment_base": (float(term.min_payment) * rate
                                 if term and rate is not None else None),
            "has_terms": term is not None,
        })
    return out, warnings, base


@router.get("/debts")
def list_debts(db: Session = Depends(get_db)):
    debts, warnings, base = _debts(db)
    return {"currency": base, "debts": debts, "warnings": warnings}


@router.put("/debts/{account_id}")
def save_terms(account_id: int, body: DebtTermsIn,
               db: Session = Depends(get_db)):
    acc = get_or_404(db, Account, account_id)
    if acc.type not in DEBT_TYPES:
        raise HTTPException(
            422, "Interest and minimum payment can only be set for loan "
            "and credit-card accounts. Change the account type first.")
    term = db.get(DebtTerms, acc.id) or DebtTerms(account_id=acc.id)
    term.apr, term.min_payment = body.apr, body.min_payment
    db.add(term)
    db.commit()
    return {"account_id": acc.id, "apr": float(term.apr),
            "min_payment": float(term.min_payment)}


@router.post("/debts/plan")
def debt_plan(body: PlanIn, db: Session = Depends(get_db)):
    """Compare avalanche, snowball and minimum payments only."""
    debts, warnings, base = _debts(db)
    usable = [pt.Debt(d["account_id"], d["name"], d["owed_base"], d["apr"],
                      d["min_payment_base"] or 0.0)
              for d in debts if d["owed"] > 0 and d["owed_base"] is not None]
    plans = {name: pt.payoff_plan(usable, float(body.extra), name)
             for name in ("avalanche", "snowball", "minimum")}
    return {"currency": base, "extra": float(body.extra),
            "start": date.today(), "warnings": warnings,
            "plans": {k: v.to_dict(date.today()) for k, v in plans.items()}}


# --- spending calendar -----------------------------------------------------
@router.get("/analytics/calendar")
def spending_calendar(year: int | None = None,
                      db: Session = Depends(get_db)):
    """Daily spending of one year and a year-in-review summary."""
    year = year or date.today().year
    base = base_currency(db)
    fx = FxConverter.from_db(db)
    df = load_transactions(db, fx, base, date(year - 1, 1, 1),
                           date(year, 12, 31))
    first = db.scalar(select(func.min(Transaction.txn_date)))
    return {"year": year, "currency": base,
            "first_year": first.year if first else year,
            **pt.calendar(expenses(df), incomes(df), year),
            "missing_fx": sorted(df.attrs.get("missing_fx", []))}
