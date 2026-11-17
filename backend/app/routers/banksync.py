"""Bank sync: SimpleFIN (US/Canada) and Enable Banking (Europe)."""
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Account, BankLink
from ..services import banksync
from ..services.banksync import BankSyncError

router = APIRouter(prefix="/api/banksync")
# The bank's consent page returns to the website, which forwards the code
# to this page on 127.0.0.1; the random ``state`` protects it.
oauth_router = APIRouter()
CALLBACK = "/oauth/enablebanking"


class TokenIn(BaseModel):
    token: Annotated[str, Field(min_length=10, max_length=4000)]


class EbConfigIn(BaseModel):
    app_id: Annotated[str, Field(min_length=3, max_length=200)]
    private_key: Annotated[str, Field(min_length=100, max_length=20000)]


class EbConnectIn(BaseModel):
    bank: Annotated[str, Field(min_length=1, max_length=200)]
    country: Annotated[str, Field(min_length=2, max_length=2)]


class CodeIn(BaseModel):
    code: Annotated[str, Field(min_length=4, max_length=2000)]


class LinkIn(BaseModel):
    account_id: int | None = None
    start_date: date | None = None


def _dir():
    return get_settings().data_dir


def _fail(exc: BankSyncError):
    raise HTTPException(422, str(exc)) from exc


def _out(db: Session) -> dict:
    links = db.scalars(select(BankLink).order_by(
        BankLink.provider, BankLink.institution, BankLink.name))
    return {**banksync.configured(_dir()),
            "redirect_url": get_settings().bank_redirect_url,
            "links": [{
                "id": link.id, "provider": link.provider, "name": link.name,
                "institution": link.institution, "currency": link.currency,
                "balance": float(link.balance)
                if link.balance is not None else None,
                "account_id": link.account_id,
                "start_date": link.start_date,
                "last_synced_on": link.last_synced_on,
                "last_error": link.last_error} for link in links]}


@router.get("")
def status(db: Session = Depends(get_db)):
    return _out(db)


@router.post("/simplefin")
def simplefin_connect(body: TokenIn, db: Session = Depends(get_db)):
    try:
        banksync.simplefin_connect(_dir(), body.token)
        warnings = banksync.refresh_links(db, _dir(), banksync.SIMPLEFIN)
    except BankSyncError as exc:
        _fail(exc)
    return {**_out(db), "warnings": warnings}


@router.post("/enablebanking")
def eb_configure(body: EbConfigIn, db: Session = Depends(get_db)):
    try:
        banksync.eb_configure(_dir(), body.app_id, body.private_key)
    except BankSyncError as exc:
        _fail(exc)
    return _out(db)


@router.get("/enablebanking/banks")
def eb_banks(country: str):
    try:
        return {"banks": banksync.eb_banks(_dir(), country)}
    except BankSyncError as exc:
        _fail(exc)


@router.post("/enablebanking/connect")
def eb_connect(body: EbConnectIn, request: Request):
    port = request.url.port or 80
    try:
        return {"url": banksync.eb_start(
            _dir(), body.bank, body.country,
            get_settings().bank_redirect_url, port)}
    except BankSyncError as exc:
        _fail(exc)


@router.post("/enablebanking/code")
def eb_code(body: CodeIn, db: Session = Depends(get_db)):
    """Finish the bank consent with a code pasted by hand."""
    try:
        banksync.eb_finish(_dir(), body.code)
        banksync.refresh_links(db, _dir(), banksync.ENABLEBANKING)
    except BankSyncError as exc:
        _fail(exc)
    return _out(db)


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)):
    warnings: list[str] = []
    cfg = banksync.configured(_dir())
    try:
        if cfg[banksync.SIMPLEFIN]:
            warnings += banksync.refresh_links(db, _dir(), banksync.SIMPLEFIN)
        if cfg["enablebanking_sessions"]:
            warnings += banksync.refresh_links(db, _dir(),
                                               banksync.ENABLEBANKING)
    except BankSyncError as exc:
        _fail(exc)
    return {**_out(db), "warnings": warnings}


@router.put("/links/{link_id}")
def set_link(link_id: int, body: LinkIn, db: Session = Depends(get_db)):
    link = db.get(BankLink, link_id)
    if link is None:
        raise HTTPException(404, "This bank account is no longer listed. "
                            "Refresh the list and try again.")
    if body.account_id is not None and \
            db.get(Account, body.account_id) is None:
        raise HTTPException(422, "The PFI account does not exist. Choose "
                            "another account.")
    if body.account_id != link.account_id:
        link.last_synced_on = None
    link.account_id = body.account_id
    link.start_date = body.start_date
    db.commit()
    return _out(db)


@router.post("/run")
def run_now(db: Session = Depends(get_db)):
    result = banksync.run(db, _dir())
    return {**_out(db), "result": asdict(result)}


@router.delete("/{provider}")
def disconnect(provider: str, db: Session = Depends(get_db)):
    try:
        banksync.disconnect(db, _dir(), provider)
    except BankSyncError as exc:
        _fail(exc)
    return _out(db)


_PAGE = """<!doctype html><meta charset="utf-8"><title>PFI</title>
<body style="font:16px system-ui;margin:15vh auto;max-width:520px;
text-align:center"><h1 style="font-size:24px">{title}</h1><p>{text}</p>"""


@oauth_router.get(CALLBACK, response_class=HTMLResponse)
def eb_callback(state: str = "", code: str = "", error: str = "",
                db: Session = Depends(get_db)):
    if error or not code:
        return _PAGE.format(
            title="Bank connection cancelled",
            text="Nothing was connected. You can close this tab and try "
                 "again in PFI.")
    try:
        accounts = banksync.eb_finish(_dir(), code, state)
        banksync.refresh_links(db, _dir(), banksync.ENABLEBANKING)
    except BankSyncError as exc:
        return HTMLResponse(_PAGE.format(title="Bank connection failed",
                                         text=str(exc)), status_code=400)
    return _PAGE.format(
        title="Your bank is connected",
        text=f"PFI can now read {len(accounts)} account(s). Close this tab "
             "and choose, in PFI, which PFI account each one fills.")
