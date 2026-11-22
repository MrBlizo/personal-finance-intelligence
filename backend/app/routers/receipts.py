"""Receipt scanning: drop a photo, get the amount, date and shop."""
from fastapi import (
    APIRouter, Depends, File, HTTPException, UploadFile)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import receipts
from ..services.ledger import base_currency

router = APIRouter(prefix="/api/receipts")
MAX_IMAGE = 20 * 1024 * 1024


class TextIn(BaseModel):
    text: str = Field(max_length=50_000)


def _dayfirst(db: Session) -> bool:
    # Ambiguous dates like 03/04/2026 are month first only on US receipts;
    # Swiss, Moroccan and European ones print the day first.
    return base_currency(db) != "USD"


def _result(db: Session, text: str) -> dict:
    found = receipts.parse_receipt(text, dayfirst=_dayfirst(db))
    found["category_id"] = receipts.guess_category(db, found["merchant"])
    return found


@router.get("/status")
def status():
    """Whether this computer can read receipt photos."""
    return {"ocr": receipts.ocr_available()}


@router.post("/parse")
def parse(body: TextIn, db: Session = Depends(get_db)):
    """Read amount, date and shop from text recognised elsewhere (phone)."""
    return _result(db, body.text)


@router.post("/scan")
async def scan(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Recognise a receipt photo with Windows' offline OCR and read it."""
    data = await file.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "The photo is larger than 20 MB. Take it "
                                 "again at a lower resolution.")
    if not data:
        raise HTTPException(422, "The file is empty. Drop the photo again.")
    try:
        text = await run_in_threadpool(receipts.ocr_image, data)
    except receipts.OcrUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not text.strip():
        raise HTTPException(
            422, "No text was found on this photo. Take it flat, in good "
            "light and filling the frame, then try again.")
    return _result(db, text)
