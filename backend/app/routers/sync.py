"""Sync with the phone app through a folder in the user's cloud drive."""
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import sync

router = APIRouter(prefix="/api/sync")


class SetupIn(BaseModel):
    folder: Annotated[str, Field(min_length=3, max_length=500)]
    passphrase: Annotated[str, Field(min_length=8, max_length=200)]
    device_name: Annotated[str | None, Field(max_length=60)] = None


def _out(db: Session) -> dict:
    st = sync.status(db, get_settings().data_dir)
    return {**asdict(st), "suggestions": sync.suggest_folders()}


@router.get("")
def get_sync(db: Session = Depends(get_db)):
    return _out(db)


@router.post("/setup")
def setup_sync(body: SetupIn, db: Session = Depends(get_db)):
    try:
        sync.setup(db, get_settings().data_dir, body.folder,
                   body.passphrase, body.device_name)
        sync.run(db, get_settings().data_dir)
    except sync.SyncError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(db)


@router.post("/run")
def run_sync(db: Session = Depends(get_db)):
    try:
        result = sync.run(db, get_settings().data_dir)
    except sync.SyncError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**_out(db), "result": asdict(result)}


@router.post("/disable")
def disable_sync(db: Session = Depends(get_db)):
    sync.disable(db, get_settings().data_dir)
    return _out(db)
