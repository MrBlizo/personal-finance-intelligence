"""Health check and demo-data management."""
from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import get_db, get_engine
from ..migrations import run_migrations
from ..services import backup as bk
from ..services.demo import remove_demo, seed_demo

router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@router.get("/info")
def info():
    s = get_settings()
    return {"version": __version__, "data_dir": str(s.data_dir.resolve()),
            "database": "bundled PostgreSQL" if s.pg_bin
            else "external PostgreSQL"}


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
def _pg(request: Request):
    pg = getattr(request.app.state, "pg", None)
    if pg is None:
        raise HTTPException(
            409, "Backups need the bundled database (PFI.exe or PFI_PG_BIN). "
            "With an external PostgreSQL server use pg_dump directly.")
    return pg


def _info(b: bk.BackupInfo) -> dict:
    return {"name": b.name, "kind": b.kind, "size": b.size,
            "created": b.created.isoformat(timespec="seconds")}


@router.get("/backups")
def list_backups(request: Request):
    data_dir = get_settings().data_dir
    return {"folder": str(bk.backup_dir(data_dir).resolve()),
            "available": getattr(request.app.state, "pg", None) is not None,
            "backups": [_info(b) for b in bk.list_backups(data_dir)]}


@router.post("/backups")
def create_backup(request: Request):
    try:
        return _info(bk.create_backup(_pg(request), get_settings().data_dir))
    except bk.BackupError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/backups/{name}/download")
def download_backup(name: str):
    try:
        path = bk.resolve(get_settings().data_dir, name)
    except bk.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=name,
                        media_type="application/octet-stream")


def _restore(request: Request, path) -> dict:
    pg = _pg(request)
    try:
        safety = bk.restore_backup(pg, get_settings().data_dir, path,
                                   get_engine())
    except bk.BackupError as exc:
        raise HTTPException(500, str(exc)) from exc
    run_migrations(get_engine())
    return {"restored": path.name, "safety_backup": safety.name}


@router.post("/backups/{name}/restore")
def restore_backup(name: str, request: Request):
    try:
        path = bk.resolve(get_settings().data_dir, name)
    except bk.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _restore(request, path)


@router.post("/backups/upload")
async def upload_backup(request: Request, file: UploadFile = File(...)):
    """Store an uploaded .dump file in the backup folder (not restored)."""
    raw = await file.read()
    if not raw.startswith(b"PGDMP"):
        raise HTTPException(
            422, "This file is not a PFI/PostgreSQL backup (.dump). Choose "
            "a file created with 'Back up now'.")
    path = bk.new_path(get_settings().data_dir, "uploaded")
    path.write_bytes(raw)
    return {"name": path.name, "kind": "uploaded", "size": len(raw)}
