"""Split transactions, tags and receipt attachments (0.4)."""
import mimetypes
import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response
from fastapi import UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (
    Attachment, Category, Tag, Transaction, TransactionSplit,
    TransactionTag)
from ..services.frame import load_transactions
from ..services.fx import FxConverter
from ..services.ledger import base_currency
from .common import commit_or_409, get_or_404

router = APIRouter(prefix="/api")
MAX_ATTACHMENT = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic",
                 "image/gif", "application/pdf"}


# --- splits ------------------------------------------------------------------
class SplitPart(BaseModel):
    category_id: int | None = None
    amount: Decimal
    note: str | None = Field(None, max_length=200)


class SplitIn(BaseModel):
    parts: list[SplitPart]


def _editable(txn: Transaction) -> None:
    if txn.kind == "transfer" or txn.trade_id is not None:
        raise HTTPException(
            409, "Transfers and investment trades cannot be split. Split "
            "an income or an expense instead.")


@router.put("/transactions/{txn_id}/splits")
def set_splits(txn_id: int, body: SplitIn, db: Session = Depends(get_db)):
    """Replace the split of a transaction; an empty list removes it."""
    txn = get_or_404(db, Transaction, txn_id)
    _editable(txn)
    db.execute(delete(TransactionSplit).where(
        TransactionSplit.transaction_id == txn.id))
    if body.parts:
        if len(body.parts) < 2:
            raise HTTPException(
                422, "A split needs at least two parts. To use one "
                "category, set it on the transaction instead.")
        total = sum((p.amount for p in body.parts), Decimal(0))
        if total != txn.amount:
            raise HTTPException(
                422, f"The parts add up to {total:.2f} but the transaction "
                f"is {txn.amount:.2f}. Adjust the amounts so they match.")
        for p in body.parts:
            if p.amount == 0:
                raise HTTPException(422, "A split part cannot be zero.")
            if p.category_id is not None:
                cat = get_or_404(db, Category, p.category_id)
                if cat.kind != txn.kind:
                    raise HTTPException(
                        422, f"'{cat.name}' is an {cat.kind} category but "
                        f"this transaction is an {txn.kind}. Pick "
                        f"{txn.kind} categories for every part.")
            db.add(TransactionSplit(transaction_id=txn.id,
                                    category_id=p.category_id,
                                    amount=p.amount, note=p.note))
        txn.category_id = None
        txn.category_source = "user"
    commit_or_409(db, "split")
    return get_splits(txn.id, db)


@router.get("/transactions/{txn_id}/splits")
def get_splits(txn_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Transaction, txn_id)
    return [{"id": sp.id, "category_id": sp.category_id,
             "amount": float(sp.amount), "note": sp.note}
            for sp in db.scalars(select(TransactionSplit).where(
                TransactionSplit.transaction_id == txn_id).order_by(
                TransactionSplit.id))]


# --- tags --------------------------------------------------------------------
class TagsIn(BaseModel):
    tags: list[str]


def _clean_tag(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if not name or len(name) > 60:
        raise HTTPException(
            422, f"Tag '{name[:20]}' must have 1 to 60 characters.")
    return name


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(
        TransactionTag.tag_id, func.count()).group_by(
        TransactionTag.tag_id)).all())
    return [{"id": t.id, "name": t.name, "count": counts.get(t.id, 0)}
            for t in db.scalars(select(Tag).order_by(Tag.name))]


@router.put("/transactions/{txn_id}/tags")
def set_tags(txn_id: int, body: TagsIn, db: Session = Depends(get_db)):
    """Replace the tags of a transaction; unknown names are created."""
    get_or_404(db, Transaction, txn_id)
    names = []
    for raw in body.tags:
        name = _clean_tag(raw)
        if name.lower() not in (n.lower() for n in names):
            names.append(name)
    existing = {t.name.lower(): t for t in db.scalars(select(Tag))}
    db.execute(delete(TransactionTag).where(
        TransactionTag.transaction_id == txn_id))
    for name in names:
        tag = existing.get(name.lower())
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
            existing[name.lower()] = tag
        db.add(TransactionTag(transaction_id=txn_id, tag_id=tag.id))
    commit_or_409(db, "tag")
    return sorted(t.name for t in existing.values()
                  if t.name.lower() in {n.lower() for n in names})


class TagRename(BaseModel):
    name: str


@router.patch("/tags/{tag_id}")
def rename_tag(tag_id: int, body: TagRename, db: Session = Depends(get_db)):
    tag = get_or_404(db, Tag, tag_id)
    tag.name = _clean_tag(body.name)
    commit_or_409(db, "tag")
    return {"id": tag.id, "name": tag.name}


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Tag, tag_id))
    db.commit()
    return Response(status_code=204)


@router.get("/analytics/tags")
def tag_report(start: date | None = None, end: date | None = None,
               db: Session = Depends(get_db)):
    """Money spent and received per tag in the base currency."""
    fx, base = FxConverter.from_db(db), base_currency(db)
    df = load_transactions(db, fx, base, start, end)
    df = df[df["amount_base"].notna() & df["tags"].map(bool)]
    out = {}
    for _, row in df.explode("tags").iterrows():
        item = out.setdefault(row["tags"], {
            "tag": row["tags"], "spent": 0.0, "received": 0.0,
            "transactions": set()})
        if row["kind"] == "expense":
            item["spent"] -= row["amount_base"]
        elif row["kind"] == "income":
            item["received"] += row["amount_base"]
        item["transactions"].add(row["id"])
    items = [{**v, "spent": round(v["spent"], 2),
              "received": round(v["received"], 2),
              "transactions": len(v["transactions"])}
             for v in out.values()]
    return {"base_currency": base,
            "items": sorted(items, key=lambda i: -i["spent"])}


# --- attachments -------------------------------------------------------------
def _folder() -> Path:
    return get_settings().subdir("attachments")


def _out(a: Attachment) -> dict:
    return {"id": a.id, "filename": a.filename, "size": a.size,
            "content_type": a.content_type,
            "created_at": a.created_at.isoformat() if a.created_at else None}


@router.get("/transactions/{txn_id}/attachments")
def list_attachments(txn_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Transaction, txn_id)
    return [_out(a) for a in db.scalars(select(Attachment).where(
        Attachment.transaction_id == txn_id).order_by(Attachment.id))]


@router.post("/transactions/{txn_id}/attachments", status_code=201)
async def add_attachment(txn_id: int, file: UploadFile = File(...),
                         db: Session = Depends(get_db)):
    get_or_404(db, Transaction, txn_id)
    name = Path(file.filename or "receipt").name[:255]
    ctype = (file.content_type or mimetypes.guess_type(name)[0]
             or "application/octet-stream")
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(
            415, "Attach a photo (JPEG, PNG, WebP, HEIC, GIF) or a PDF. "
            f"'{name}' has the type {ctype}.")
    raw = await file.read(MAX_ATTACHMENT + 1)
    if len(raw) > MAX_ATTACHMENT:
        raise HTTPException(
            413, "The file is larger than 20 MB. Save a smaller photo or "
            "a compressed PDF and attach it again.")
    ext = (Path(name).suffix.lower()[:10] or
           mimetypes.guess_extension(ctype) or "")
    stored = f"{uuid.uuid4().hex}{ext}"
    path = _folder() / stored
    path.write_bytes(raw)
    att = Attachment(transaction_id=txn_id, filename=name,
                     stored_name=stored, content_type=ctype, size=len(raw))
    db.add(att)
    try:
        commit_or_409(db, "attachment")
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    db.refresh(att)
    return _out(att)


@router.get("/attachments/{att_id}")
def open_attachment(att_id: int, db: Session = Depends(get_db)):
    att = get_or_404(db, Attachment, att_id)
    path = _folder() / att.stored_name
    if not path.is_file():
        raise HTTPException(
            404, f"The file of '{att.filename}' is missing from the "
            "attachments folder. Restore a backup or attach it again.")
    return FileResponse(path, filename=att.filename,
                        media_type=att.content_type)


@router.delete("/attachments/{att_id}", status_code=204)
def delete_attachment(att_id: int, db: Session = Depends(get_db)):
    att = get_or_404(db, Attachment, att_id)
    stored = att.stored_name
    db.delete(att)
    db.commit()
    (_folder() / stored).unlink(missing_ok=True)
    return Response(status_code=204)


def sweep_orphans(db: Session, folder: Path) -> int:
    """Delete attachment files no transaction refers to any more.

    Parameters
    ----------
    db : Session
        The open database session.
    folder : Path
        The attachments folder.

    Returns
    -------
    int
        The number of files removed.
    """
    if not folder.is_dir():
        return 0
    known = set(db.scalars(select(Attachment.stored_name)))
    removed = 0
    for f in folder.iterdir():
        if f.is_file() and f.name not in known:
            f.unlink(missing_ok=True)
            removed += 1
    return removed
