"""Health check and demo-data management."""
from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import get_db, get_engine
from ..migrations import run_migrations
from ..models import Account
from ..services import backup as bk
from ..services.demo import remove_demo, seed_demo

router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@router.get("/info")
def info(db: Session = Depends(get_db)):
    s = get_settings()
    empty = db.scalar(select(func.count(Account.id))) == 0
    return {"version": __version__, "data_dir": str(s.data_dir.resolve()),
            "database": "SQLite", "database_file": str(s.sqlite_path),
            "empty": empty}


@router.post("/system/shutdown")
def shutdown(request: Request):
    """Ask the server to exit gracefully (used by PFI.exe on close)."""
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise HTTPException(
            409, "Shutdown is only available when started through run.py "
            "or PFI.exe.")
    server.should_exit = True
    return {"status": "stopping"}


@router.post("/demo")
def create_demo(db: Session = Depends(get_db)):
    try:
        return seed_demo(db)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/demo")
def delete_demo(db: Session = Depends(get_db)):
    return remove_demo(db)


# --- backups ---------------------------------------------------------------
class BackupSettingsIn(BaseModel):
    folder: str | None = None
    encrypt: bool = False
    password: str | None = None
    clear_password: bool = False


class BackupCreateIn(BaseModel):
    kind: str = "manual"


class RestoreIn(BaseModel):
    password: str | None = None


def _info(b: bk.BackupInfo) -> dict:
    return {"name": b.name, "kind": b.kind, "size": b.size,
            "created": b.created.isoformat(timespec="seconds"),
            "folder": b.folder, "encrypted": b.encrypted,
            "legacy": b.legacy, "warning": b.warning}


def _fail(exc: bk.BackupError) -> HTTPException:
    return HTTPException(423 if isinstance(exc, bk.PasswordError) else 422,
                         str(exc))


def _settings_out(data_dir) -> dict:
    cfg = bk.load_config(data_dir)
    target, warning = bk.target_dir(data_dir)
    return {"folder": str(target.resolve()),
            "default_folder": str(bk.default_dir(data_dir).resolve()),
            "chosen_folder": str(cfg.folder) if cfg.folder else None,
            "folder_warning": warning, "encrypt": cfg.encrypt,
            "has_password": cfg.has_password, "available": True}


@router.get("/backups")
def list_backups():
    data_dir = get_settings().data_dir
    return {**_settings_out(data_dir),
            "backups": [_info(b) for b in bk.list_backups(data_dir)]}


@router.put("/backups/settings")
def backup_settings(body: BackupSettingsIn):
    data_dir = get_settings().data_dir
    try:
        bk.save_config(data_dir, body.folder, body.encrypt, body.password,
                       body.clear_password)
    except bk.BackupError as exc:
        raise _fail(exc) from exc
    return _settings_out(data_dir)


@router.post("/backups")
def create_backup(body: BackupCreateIn | None = None):
    kind = body.kind if body else "manual"
    if kind not in ("manual", "move"):
        raise HTTPException(422, "Backup kind must be 'manual' or 'move'.")
    s = get_settings()
    try:
        return _info(bk.create_backup(s.data_dir, s.sqlite_path, kind))
    except bk.BackupError as exc:
        raise _fail(exc) from exc


@router.get("/backups/{name}/download")
def download_backup(name: str):
    try:
        path = bk.resolve(get_settings().data_dir, name)
    except bk.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=name,
                        media_type="application/octet-stream")


def _restore(path, password: str | None) -> dict:
    s = get_settings()
    try:
        safety = bk.restore_backup(s.data_dir, s.sqlite_path, path,
                                   get_engine(), password, s.pg_bin)
    except bk.BackupError as exc:
        raise _fail(exc) from exc
    run_migrations(get_engine())
    return {"restored": path.name, "safety_backup": safety.name}


@router.post("/backups/{name}/restore")
def restore_backup(name: str, body: RestoreIn | None = None):
    try:
        path = bk.resolve(get_settings().data_dir, name)
    except bk.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _restore(path, body.password if body else None)


@router.post("/backups/upload")
async def upload_backup(file: UploadFile = File(...)):
    """Store an uploaded backup in the default backup folder (not restored).

    Accepts ``.pfibak`` files (plain or encrypted) and ``.dump`` files from
    PFI 0.3.
    """
    raw = await file.read()
    if raw.startswith(b"PGDMP"):
        ext = "dump"
    elif raw.startswith(b"PK") or raw.startswith(bk.MAGIC):
        ext = "pfibak"
    else:
        raise HTTPException(
            422, "This file is not a PFI backup. Choose a .pfibak file made "
            "with 'Back up now' (or a .dump file from PFI 0.3).")
    path = bk.new_path(bk.default_dir(get_settings().data_dir), "uploaded",
                       ext)
    path.write_bytes(raw)
    return _info(bk._info(path))
