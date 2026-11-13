"""Transactions, transfers and CSV import."""
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Response,
    UploadFile)
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import schemas as s
from ..config import get_settings
from ..db import get_db
from ..models import (
    Account, Attachment, Category, ImportBatch, ImportPreset, Tag,
    Transaction, TransactionSplit, TransactionTag)
from ..services import importer
from ..services.learn_apply import auto_categorize_batch
from ..services.fx import FxConverter
from ..services.ledger import base_currency
from .extras import sweep_orphans
from .common import (
    category_names, category_with_children, commit_or_409, get_or_404,
    not_split)

router = APIRouter(prefix="/api")
_LOCKED = ("This transaction is part of a reconciled bank statement, so its "
           "amount and date are locked. To change it, undo the latest "
           "reconciliation of the account first (Accounts > Reconcile).")
MAX_UPLOAD = 20 * 1024 * 1024


def _to_out(db: Session, txns: list[Transaction]) -> list[s.TransactionOut]:
    fx, base = FxConverter.from_db(db), base_currency(db)
    names = category_names(db)
    ids = [t.id for t in txns]
    splits: dict[int, list[dict]] = {}
    tags: dict[int, list[str]] = {}
    files: dict[int, int] = {}
    if ids:
        for sp in db.scalars(select(TransactionSplit).where(
                TransactionSplit.transaction_id.in_(ids)).order_by(
                TransactionSplit.id)):
            splits.setdefault(sp.transaction_id, []).append({
                "category_id": sp.category_id, "amount": float(sp.amount),
                "category_name": names.get(sp.category_id),
                "note": sp.note})
        for txn_id, name in db.execute(
                select(TransactionTag.transaction_id, Tag.name).join(Tag)
                .where(TransactionTag.transaction_id.in_(ids))
                .order_by(Tag.name)):
            tags.setdefault(txn_id, []).append(name)
        files = dict(db.execute(
            select(Attachment.transaction_id, func.count())
            .where(Attachment.transaction_id.in_(ids))
            .group_by(Attachment.transaction_id)).all())
    out = []
    for t in txns:
        item = s.TransactionOut.model_validate(t)
        item.account_name = t.account.name
        item.currency = t.account.currency
        rate = fx.try_rate(t.account.currency, base, t.txn_date)
        item.amount_base = (float(t.amount) * rate
                            if rate is not None else None)
        item.category_name = names.get(t.category_id)
        item.splits = splits.get(t.id, [])
        item.tags = tags.get(t.id, [])
        item.attachments = files.get(t.id, 0)
        out.append(item)
    return out


def _resolve_kind(db: Session, category_id: int | None,
                  kind: str | None, amount: Decimal) -> str:
    if category_id is not None:
        return get_or_404(db, Category, category_id).kind
    return kind or ("income" if amount > 0 else "expense")


@router.get("/transactions", response_model=s.TransactionPage)
def list_transactions(
        start: date | None = None, end: date | None = None,
        account_id: int | None = None, category_id: int | None = None,
        kind: str | None = None, q: str | None = None,
        uncategorized: bool = False, tag: str | None = None,
        limit: int = Query(100, ge=1, le=5000), offset: int = 0,
        db: Session = Depends(get_db)):
    stmt = select(Transaction)
    if start:
        stmt = stmt.where(Transaction.txn_date >= start)
    if end:
        stmt = stmt.where(Transaction.txn_date <= end)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id:
        wanted = category_with_children(db, category_id)
        stmt = stmt.where(or_(
            Transaction.category_id.in_(wanted),
            Transaction.id.in_(select(TransactionSplit.transaction_id).where(
                TransactionSplit.category_id.in_(wanted)))))
    if tag:
        stmt = stmt.where(Transaction.id.in_(
            select(TransactionTag.transaction_id).join(Tag).where(
                func.lower(Tag.name) == tag.strip().lower())))
    if kind:
        stmt = stmt.where(Transaction.kind == kind)
    if uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None),
                          Transaction.kind != "transfer", not_split())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Transaction.description.ilike(like),
                              Transaction.merchant.ilike(like),
                              Transaction.notes.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(
        Transaction.txn_date.desc(), Transaction.id.desc())
        .limit(limit).offset(offset)).all()
    return {"total": total, "items": _to_out(db, list(rows))}


@router.post("/transactions", response_model=s.TransactionOut,
             status_code=201)
def create_transaction(body: s.TransactionIn,
                       db: Session = Depends(get_db)):
    get_or_404(db, Account, body.account_id)
    data = body.model_dump()
    data["kind"] = _resolve_kind(db, body.category_id, body.kind,
                                 body.amount)
    txn = Transaction(**data)
    if txn.category_id is not None:
        txn.category_source = "user"
    db.add(txn)
    commit_or_409(db, "transaction")
    db.refresh(txn)
    return _to_out(db, [txn])[0]


@router.patch("/transactions/{txn_id}", response_model=s.TransactionOut)
def update_transaction(txn_id: int, body: s.TransactionPatch,
                       db: Session = Depends(get_db)):
    txn = get_or_404(db, Transaction, txn_id)
    if txn.trade_id is not None:
        raise HTTPException(
            409, "This transaction was created by an investment trade. "
            "Edit or delete the trade on the Investments page instead.")
    patch = body.model_dump(exclude_unset=True)
    clear = patch.pop("clear_category", False)
    wanted_kind = patch.pop("kind", None)
    if txn.kind == "transfer" and ({"amount", "category_id"} & set(patch)):
        raise HTTPException(
            409, "Amounts and categories of transfers cannot be edited "
            "leg by leg. Delete the transfer and create it again.")
    if "amount" in patch and patch["amount"] == 0:
        raise HTTPException(422, "Amount must not be zero.")
    if txn.reconciled and (
            ("amount" in patch and patch["amount"] != txn.amount)
            or ("txn_date" in patch and patch["txn_date"] != txn.txn_date)
            or patch.get("cleared") is False):
        raise HTTPException(409, _LOCKED)
    is_split = db.scalar(select(func.count()).where(
        TransactionSplit.transaction_id == txn.id))
    if is_split and (("amount" in patch and patch["amount"] != txn.amount)
                     or "category_id" in patch or clear):
        raise HTTPException(
            409, "This transaction is split across categories. Change the "
            "amounts or categories in the split, or remove the split "
            "first.")
    for key, value in patch.items():
        setattr(txn, key, value)
    if clear:
        txn.category_id = None
    if clear or "category_id" in patch:
        txn.category_source = "user" if txn.category_id else None
    if txn.kind != "transfer":
        txn.kind = _resolve_kind(db, txn.category_id, wanted_kind,
                                 txn.amount)
    if txn.transfer_group and "txn_date" in patch:
        for leg in db.scalars(select(Transaction).where(
                Transaction.transfer_group == txn.transfer_group)):
            leg.txn_date = txn.txn_date
    commit_or_409(db, "transaction")
    return _to_out(db, [txn])[0]


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    txn = get_or_404(db, Transaction, txn_id)
    if txn.reconciled:
        raise HTTPException(409, _LOCKED)
    if txn.trade_id is not None:
        raise HTTPException(
            409, "This transaction belongs to an investment trade; delete "
            "the trade on the Investments page instead.")
    if txn.transfer_group:
        for leg in db.scalars(select(Transaction).where(
                Transaction.transfer_group == txn.transfer_group)):
            db.delete(leg)
    else:
        db.delete(txn)
    db.commit()
    sweep_orphans(db, get_settings().subdir("attachments"))
    return Response(status_code=204)


@router.post("/transactions/bulk-categorize")
def bulk_categorize(body: s.BulkCategorize, db: Session = Depends(get_db)):
    kind = (get_or_404(db, Category, body.category_id).kind
            if body.category_id else None)
    changed = 0
    for txn in db.scalars(select(Transaction).where(
            Transaction.id.in_(body.ids), Transaction.kind != "transfer",
            Transaction.trade_id.is_(None), not_split())):
        txn.category_id = body.category_id
        txn.category_source = "user" if body.category_id else None
        txn.kind = kind or ("income" if txn.amount > 0 else "expense")
        changed += 1
    db.commit()
    return {"updated": changed}


@router.post("/transfers", response_model=list[s.TransactionOut],
             status_code=201)
def create_transfer(body: s.TransferIn, db: Session = Depends(get_db)):
    src = get_or_404(db, Account, body.from_account_id)
    dst = get_or_404(db, Account, body.to_account_id)
    if src.id == dst.id:
        raise HTTPException(422, "Choose two different accounts.")
    to_amount = body.to_amount
    if to_amount is None:
        if src.currency != dst.currency:
            fx = FxConverter.from_db(db)
            rate = fx.try_rate(src.currency, dst.currency, body.txn_date)
            if rate is None:
                raise HTTPException(
                    422, f"No {src.currency}->{dst.currency} rate is "
                    "stored. Enter the received amount, or add an "
                    "exchange rate in Settings.")
            to_amount = (body.amount * Decimal(str(rate))).quantize(
                Decimal("0.01"))
        else:
            to_amount = body.amount
    group = uuid.uuid4()
    legs = [
        Transaction(account_id=src.id, txn_date=body.txn_date,
                    amount=-body.amount, kind="transfer",
                    description=body.description, transfer_group=group),
        Transaction(account_id=dst.id, txn_date=body.txn_date,
                    amount=to_amount, kind="transfer",
                    description=body.description, transfer_group=group),
    ]
    db.add_all(legs)
    db.commit()
    for leg in legs:
        db.refresh(leg)
    return _to_out(db, legs)


# --- CSV import ------------------------------------------------------------
async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(
            413, "The file is larger than 20 MB. Split the statement into "
            "smaller date ranges and import them one by one.")
    return raw


def header_signature(columns: list[str]) -> str:
    """Return a stable hash of a CSV header row (used to match presets)."""
    norm = "\x1f".join(c.strip().lower() for c in columns)
    return hashlib.sha256(norm.encode()).hexdigest()


@router.get("/import/presets")
def list_presets(db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name,
             "mapping": json.loads(p.mapping_json)}
            for p in db.scalars(select(ImportPreset).order_by(
                ImportPreset.name))]


@router.delete("/import/presets/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ImportPreset, preset_id))
    db.commit()
    return Response(status_code=204)


@router.post("/import/preview", response_model=s.ImportPreview)
async def import_preview(file: UploadFile = File(...), skip_rows: int = 0,
                         db: Session = Depends(get_db)):
    raw = await _read_upload(file)
    try:
        df, delimiter, encoding, fmt = importer.read_statement(raw, skip_rows)
    except importer.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    sha = hashlib.sha256(raw).hexdigest()
    seen = db.scalar(select(func.count()).where(ImportBatch.sha256 == sha))
    rows = df.head(20).to_dict(orient="records")
    preset = db.scalar(select(ImportPreset).where(
        ImportPreset.header_signature == header_signature(list(df.columns)))
        .order_by(ImportPreset.created_at.desc(), ImportPreset.id.desc())
        .limit(1))
    return {"filename": file.filename or "upload.csv", "sha256": sha,
            "already_imported": bool(seen), "delimiter": delimiter,
            "encoding": encoding, "columns": list(df.columns),
            "rows": rows, "format": fmt,
            "guess": (importer.guess_mapping(df) if fmt == "csv"
                      else importer.structured_mapping()),
            "preset": ({"id": preset.id, "name": preset.name,
                        "mapping": json.loads(preset.mapping_json)}
                       if preset else None)}


def _mapping(mapping: str) -> s.ImportMapping:
    try:
        return s.ImportMapping.model_validate(json.loads(mapping))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            422, f"The column mapping is invalid: {exc}. Re-run the "
            "preview and choose the columns again.") from exc


@router.post("/import/check")
async def import_check(file: UploadFile = File(...),
                       mapping: str = Form(...),
                       db: Session = Depends(get_db)):
    """Count new and duplicate rows and list possible duplicates."""
    m = _mapping(mapping)
    get_or_404(db, Account, m.account_id)
    raw = await _read_upload(file)
    try:
        return importer.check_import(db, raw, m)
    except importer.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/commit", response_model=s.ImportResult)
async def import_commit(file: UploadFile = File(...),
                        mapping: str = Form(...),
                        save_preset: str | None = Form(None),
                        skip_lines: str | None = Form(None),
                        db: Session = Depends(get_db)):
    m = _mapping(mapping)
    get_or_404(db, Account, m.account_id)
    try:
        skip = {int(x) for x in json.loads(skip_lines or "[]")}
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            422, "skip_lines must be a JSON list of line numbers from the "
            "duplicate review.") from exc
    raw = await _read_upload(file)
    try:
        result = importer.commit_import(
            db, raw, file.filename or "upload.csv", m,
            get_settings().subdir("imports"), skip)
    except importer.ImportError_ as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    result["learned"] = auto_categorize_batch(db, result["batch_id"])
    if save_preset and save_preset.strip():
        df = importer.read_statement(raw, m.skip_rows)[0]
        name = save_preset.strip()[:120]
        preset = db.scalar(select(ImportPreset).where(
            ImportPreset.name == name))
        if preset is None:
            preset = ImportPreset(name=name)
            db.add(preset)
        preset.header_signature = header_signature(list(df.columns))
        preset.mapping_json = m.model_dump_json()
        db.commit()
        result["preset"] = name
    return result


@router.get("/import/batches", response_model=list[s.ImportBatchOut])
def list_batches(db: Session = Depends(get_db)):
    return db.scalars(select(ImportBatch).order_by(
        ImportBatch.imported_at.desc(), ImportBatch.id.desc())).all()


@router.delete("/import/batches/{batch_id}")
def undo_batch(batch_id: int, db: Session = Depends(get_db)):
    """Delete the transactions created by an import (the archived original
    file is kept)."""
    batch = get_or_404(db, ImportBatch, batch_id)
    removed = 0
    for txn in db.scalars(select(Transaction).where(
            Transaction.import_batch_id == batch.id)):
        db.delete(txn)
        removed += 1
    db.delete(batch)
    db.commit()
    sweep_orphans(db, get_settings().subdir("attachments"))
    return {"removed": removed}
