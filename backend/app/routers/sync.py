"""Sync with the phone app through a folder in the user's cloud drive."""
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import conflicts, gdrive, sync

router = APIRouter(prefix="/api/sync")
# The Google sign-in returns to this page in the browser, which has no PFI
# launch token; the random ``state`` of the sign-in protects it instead.
oauth_router = APIRouter()
CALLBACK = "/oauth/google"


class SetupIn(BaseModel):
    folder: Annotated[str, Field(min_length=3, max_length=500)]
    passphrase: Annotated[str, Field(min_length=8, max_length=200)]
    device_name: Annotated[str | None, Field(max_length=60)] = None


def _out(db: Session) -> dict:
    st = sync.status(db, get_settings().data_dir)
    data_dir = get_settings().data_dir
    return {**asdict(st), "suggestions": sync.suggest_folders(),
            "phone_ready": sync.phone_can_find(st.folder),
            "folder_label": (gdrive.LABEL if st.folder == gdrive.FOLDER
                             else st.folder),
            "google_available": gdrive.available(),
            "google_signed_in": gdrive.signed_in(data_dir)}


class ResolveIn(BaseModel):
    use: Literal["kept", "other"]


@router.get("/conflicts")
def list_conflicts(db: Session = Depends(get_db)):
    """Edits made on two devices before they synced."""
    return {"conflicts": conflicts.open_conflicts(db)}


@router.post("/conflicts/{conflict_id}")
def resolve_conflict(conflict_id: int, body: ResolveIn,
                     db: Session = Depends(get_db)):
    """Keep the synced version or switch to the other device's edit."""
    try:
        conflicts.resolve(db, conflict_id, body.use)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    return {"conflicts": conflicts.open_conflicts(db)}


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


@router.post("/google/start")
def google_start(request: Request):
    base = str(request.base_url).rstrip("/").replace("localhost", "127.0.0.1")
    try:
        return {"url": gdrive.start(base + CALLBACK)}
    except gdrive.DriveError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/google/signout")
def google_signout(db: Session = Depends(get_db)):
    gdrive.sign_out(get_settings().data_dir)
    return _out(db)


_PAGE = """<!doctype html><meta charset="utf-8"><title>Personal Finance</title>
<body style="font:16px system-ui;margin:15vh auto;max-width:520px;
text-align:center"><h1 style="font-size:24px">{title}</h1><p>{text}</p>"""


@oauth_router.get(CALLBACK, response_class=HTMLResponse)
def google_callback(state: str = "", code: str = "", error: str = ""):
    if error or not code:
        return _PAGE.format(
            title="Sign-in cancelled",
            text="Google Drive was not connected. You can close this tab "
                 "and try again in Personal Finance.")
    try:
        gdrive.finish(get_settings().data_dir, state, code)
    except gdrive.DriveError as exc:
        return HTMLResponse(_PAGE.format(title="Sign-in failed",
                                         text=str(exc)), status_code=400)
    return _PAGE.format(
        title="Google Drive is connected",
        text="You can close this tab and go back to Personal Finance.")
