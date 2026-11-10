"""Helpers shared by the API routers."""
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Category, Transaction, TransactionSplit

T = TypeVar("T")


def get_or_404(db: Session, model: type[T], obj_id: int) -> T:
    """Return the row with ``obj_id`` or raise HTTP 404.

    Parameters
    ----------
    db : Session
        The open database session.
    model : type
        The ORM model class.
    obj_id : int
        The primary key.

    Returns
    -------
    object
        The ORM instance.
    """
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(
            404, f"{model.__name__} {obj_id} does not exist. It may have "
            "been deleted; refresh the page.")
    return obj


def commit_or_409(db: Session, what: str) -> None:
    """Commit, turning constraint violations into HTTP 409 errors."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        detail = str(exc.orig).splitlines()[0] if exc.orig else str(exc)
        raise HTTPException(
            409, f"Could not save {what}: {detail}. A record with the same "
            "unique values probably exists already; change the name or "
            "date and retry.") from exc


def category_names(db: Session) -> dict[int, str]:
    """Return ``"Parent › Child"`` display names keyed by category id."""
    cats = {c.id: c for c in db.scalars(select(Category))}
    out = {}
    for cid, c in cats.items():
        parent = cats.get(c.parent_id) if c.parent_id else None
        out[cid] = f"{parent.name} › {c.name}" if parent else c.name
    return out


def category_with_children(db: Session, category_id: int) -> list[int]:
    """Return ``category_id`` plus the ids of its direct children."""
    children = db.scalars(select(Category.id).where(
        Category.parent_id == category_id))
    return [category_id, *children]


def not_split():
    """Return a filter that keeps transactions without split parts."""
    return ~exists().where(TransactionSplit.transaction_id == Transaction.id)
