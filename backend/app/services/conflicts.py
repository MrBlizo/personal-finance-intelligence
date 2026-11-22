"""Show and settle edits made on two devices before they synced."""
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Account, Category, SyncConflict

#: Columns worth showing per table, in display order.
FIELDS = {
    "transactions": ("txn_date", "amount", "description", "merchant",
                     "category_id", "account_id", "notes"),
    "accounts": ("name", "type", "currency", "opening_balance", "notes"),
    "categories": ("name", "kind", "parent_id", "color"),
    "recurring_items": ("name", "amount", "frequency", "start_date",
                        "end_date", "is_active"),
    "goals": ("name", "target_amount", "target_date"),
}
MONEY = {"amount", "opening_balance", "target_amount"}


def _readable(db: Session, table: str, values: dict) -> dict:
    out = {}
    for col in FIELDS.get(table, tuple(values)):
        if col not in values:
            continue
        v = values[col]
        if col in MONEY and v is not None:
            v = int(v) / 100
        elif col in ("category_id", "parent_id") and v is not None:
            cat = db.get(Category, int(v))
            v = cat.name if cat else None
            col = "category" if col == "category_id" else "parent"
        elif col == "account_id" and v is not None:
            acc = db.get(Account, int(v))
            v = acc.name if acc else None
            col = "account"
        out[col] = v
    return out


def open_conflicts(db: Session) -> list[dict]:
    """Return the conflicts the user has not settled yet.

    Parameters
    ----------
    db : Session
        The open database session.

    Returns
    -------
    list of dict
        ``id``, ``table``, ``replaced`` ("here" when this device's edit was
        replaced), ``kept`` and ``other`` as readable fields, and
        ``created_at``. Conflicts whose row no longer exists are dropped.
    """
    out = []
    for c in db.scalars(select(SyncConflict).where(
            SyncConflict.resolved.is_(False)).order_by(SyncConflict.id)):
        exists = db.execute(text(
            f"SELECT 1 FROM {c.table_name} WHERE uid = :u"),
            {"u": c.uid}).first()
        if not exists:
            c.resolved = True
            continue
        out.append({
            "id": c.id, "table": c.table_name, "replaced": c.replaced,
            "kept": _readable(db, c.table_name, json.loads(c.kept)),
            "other": _readable(db, c.table_name, json.loads(c.other)),
            "created_at": c.created_at})
    db.commit()
    return out


def resolve(db: Session, conflict_id: int, use: str) -> None:
    """Settle a conflict.

    Parameters
    ----------
    db : Session
        The open database session.
    conflict_id : int
        The conflict to settle.
    use : str
        ``"kept"`` to keep what sync chose, ``"other"`` to switch to the
        other device's edit (saved as a new edit, so it syncs everywhere).

    Raises
    ------
    LookupError
        If the conflict does not exist or was already settled.
    """
    c = db.get(SyncConflict, conflict_id)
    if c is None or c.resolved:
        raise LookupError(
            f"Conflict {conflict_id} was already settled or no longer "
            "exists. Reload the list.")
    if use == "other":
        values = json.loads(c.other)
        sets = ", ".join(f"{k} = :{k}" for k in values)
        db.execute(text(
            f"UPDATE {c.table_name} SET {sets} WHERE uid = :_uid"),
            {**values, "_uid": c.uid})
    c.resolved = True
    db.commit()
