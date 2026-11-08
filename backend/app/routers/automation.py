"""Reminders, recurring auto-posting and learned categorisation."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Transaction
from ..services import automation, learner, learn_apply, prefs
from .common import category_names

router = APIRouter(prefix="/api")


@router.get("/reminders")
def reminders(days: int | None = Query(None, ge=1, le=60),
              db: Session = Depends(get_db)):
    """Recurring payments due soon (per item reminder window by default)."""
    return automation.upcoming(db, horizon=days)


@router.post("/reminders/notifications")
def notifications(db: Session = Depends(get_db)):
    """Reminders the desktop shell has not shown yet (marked as shown)."""
    fresh = automation.take_notifications(db)
    db.commit()
    return fresh


@router.post("/recurring/post-due")
def post_due(db: Session = Depends(get_db)):
    """Book due occurrences of auto-posting recurring items now."""
    ids = automation.post_due(db)
    db.commit()
    return {"posted": len(ids), "ids": ids}


@router.get("/learn/status")
def learn_status(db: Session = Depends(get_db)):
    """Size of the training history and chronological validation scores."""
    return learner.evaluate(db, prefs.get_float(
        db, "auto_categorize_threshold"))


@router.get("/learn/suggestions")
def learn_suggestions(limit: int = Query(200, ge=1, le=2000),
                      db: Session = Depends(get_db)):
    """Uncategorised transactions with the model's suggestion."""
    txns = learn_apply._uncategorised(db)
    txns.sort(key=lambda t: (t.txn_date, t.id), reverse=True)
    txns = txns[:limit]
    found = learner.suggest(db, txns)
    names = category_names(db)
    out = []
    for t in txns:
        sug = found.get(t.id)
        if not sug:
            continue
        out.append({"id": t.id, "txn_date": t.txn_date,
                    "description": t.description, "merchant": t.merchant,
                    "amount": float(t.amount),
                    "currency": t.account.currency,
                    "category_id": sug["category_id"],
                    "category_name": names.get(sug["category_id"]),
                    "confidence": sug["confidence"], "why": sug["why"]})
    return out


class ApplyIn(BaseModel):
    ids: list[int] | None = None
    min_confidence: float = Field(0.0, ge=0, le=1)


@router.post("/learn/apply")
def learn_apply_(body: ApplyIn, db: Session = Depends(get_db)):
    """Accept suggestions for the given ids (or all above a confidence)."""
    txns = learn_apply._uncategorised(db, ids=body.ids)
    n = learn_apply.apply(db, txns, body.min_confidence)
    db.commit()
    return {"updated": n}
