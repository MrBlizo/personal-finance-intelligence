"""Envelope budgets, period budgets, IOUs, loan schedules and review."""
from datetime import date
from decimal import Decimal

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Response, UploadFile)
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import schemas as s
from ..db import get_db
from ..models import (
    Account, BudgetTarget, Category, DebtTerms, Iou, IouPayment,
    PeriodBudget, PeriodBudgetCategory, Tag, Transaction)
from ..services import budgeting as bg
from ..services import envelope as env
from ..services import app_import, ynab
from ..services.fx import FxConverter
from ..services.ledger import account_balances, base_currency
from ..services.planning import add_months
from .common import commit_or_409, get_or_404

router = APIRouter(prefix="/api")
MAX_YNAB = 50 * 1024 * 1024


def _month(value: str | None) -> date:
    if not value:
        return date.today().replace(day=1)
    try:
        return date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise HTTPException(
            422, f"'{value}' is not a month. Use the form YYYY-MM, for "
            "example 2026-11.") from exc


def _expense_category(db: Session, category_id: int) -> Category:
    cat = get_or_404(db, Category, category_id)
    if cat.kind != "expense":
        raise HTTPException(
            422, f"'{cat.name}' is an income category. Money can only be "
            "assigned to expense categories; pick another category.")
    return cat


# --- envelope budgeting ----------------------------------------------------
@router.get("/envelopes")
def get_envelopes(month: str | None = None, db: Session = Depends(get_db)):
    """The envelope budget of a month (default: this month)."""
    return env.month_view(db, FxConverter.from_db(db), base_currency(db),
                          _month(month))


@router.put("/envelopes/{month}/{category_id}")
def assign(month: str, category_id: int, body: s.AssignIn,
           db: Session = Depends(get_db)):
    _expense_category(db, category_id)
    env.set_assigned(db, category_id, _month(month), body.amount)
    commit_or_409(db, "assigned amount")
    return env.month_view(db, FxConverter.from_db(db), base_currency(db),
                          _month(month))


@router.post("/envelopes/move")
def move_money(body: s.MoveIn, db: Session = Depends(get_db)):
    """Move money between categories, or to/from Ready to Assign."""
    if body.from_category_id is None and body.to_category_id is None:
        raise HTTPException(
            422, "Choose a category to move the money from or to; moving "
            "from Ready to Assign to Ready to Assign changes nothing.")
    if body.from_category_id == body.to_category_id:
        raise HTTPException(
            422, "The two categories are the same. Pick a different "
            "category to receive the money.")
    for cid in (body.from_category_id, body.to_category_id):
        if cid is not None:
            _expense_category(db, cid)
    env.move(db, _month(body.month), body.amount, body.from_category_id,
             body.to_category_id)
    commit_or_409(db, "moved money")
    return env.month_view(db, FxConverter.from_db(db), base_currency(db),
                          _month(body.month))


@router.post("/envelopes/quick-assign")
def quick_assign(body: s.QuickAssignIn, db: Session = Depends(get_db)):
    """Preview (``apply`` false) or apply a quick assignment."""
    fx, base, month = FxConverter.from_db(db), base_currency(db), \
        _month(body.month)
    changes = env.quick_assign(db, fx, base, month, body.mode)
    if body.apply:
        for c in changes:
            env.set_assigned(db, c["category_id"], month, c["new"])
        commit_or_409(db, "quick assignment")
    return {"changes": changes, "applied": body.apply,
            "total": sum((c["new"] - c["old"] for c in changes),
                         Decimal(0))}


@router.put("/budget-targets/{category_id}")
def save_target(category_id: int, body: s.TargetIn,
                db: Session = Depends(get_db)):
    _expense_category(db, category_id)
    target = db.get(BudgetTarget, category_id) \
        or BudgetTarget(category_id=category_id)
    target.kind, target.amount = body.kind, body.amount
    target.due_date = body.due_date
    db.add(target)
    commit_or_409(db, "target")
    return {"category_id": category_id, "kind": target.kind,
            "amount": target.amount, "due_date": target.due_date}


@router.delete("/budget-targets/{category_id}", status_code=204)
def delete_target(category_id: int, db: Session = Depends(get_db)):
    target = db.get(BudgetTarget, category_id)
    if target is not None:
        db.delete(target)
        db.commit()
    return Response(status_code=204)


# --- period budgets --------------------------------------------------------
@router.get("/period-budgets")
def list_period_budgets(db: Session = Depends(get_db)):
    return bg.period_budgets(db, FxConverter.from_db(db), base_currency(db))


def _save_period(db: Session, pb: PeriodBudget,
                 body: s.PeriodBudgetIn) -> None:
    if body.tag_id is not None:
        get_or_404(db, Tag, body.tag_id)
    for cid in body.category_ids:
        _expense_category(db, cid)
    for key in ("name", "amount", "period", "start_date", "tag_id",
                "notes"):
        setattr(pb, key, getattr(body, key))
    pb.end_date = body.end_date if body.period == "custom" else None
    db.add(pb)
    db.flush()
    current = {link.category_id: link for link in db.scalars(
        select(PeriodBudgetCategory).where(
            PeriodBudgetCategory.period_budget_id == pb.id))}
    for cid, link in current.items():
        if cid not in body.category_ids:
            db.delete(link)
    for cid in set(body.category_ids) - set(current):
        db.add(PeriodBudgetCategory(period_budget_id=pb.id, category_id=cid))
    commit_or_409(db, "budget")


@router.post("/period-budgets", status_code=201)
def create_period_budget(body: s.PeriodBudgetIn,
                         db: Session = Depends(get_db)):
    pb = PeriodBudget()
    _save_period(db, pb, body)
    return {"id": pb.id}


@router.put("/period-budgets/{budget_id}")
def update_period_budget(budget_id: int, body: s.PeriodBudgetIn,
                         db: Session = Depends(get_db)):
    _save_period(db, get_or_404(db, PeriodBudget, budget_id), body)
    return {"id": budget_id}


@router.delete("/period-budgets/{budget_id}", status_code=204)
def delete_period_budget(budget_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, PeriodBudget, budget_id))
    db.commit()
    return Response(status_code=204)


# --- IOUs -------------------------------------------------------------------
@router.get("/ious")
def list_ious(db: Session = Depends(get_db)):
    return bg.iou_summary(db, FxConverter.from_db(db), base_currency(db))


@router.post("/ious", status_code=201)
def create_iou(body: s.IouIn, db: Session = Depends(get_db)):
    iou = Iou(**body.model_dump())
    db.add(iou)
    commit_or_409(db, "IOU")
    return {"id": iou.id}


@router.put("/ious/{iou_id}")
def update_iou(iou_id: int, body: s.IouIn, db: Session = Depends(get_db)):
    iou = get_or_404(db, Iou, iou_id)
    for key, value in body.model_dump().items():
        setattr(iou, key, value)
    commit_or_409(db, "IOU")
    return {"id": iou.id}


@router.delete("/ious/{iou_id}", status_code=204)
def delete_iou(iou_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Iou, iou_id))
    db.commit()
    return Response(status_code=204)


def _refresh_settled(db: Session, iou: Iou) -> None:
    db.flush()
    pays = list(db.scalars(select(IouPayment).where(
        IouPayment.iou_id == iou.id)))
    repaid = sum((p.amount for p in pays), Decimal(0))
    iou.settled_on = (max(p.paid_on for p in pays)
                      if pays and repaid >= iou.amount else None)


@router.post("/ious/{iou_id}/payments", status_code=201)
def add_iou_payment(iou_id: int, body: s.IouPaymentIn,
                    db: Session = Depends(get_db)):
    iou = get_or_404(db, Iou, iou_id)
    db.add(IouPayment(iou_id=iou.id, **body.model_dump()))
    _refresh_settled(db, iou)
    commit_or_409(db, "repayment")
    return {"id": iou.id, "settled_on": iou.settled_on}


@router.post("/ious/{iou_id}/settle")
def settle_iou(iou_id: int, db: Session = Depends(get_db)):
    """Record a repayment of whatever is still open, dated today."""
    iou = get_or_404(db, Iou, iou_id)
    paid = sum((p.amount for p in db.scalars(select(IouPayment).where(
        IouPayment.iou_id == iou.id))), Decimal(0))
    if paid < iou.amount:
        db.add(IouPayment(iou_id=iou.id, paid_on=date.today(),
                          amount=iou.amount - paid, note="Settled"))
    _refresh_settled(db, iou)
    commit_or_409(db, "repayment")
    return {"id": iou.id, "settled_on": iou.settled_on}


@router.delete("/ious/{iou_id}/payments/{payment_id}", status_code=204)
def delete_iou_payment(iou_id: int, payment_id: int,
                       db: Session = Depends(get_db)):
    iou = get_or_404(db, Iou, iou_id)
    pay = get_or_404(db, IouPayment, payment_id)
    if pay.iou_id != iou.id:
        raise HTTPException(
            404, "This repayment belongs to another IOU. Refresh the page.")
    db.delete(pay)
    _refresh_settled(db, iou)
    db.commit()
    return Response(status_code=204)


# --- loan schedules ---------------------------------------------------------
@router.get("/debts/{account_id}/schedule")
def loan_schedule(account_id: int, payment: float | None = None,
                  finish_by: date | None = None,
                  db: Session = Depends(get_db)):
    """Amortization schedule and the payment needed to finish by a date.

    Amounts are in the account's own currency.
    """
    acc = get_or_404(db, Account, account_id)
    if acc.type not in ("loan", "credit_card"):
        raise HTTPException(
            422, "Schedules exist for loan and credit-card accounts only. "
            "Change the account type first.")
    owed = float(max(-account_balances(db).get(acc.id, Decimal(0)),
                     Decimal(0)))
    term = db.get(DebtTerms, acc.id)
    apr = float(term.apr) if term else 0.0
    pay = payment if payment is not None else (
        float(term.min_payment) if term else 0.0)
    start = add_months(date.today().replace(day=1), 1)
    out = {"account_id": acc.id, "name": acc.name, "currency": acc.currency,
           "owed": owed, "apr": apr, "payment": pay,
           "schedule": bg.amortization(owed, apr, pay, start)}
    if finish_by is not None:
        months = (finish_by.year - start.year) * 12 + finish_by.month \
            - start.month + 1
        out["finish_by"] = finish_by
        out["payment_to_finish"] = bg.payment_to_finish(owed, apr, months)
    return out


# --- YNAB import ------------------------------------------------------------
@router.post("/import/ynab")
async def import_ynab(file: UploadFile = File(...),
                      currency: str = Form(...),
                      dry_run: bool = Form(True),
                      db: Session = Depends(get_db)):
    """Import YNAB's Export Plan zip (or its Register/Plan file).

    With ``dry_run`` (the default) nothing is saved; the report shows what
    would be created.
    """
    data = await file.read(MAX_YNAB + 1)
    if len(data) > MAX_YNAB:
        raise HTTPException(
            413, "The file is larger than 50 MB. Upload YNAB's export zip "
            "as it was downloaded.")
    if not (len(currency) == 3 and currency.isalpha()):
        raise HTTPException(
            422, "Choose the currency of your YNAB accounts, for example "
            "CHF or EUR.")
    try:
        tables = ynab.read_files(data, file.filename or "")
        return ynab.import_export(db, tables, currency.upper(), dry_run)
    except ynab.YnabError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/app")
async def import_other_app(file: UploadFile = File(...),
                           currency: str = Form(...),
                           source: str = Form("auto"),
                           dry_run: bool = Form(True),
                           db: Session = Depends(get_db)):
    """Import a Cashew or Mint CSV export (``source`` auto-detects).

    With ``dry_run`` (the default) nothing is saved; the report shows what
    would be created.
    """
    data = await file.read(MAX_YNAB + 1)
    if len(data) > MAX_YNAB:
        raise HTTPException(413, "The file is larger than 50 MB. Export a "
                                 "shorter period from the other app.")
    if not (len(currency) == 3 and currency.isalpha()):
        raise HTTPException(
            422, "Choose the currency of the imported accounts, for "
            "example USD or EUR.")
    kind = app_import.detect(data) if source == "auto" else source
    if kind is None:
        raise HTTPException(
            422, "This file doesn't look like a Cashew or Mint export. "
            "Export it again from the other app, or use Import › bank "
            "statement for a bank's CSV file.")
    try:
        rows = app_import.normalise(data, kind)
        report = app_import.import_rows(db, rows, kind, currency.upper(),
                                        dry_run)
    except app_import.AppImportError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return {"source": kind, **report}


# --- payee memory -----------------------------------------------------------
@router.get("/payees")
def payees(q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    """Payees matching ``q`` with the category they had last time.

    The payee is the merchant, or the description when there is none.
    Most recently used payees come first.
    """
    payee = func.coalesce(func.nullif(Transaction.merchant, ""),
                          Transaction.description)
    stmt = (select(payee.label("payee"), func.count().label("n"),
                   func.max(Transaction.txn_date).label("last"))
            .where(Transaction.kind != "transfer", payee != "")
            .group_by(payee)
            .order_by(func.max(Transaction.txn_date).desc())
            .limit(max(1, min(limit, 50))))
    if q.strip():
        stmt = stmt.where(payee.ilike(f"%{q.strip()}%"))
    out = []
    for name, n, last in db.execute(stmt):
        recent = db.scalar(
            select(Transaction).where(
                payee == name, Transaction.category_id.is_not(None))
            .order_by(Transaction.txn_date.desc(), Transaction.id.desc())
            .limit(1))
        out.append({"payee": name, "count": n, "last_date": last,
                    "category_id": recent.category_id if recent else None,
                    "kind": recent.kind if recent else None,
                    "last_amount": recent.amount if recent else None})
    return out


# --- review queue -----------------------------------------------------------
@router.get("/review/count")
def review_count(db: Session = Depends(get_db)):
    return {"count": db.scalar(select(func.count()).select_from(
        Transaction).where(Transaction.reviewed.is_(False)))}


@router.post("/review/approve")
def approve(body: s.ReviewIn, db: Session = Depends(get_db)):
    """Mark transactions as reviewed (all waiting ones if no ids)."""
    stmt = update(Transaction).where(Transaction.reviewed.is_(False))
    if body.ids:
        stmt = stmt.where(Transaction.id.in_(body.ids))
    done = db.execute(stmt.values(reviewed=True)).rowcount
    db.commit()
    return {"approved": done}
