"""Recurring items, budgets and savings goals."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as s
from ..db import get_db
from ..models import Account, Budget, Category, RecurringItem, SavingsGoal
from ..services.fx import FxConverter
from ..services.ledger import base_currency
from ..services.planning import budget_status, goal_progress, \
    next_occurrence
from .common import commit_or_409, get_or_404

router = APIRouter(prefix="/api")


# --- recurring -------------------------------------------------------------
def _rec_out(item: RecurringItem) -> s.RecurringOut:
    out = s.RecurringOut.model_validate(item)
    out.next_date = next_occurrence(item, date.today()) \
        if item.is_active else None
    return out


def _check_recurring(db: Session, body: s.RecurringIn) -> None:
    get_or_404(db, Account, body.account_id)
    if body.category_id:
        get_or_404(db, Category, body.category_id)
    if body.end_date and body.end_date < body.start_date:
        raise HTTPException(422, "End date must be after the start date.")
    if body.amount == 0:
        raise HTTPException(
            422, "Amount must not be zero: use a positive amount for "
            "income and a negative amount for expenses.")


@router.get("/recurring", response_model=list[s.RecurringOut])
def list_recurring(db: Session = Depends(get_db)):
    items = db.scalars(select(RecurringItem).order_by(
        RecurringItem.is_active.desc(), RecurringItem.name))
    return [_rec_out(i) for i in items]


@router.post("/recurring", response_model=s.RecurringOut, status_code=201)
def create_recurring(body: s.RecurringIn, db: Session = Depends(get_db)):
    _check_recurring(db, body)
    item = RecurringItem(**body.model_dump())
    db.add(item)
    db.commit()
    return _rec_out(item)


@router.put("/recurring/{item_id}", response_model=s.RecurringOut)
def update_recurring(item_id: int, body: s.RecurringIn,
                     db: Session = Depends(get_db)):
    item = get_or_404(db, RecurringItem, item_id)
    _check_recurring(db, body)
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return _rec_out(item)


@router.delete("/recurring/{item_id}", status_code=204)
def delete_recurring(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, RecurringItem, item_id))
    db.commit()
    return Response(status_code=204)


# --- budgets ---------------------------------------------------------------
@router.get("/budgets", response_model=list[s.BudgetOut])
def list_budgets(db: Session = Depends(get_db)):
    return db.scalars(select(Budget)).all()


def _check_budget(db: Session, body: s.BudgetIn) -> None:
    cat = get_or_404(db, Category, body.category_id)
    if cat.kind != "expense":
        raise HTTPException(
            422, "Budgets can only be set on expense categories.")


@router.post("/budgets", response_model=s.BudgetOut, status_code=201)
def create_budget(body: s.BudgetIn, db: Session = Depends(get_db)):
    _check_budget(db, body)
    budget = Budget(**body.model_dump())
    db.add(budget)
    commit_or_409(db, "budget (one per category)")
    return budget


@router.put("/budgets/{budget_id}", response_model=s.BudgetOut)
def update_budget(budget_id: int, body: s.BudgetIn,
                  db: Session = Depends(get_db)):
    budget = get_or_404(db, Budget, budget_id)
    _check_budget(db, body)
    for key, value in body.model_dump().items():
        setattr(budget, key, value)
    commit_or_409(db, "budget")
    return budget


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Budget, budget_id))
    db.commit()
    return Response(status_code=204)


@router.get("/budgets/status")
def get_budget_status(month: str | None = None,
                      db: Session = Depends(get_db)):
    """Budget vs. actual for ``month`` (``YYYY-MM``; default current)."""
    try:
        day = (date.fromisoformat(f"{month}-01") if month
               else date.today())
    except ValueError as exc:
        raise HTTPException(
            422, f"Month '{month}' is not in YYYY-MM format.") from exc
    return budget_status(db, FxConverter.from_db(db), base_currency(db),
                         day)


# --- goals -----------------------------------------------------------------
@router.get("/goals")
def list_goals(db: Session = Depends(get_db)):
    fx = FxConverter.from_db(db)
    goals = db.scalars(select(SavingsGoal).order_by(
        SavingsGoal.priority.desc(), SavingsGoal.target_date))
    return [goal_progress(db, fx, g) for g in goals]


@router.post("/goals", status_code=201)
def create_goal(body: s.GoalIn, db: Session = Depends(get_db)):
    if body.account_id:
        get_or_404(db, Account, body.account_id)
    goal = SavingsGoal(**body.model_dump())
    db.add(goal)
    db.commit()
    return goal_progress(db, FxConverter.from_db(db), goal)


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, body: s.GoalIn,
                db: Session = Depends(get_db)):
    goal = get_or_404(db, SavingsGoal, goal_id)
    if body.account_id:
        get_or_404(db, Account, body.account_id)
    for key, value in body.model_dump().items():
        setattr(goal, key, value)
    db.commit()
    return goal_progress(db, FxConverter.from_db(db), goal)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, SavingsGoal, goal_id))
    db.commit()
    return Response(status_code=204)
