"""Automatic bank import with access the user sets up for themselves.

PFI has no server and no banking licence, so it never holds a contract
with a bank-data provider. Instead the user brings their own access:

* **SimpleFIN Bridge** (US and Canada). The user subscribes at
  bridge.simplefin.org, links their banks there and pastes the setup token
  into PFI. PFI exchanges it once for an access URL and reads the accounts
  and transactions from it.
* **Enable Banking** (EU/EEA and UK, free "restricted mode"). The user
  registers an application in the Enable Banking Control Panel, links their
  own accounts to it and gives PFI the application ID and private key. PFI
  signs short-lived JWTs with that key; the bank consent goes through the
  bank's own pages.

Secrets (the SimpleFIN access URL, the Enable Banking key and session) are
kept with ``secret_store`` (Windows DPAPI). Only booked transactions are
imported; each gets a fingerprint from the provider's transaction id so a
second run never duplicates it.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, BankLink, Transaction
from . import secret_store
from .importer import Categorizer

log = logging.getLogger(__name__)

SIMPLEFIN = "simplefin"
ENABLEBANKING = "enablebanking"
EB_API = "https://api.enablebanking.com"
#: How far back the first sync of a newly linked account reaches.
FIRST_SYNC_DAYS = 90
#: SimpleFIN serves at most about this many days per request.
SIMPLEFIN_WINDOW = 60


class BankSyncError(RuntimeError):
    """Raised when a bank-data provider refuses or cannot be reached."""


@dataclass
class RemoteAccount:
    """One account as the provider reports it."""

    external_id: str
    name: str
    institution: str
    currency: str
    balance: Decimal | None = None


@dataclass
class RemoteTxn:
    """One booked transaction as the provider reports it."""

    external_id: str
    day: date
    amount: Decimal
    description: str
    merchant: str | None = None


@dataclass
class RunResult:
    """Counts of one bank-sync run."""

    imported: int = 0
    duplicates: int = 0
    accounts: int = 0
    errors: list[str] = field(default_factory=list)


def _http(method: str, url: str, **kw) -> httpx.Response:
    """Send one HTTP request (replaced by a fake in the tests)."""
    try:
        return httpx.request(method, url, timeout=60, **kw)
    except httpx.HTTPError as exc:
        raise BankSyncError(
            f"Could not reach {urlsplit(url).hostname} ({exc}). Check the "
            "internet connection and try again.") from exc


def _money(text) -> Decimal:
    try:
        return Decimal(str(text)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise BankSyncError(f"The bank sent an amount PFI cannot read: "
                            f"{text!r}.") from exc


# --- SimpleFIN ---------------------------------------------------------
def _simplefin_path(data_dir: Path) -> Path:
    return Path(data_dir) / "simplefin.access"


def simplefin_connect(data_dir: Path, setup_token: str) -> None:
    """Exchange a SimpleFIN setup token for an access URL and keep it.

    Parameters
    ----------
    data_dir : Path
        The PFI data folder that holds the secrets.
    setup_token : str
        The setup token copied from the SimpleFIN Bridge website.

    Raises
    ------
    BankSyncError
        If the token is not valid or was already used.
    """
    token = "".join(setup_token.split())
    try:
        claim = base64.b64decode(token + "=" * (-len(token) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise BankSyncError(
            "That is not a SimpleFIN setup token. Copy the whole token from "
            "the SimpleFIN Bridge website (Apps › New connection).") from exc
    if not claim.startswith("https://"):
        raise BankSyncError(
            "That is not a SimpleFIN setup token. Copy the whole token from "
            "the SimpleFIN Bridge website (Apps › New connection).")
    r = _http("POST", claim, headers={"Content-Length": "0"})
    if r.status_code == 403:
        raise BankSyncError(
            "SimpleFIN says this setup token was already used or has "
            "expired. Create a new token on the SimpleFIN Bridge website and "
            "paste it again.")
    if r.status_code != 200 or not r.text.strip().startswith("https://"):
        raise BankSyncError(
            f"SimpleFIN did not accept the token (HTTP {r.status_code}). "
            "Create a new token and try again.")
    secret_store.save(_simplefin_path(data_dir), r.text.strip())


def _simplefin_get(data_dir: Path, params: dict) -> dict:
    access = secret_store.load(_simplefin_path(data_dir))
    if not access:
        raise BankSyncError(
            "SimpleFIN is not connected. Paste a setup token in Settings › "
            "Bank sync.")
    parts = urlsplit(access)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    url = urlunsplit((parts.scheme, host, parts.path.rstrip("/")
                      + "/accounts", "", ""))
    r = _http("GET", url, params=params,
              auth=(parts.username or "", parts.password or ""))
    if r.status_code == 403:
        raise BankSyncError(
            "SimpleFIN refused the saved access (it may have been revoked). "
            "Disconnect and connect again with a new setup token.")
    if r.status_code == 402:
        raise BankSyncError(
            "SimpleFIN says the subscription needs payment. Renew it on the "
            "SimpleFIN Bridge website.")
    if r.status_code != 200:
        raise BankSyncError(f"SimpleFIN answered HTTP {r.status_code}. Try "
                            "again later.")
    return r.json()


def simplefin_accounts(data_dir: Path) -> tuple[list[RemoteAccount],
                                                list[str]]:
    """Return the accounts linked at SimpleFIN and its warnings."""
    data = _simplefin_get(data_dir, {"balances-only": "1"})
    out = []
    for a in data.get("accounts", []):
        cur = str(a.get("currency") or "USD")
        out.append(RemoteAccount(
            str(a["id"]), str(a.get("name") or a["id"]),
            str((a.get("org") or {}).get("name") or ""),
            cur.upper() if len(cur) == 3 else "USD",
            _money(a["balance"]) if a.get("balance") is not None else None))
    return out, [str(e) for e in data.get("errors", [])]


def simplefin_transactions(data_dir: Path, since: date
                           ) -> tuple[dict[str, list[RemoteTxn]], list[str]]:
    """Return booked transactions per SimpleFIN account since ``since``."""
    out: dict[str, list[RemoteTxn]] = {}
    errors: list[str] = []
    start = since
    today = date.today()
    while start <= today:
        end = min(start + timedelta(days=SIMPLEFIN_WINDOW), today
                  + timedelta(days=1))
        data = _simplefin_get(data_dir, {
            "start-date": str(_unix(start)), "end-date": str(_unix(end))})
        errors += [str(e) for e in data.get("errors", [])]
        for a in data.get("accounts", []):
            rows = out.setdefault(str(a["id"]), [])
            for t in a.get("transactions", []):
                if t.get("pending"):
                    continue
                when = datetime.fromtimestamp(int(t["posted"]), timezone.utc)
                desc = str(t.get("description") or t.get("memo") or "")
                rows.append(RemoteTxn(
                    str(t.get("id") or ""), when.date(), _money(t["amount"]),
                    desc.strip()[:500],
                    (str(t["payee"]).strip()[:200] or None)
                    if t.get("payee") else None))
        start = end
    return out, sorted(set(errors))


def _unix(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
               .timestamp())


# --- Enable Banking ----------------------------------------------------
def _eb_path(data_dir: Path) -> Path:
    return Path(data_dir) / "enablebanking.json"


def _eb_state(data_dir: Path) -> dict:
    raw = secret_store.load(_eb_path(data_dir))
    return json.loads(raw) if raw else {}


def _eb_save(data_dir: Path, state: dict) -> None:
    secret_store.save(_eb_path(data_dir), json.dumps(state))


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def eb_jwt(app_id: str, private_key_pem: str, now: int | None = None
           ) -> str:
    """Return a one-hour RS256 token for the Enable Banking API.

    Parameters
    ----------
    app_id : str
        The application ID from the Enable Banking Control Panel.
    private_key_pem : str
        The application's private key in PEM format.
    now : int, optional
        The issue time in Unix seconds (defaults to now).

    Returns
    -------
    str
        The signed JWT.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    try:
        key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise BankSyncError(
            "The private key is not a valid PEM file. Use the .pem file "
            "Enable Banking downloaded when you registered the "
            "application.") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise BankSyncError("The private key must be an RSA key (.pem from "
                            "Enable Banking).")
    now = int(time.time()) if now is None else now
    head = _b64url(json.dumps({"typ": "JWT", "alg": "RS256", "kid": app_id},
                              separators=(",", ":")).encode())
    body = _b64url(json.dumps({
        "iss": "enablebanking.com", "aud": "api.enablebanking.com",
        "iat": now, "exp": now + 3600}, separators=(",", ":")).encode())
    sig = key.sign(head + b"." + body, padding.PKCS1v15(), hashes.SHA256())
    return (head + b"." + body + b"." + _b64url(sig)).decode()


def _eb(data_dir: Path, method: str, path: str, **kw) -> dict:
    st = _eb_state(data_dir)
    if not st.get("app_id") or not st.get("key"):
        raise BankSyncError(
            "Enable Banking is not set up. Enter the application ID and "
            "private key in Settings › Bank sync.")
    headers = {"Authorization": "Bearer " + eb_jwt(st["app_id"], st["key"])}
    r = _http(method, EB_API + path, headers=headers, **kw)
    if r.status_code in (401, 403):
        raise BankSyncError(
            "Enable Banking refused the request. Check the application ID and "
            "private key, and that the application is active (link your "
            f"accounts in its Control Panel). Details: {r.text[:200]}")
    if r.status_code >= 400:
        raise BankSyncError(f"Enable Banking answered HTTP {r.status_code}: "
                            f"{r.text[:300]}")
    return r.json()


def eb_configure(data_dir: Path, app_id: str, private_key_pem: str) -> None:
    """Check and keep the user's Enable Banking application credentials."""
    app_id = app_id.strip()
    if not app_id:
        raise BankSyncError("Enter the application ID shown in the Enable "
                            "Banking Control Panel.")
    eb_jwt(app_id, private_key_pem)
    st = _eb_state(data_dir)
    st.update(app_id=app_id, key=private_key_pem.strip() + "\n")
    _eb_save(data_dir, st)


def eb_banks(data_dir: Path, country: str) -> list[str]:
    """Return the names of the banks Enable Banking reaches in a country."""
    data = _eb(data_dir, "GET", "/aspsps",
               params={"country": country.upper(), "psu_type": "personal"})
    return sorted({a["name"] for a in data.get("aspsps", [])},
                  key=str.lower)


def eb_start(data_dir: Path, bank: str, country: str, redirect_url: str,
             port: int) -> str:
    """Start the bank consent and return the bank's sign-in URL.

    Parameters
    ----------
    data_dir : Path
        The PFI data folder that holds the secrets.
    bank : str
        The bank name as listed by ``eb_banks``.
    country : str
        The two-letter country code of the bank.
    redirect_url : str
        The HTTPS page registered in the Enable Banking application; it
        passes the code back to PFI on this PC.
    port : int
        The port PFI listens on, carried in the state.

    Returns
    -------
    str
        The URL to open in the browser.
    """
    state = f"{port}.{secrets.token_urlsafe(16)}"
    until = datetime.now(timezone.utc) + timedelta(days=180)
    data = _eb(data_dir, "POST", "/auth", json={
        "access": {"valid_until": until.isoformat(timespec="seconds")},
        "aspsp": {"name": bank, "country": country.upper()},
        "state": state, "redirect_url": redirect_url,
        "psu_type": "personal"})
    st = _eb_state(data_dir)
    st["pending_state"] = state
    _eb_save(data_dir, st)
    return data["url"]


def eb_finish(data_dir: Path, code: str, state: str | None = None
              ) -> list[RemoteAccount]:
    """Turn the code from the bank's redirect into a session."""
    st = _eb_state(data_dir)
    if state is not None and state != st.get("pending_state"):
        raise BankSyncError(
            "This bank answer does not belong to the connection PFI started. "
            "Start the connection again from Settings › Bank sync.")
    data = _eb(data_dir, "POST", "/sessions", json={"code": code.strip()})
    sessions = st.get("sessions", [])
    sessions.append({"id": data["session_id"],
                     "valid_until": (data.get("access") or {})
                     .get("valid_until")})
    st.update(sessions=sessions, pending_state=None)
    _eb_save(data_dir, st)
    return [_eb_account(a) for a in data.get("accounts", [])]


def _eb_account(a: dict) -> RemoteAccount:
    ident = a.get("account_id") or {}
    name = (a.get("name") or a.get("product") or ident.get("iban")
            or a["uid"])
    return RemoteAccount(str(a["uid"]), str(name),
                         str(a.get("aspsp_name") or ""),
                         str(a.get("currency") or "EUR").upper())


def eb_accounts(data_dir: Path) -> list[RemoteAccount]:
    """Return the accounts of every saved Enable Banking session."""
    out = []
    for s in _eb_state(data_dir).get("sessions", []):
        data = _eb(data_dir, "GET", f"/sessions/{s['id']}")
        aspsp = (data.get("aspsp") or {}).get("name", "")
        for uid in data.get("accounts", []):
            if isinstance(uid, dict):
                acc = _eb_account(uid)
            else:
                info = _eb(data_dir, "GET", f"/accounts/{uid}/details")
                acc = _eb_account({**info, "uid": uid})
            acc.institution = acc.institution or aspsp
            out.append(acc)
    return out


def eb_transactions(data_dir: Path, uid: str, since: date
                    ) -> list[RemoteTxn]:
    """Return the booked transactions of one account since ``since``."""
    out: list[RemoteTxn] = []
    params = {"date_from": since.isoformat()}
    for _ in range(100):
        data = _eb(data_dir, "GET", f"/accounts/{uid}/transactions",
                   params=params)
        for t in data.get("transactions", []):
            if t.get("status") not in (None, "BOOK"):
                continue
            amt = _money((t.get("transaction_amount") or {})["amount"])
            if t.get("credit_debit_indicator") == "DBIT":
                amt = -abs(amt)
            else:
                amt = abs(amt)
            party = (t.get("creditor") if amt < 0 else t.get("debtor")) \
                or {}
            info = t.get("remittance_information") or []
            desc = " ".join(info) if isinstance(info, list) else str(info)
            day = t.get("booking_date") or t.get("value_date") \
                or t.get("transaction_date")
            ref = t.get("entry_reference") or t.get("transaction_id") or ""
            out.append(RemoteTxn(
                str(ref), date.fromisoformat(day),
                amt, (desc or party.get("name") or "").strip()[:500],
                (party.get("name") or "").strip()[:200] or None))
        key = data.get("continuation_key")
        if not key:
            break
        params = {**params, "continuation_key": key}
    return out


# --- links and import --------------------------------------------------
def configured(data_dir: Path) -> dict:
    """Return which providers are set up (without any secret)."""
    st = _eb_state(data_dir)
    return {
        SIMPLEFIN: secret_store.load(_simplefin_path(data_dir)) is not None,
        ENABLEBANKING: bool(st.get("app_id")),
        "enablebanking_app_id": st.get("app_id"),
        "enablebanking_sessions": [
            {"valid_until": s.get("valid_until")}
            for s in st.get("sessions", [])]}


def disconnect(db: Session, data_dir: Path, provider: str) -> None:
    """Forget a provider's access and its account links."""
    if provider == SIMPLEFIN:
        secret_store.save(_simplefin_path(data_dir), None)
    elif provider == ENABLEBANKING:
        secret_store.save(_eb_path(data_dir), None)
    else:
        raise BankSyncError(f"Unknown provider {provider!r}.")
    for link in db.scalars(select(BankLink).where(
            BankLink.provider == provider)):
        db.delete(link)
    db.commit()


def refresh_links(db: Session, data_dir: Path, provider: str) -> list[str]:
    """Add or update one ``BankLink`` per remote account of ``provider``.

    Returns
    -------
    list of str
        The provider's warnings (for example a bank that needs a new
        sign-in at SimpleFIN).
    """
    warnings: list[str] = []
    if provider == SIMPLEFIN:
        remote, warnings = simplefin_accounts(data_dir)
    else:
        remote = eb_accounts(data_dir)
    have = {(link.external_id): link for link in db.scalars(
        select(BankLink).where(BankLink.provider == provider))}
    for r in remote:
        link = have.get(r.external_id)
        if link is None:
            link = BankLink(provider=provider, external_id=r.external_id)
            db.add(link)
        link.name = r.name[:160]
        link.institution = r.institution[:160]
        link.currency = r.currency
        if r.balance is not None:
            link.balance = r.balance
    db.commit()
    return warnings


def _fingerprint(provider: str, link: BankLink, t: RemoteTxn) -> str:
    ident = t.external_id or f"{t.day}|{t.amount}|{t.description}"
    return hashlib.sha256(
        f"bank:{provider}:{link.external_id}:{ident}".encode()).hexdigest()


def _since(db: Session, link: BankLink) -> date:
    if link.last_synced_on:
        return link.last_synced_on - timedelta(days=7)
    if link.start_date:
        return link.start_date
    last = db.scalar(select(func.max(Transaction.txn_date)).where(
        Transaction.account_id == link.account_id))
    floor = date.today() - timedelta(days=FIRST_SYNC_DAYS)
    return max(last + timedelta(days=1), floor) if last else floor


def import_txns(db: Session, link: BankLink, txns: list[RemoteTxn],
                result: RunResult) -> None:
    """Add the transactions of one linked account that PFI lacks."""
    existing = set(db.scalars(select(Transaction.fingerprint).where(
        Transaction.account_id == link.account_id,
        Transaction.fingerprint.is_not(None))))
    categorizer = Categorizer(db)
    floor = link.start_date
    for t in txns:
        if t.amount == 0 or (floor and t.day < floor):
            continue
        fp = _fingerprint(link.provider, link, t)
        if fp in existing:
            result.duplicates += 1
            continue
        existing.add(fp)
        cat = categorizer.match(t.description, t.merchant)
        db.add(Transaction(
            account_id=link.account_id, txn_date=t.day, amount=t.amount,
            kind=categorizer.kind_for(cat, t.amount),
            description=t.description or (t.merchant or ""),
            merchant=t.merchant, category_id=cat, fingerprint=fp,
            category_source="rule" if cat is not None else None,
            reviewed=False, notes=None))
        result.imported += 1


def run(db: Session, data_dir: Path) -> RunResult:
    """Fetch new transactions for every linked account.

    Parameters
    ----------
    db : Session
        The open database session.
    data_dir : Path
        The PFI data folder that holds the secrets.

    Returns
    -------
    RunResult
        How many transactions were added and any problems per account.
    """
    result = RunResult()
    now = datetime.now(timezone.utc)
    links = [link for link in db.scalars(select(BankLink).where(
        BankLink.account_id.is_not(None)))
        if db.get(Account, link.account_id) is not None]
    by_provider: dict[str, list[BankLink]] = {}
    for link in links:
        by_provider.setdefault(link.provider, []).append(link)
    today = date.today()
    for link in links:
        link.last_run_at = now
    if SIMPLEFIN in by_provider:
        group = by_provider[SIMPLEFIN]
        try:
            since = min(_since(db, link) for link in group)
            data, warnings = simplefin_transactions(data_dir, since)
            result.errors += warnings
            for link in group:
                import_txns(db, link, data.get(link.external_id, []), result)
                link.last_synced_on = today
                link.last_error = None
                result.accounts += 1
        except BankSyncError as exc:
            result.errors.append(f"SimpleFIN: {exc}")
            for link in group:
                link.last_error = str(exc)[:500]
    for link in by_provider.get(ENABLEBANKING, []):
        try:
            txns = eb_transactions(data_dir, link.external_id,
                                   _since(db, link))
            import_txns(db, link, txns, result)
            link.last_synced_on = today
            link.last_error = None
            result.accounts += 1
        except BankSyncError as exc:
            result.errors.append(f"{link.name}: {exc}")
            link.last_error = str(exc)[:500]
    db.commit()
    return result


def due(db: Session, hours: int = 6) -> bool:
    """Tell whether linked accounts have not been synced for ``hours``."""
    runs = [link.last_run_at for link in db.scalars(select(BankLink).where(
        BankLink.account_id.is_not(None)))]
    if not runs:
        return False
    if any(r is None for r in runs):
        return True
    oldest = min(r if r.tzinfo else r.replace(tzinfo=timezone.utc)
                 for r in runs)
    return datetime.now(timezone.utc) - oldest > timedelta(hours=hours)
