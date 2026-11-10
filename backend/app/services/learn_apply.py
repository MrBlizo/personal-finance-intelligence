"""Apply learned category suggestions to stored transactions."""
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..models import Category, Transaction, TransactionSplit
from . import learner, prefs


def _uncategorised(db: Session, batch_id: int | None = None,
                   ids: list[int] | None = None) -> list[Transaction]:
    stmt = select(Transaction).where(
        Transaction.category_id.is_(None), Transaction.kind != "transfer",
        Transaction.trade_id.is_(None),
        ~exists().where(TransactionSplit.transaction_id == Transaction.id))
    if batch_id is not None:
        stmt = stmt.where(Transaction.import_batch_id == batch_id)
    if ids is not None:
        stmt = stmt.where(Transaction.id.in_(ids))
    return list(db.scalars(stmt))


def apply(db: Session, txns: list[Transaction], min_confidence: float
          ) -> int:
    """Categorise ``txns`` whose suggestion reaches ``min_confidence``.

    Parameters
    ----------
    db : Session
        The open database session; the caller commits.
    txns : list of Transaction
        The candidate transactions.
    min_confidence : float
        The lowest posterior probability that is accepted.

    Returns
    -------
    int
        The number of transactions that received a category.
    """
    if not txns:
        return 0
    found = learner.suggest(db, txns)
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    changed = 0
    for t in txns:
        sug = found.get(t.id)
        if sug and sug["confidence"] >= min_confidence:
            t.category_id = sug["category_id"]
            t.kind = kinds[sug["category_id"]]
            t.category_source = "model"
            changed += 1
    return changed


def auto_categorize_batch(db: Session, batch_id: int) -> int:
    """Categorise a fresh import with the learned model, if enabled."""
    if not prefs.get_bool(db, "auto_categorize"):
        return 0
    n = apply(db, _uncategorised(db, batch_id=batch_id),
              prefs.get_float(db, "auto_categorize_threshold"))
    db.commit()
    return n
