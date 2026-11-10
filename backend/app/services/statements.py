"""Read bank statements in OFX/QFX, QIF and CAMT.053 format.

Each reader returns rows with the same four text columns, so the result
flows through the CSV import pipeline (preview, de-duplication, rules)
unchanged: ``Date`` (ISO ``YYYY-MM-DD``), ``Amount`` (signed, ``.`` as
decimal separator), ``Description`` and ``Payee``.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation

COLUMNS = ["Date", "Amount", "Description", "Payee"]
FORMATS = {"ofx": "OFX/QFX", "qif": "QIF", "camt": "CAMT.053"}


class StatementError(ValueError):
    """Raised when a statement file cannot be read."""


def detect(text: str) -> str | None:
    """Return ``"ofx"``, ``"qif"``, ``"camt"`` or ``None`` (plain CSV).

    Parameters
    ----------
    text : str
        The decoded file content.
    """
    head = text.lstrip("﻿ \t\r\n")[:4000]
    upper = head.upper()
    if upper.startswith("OFXHEADER") or "<OFX>" in upper:
        return "ofx"
    if upper.startswith("!TYPE") or upper.startswith("!ACCOUNT"):
        return "qif"
    if head.startswith("<?xml") or head.startswith("<Document"):
        if "camt.053" in head or "BkToCstmrStmt" in text[:20000]:
            return "camt"
    return None


def _amount(text: str, what: str) -> str:
    raw = (text or "").strip().replace("'", "").replace(" ", "")
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return str(Decimal(raw))
    except InvalidOperation as exc:
        raise StatementError(f"{what}: '{text}' is not an amount") from exc


# --- OFX / QFX ---------------------------------------------------------------
_OFX_TAG = re.compile(r"<(\w+)>([^<\r\n]*)")


def parse_ofx(text: str) -> list[dict[str, str]]:
    """Read the ``<STMTTRN>`` entries of an OFX 1.x (SGML) or 2.x file.

    Parameters
    ----------
    text : str
        The decoded file content.
    """
    rows = []
    for n, block in enumerate(re.findall(
            r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))",
            text, re.S | re.I), start=1):
        fields = {k.upper(): v.strip() for k, v in _OFX_TAG.findall(block)}
        posted = fields.get("DTPOSTED", "")[:8]
        try:
            day = datetime.strptime(posted, "%Y%m%d").date().isoformat()
        except ValueError as exc:
            raise StatementError(
                f"Entry {n}: date '{posted}' is not YYYYMMDD") from exc
        name, memo = fields.get("NAME", ""), fields.get("MEMO", "")
        rows.append({"Date": day,
                     "Amount": _amount(fields.get("TRNAMT", ""),
                                       f"Entry {n}"),
                     "Description": memo or name or fields.get("TRNTYPE", ""),
                     "Payee": name if memo else ""})
    if not rows:
        raise StatementError(
            "No transactions (<STMTTRN>) were found in this OFX file. Export "
            "a statement with transactions for the date range you need.")
    return rows


# --- QIF ---------------------------------------------------------------------
def _qif_date(text: str, n: int) -> str:
    s = text.strip().replace("'", "/").replace(" ", "")
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y",
                "%m/%d/%y", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise StatementError(f"Entry {n}: date '{text}' is not a known format")


def parse_qif(text: str) -> list[dict[str, str]]:
    """Read the bank or card entries of a QIF file.

    Day-first dates are tried before month-first ones; a file whose dates
    only make sense month-first (e.g. ``12/31/2025``) is read that way.

    Parameters
    ----------
    text : str
        The decoded file content.
    """
    rows, entry, n = [], {}, 0
    monthfirst = bool(re.search(r"^D(0?[1-9]|1[0-2])/(1[3-9]|2\d|3[01])/",
                                text, re.M))
    for line in text.splitlines():
        if not line.strip() or line.startswith("!"):
            continue
        code, value = line[0], line[1:].strip()
        if code == "^":
            if entry:
                n += 1
                raw = entry.get("D", "")
                if monthfirst:
                    raw = re.sub(r"^(\d+)/(\d+)/", r"\2/\1/", raw)
                memo, payee = entry.get("M", ""), entry.get("P", "")
                rows.append({"Date": _qif_date(raw, n),
                             "Amount": _amount(entry.get("T") or
                                               entry.get("U", ""),
                                               f"Entry {n}"),
                             "Description": memo or payee,
                             "Payee": payee if memo else ""})
            entry = {}
        elif code in "DTUPM":
            entry[code] = value
    if not rows:
        raise StatementError(
            "No transactions were found in this QIF file. Each entry must "
            "end with a line containing only '^'.")
    return rows


# --- CAMT.053 ----------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, path: str):
    for part in path.split("/"):
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == part), None)
    return el


def _text(el, path: str) -> str:
    found = _find(el, path)
    return (found.text or "").strip() if found is not None else ""


def parse_camt(raw: bytes) -> list[dict[str, str]]:
    """Read the booked entries (``<Ntry>``) of an ISO 20022 CAMT.053 file.

    Parameters
    ----------
    raw : bytes
        The XML file content.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise StatementError(f"The CAMT.053 file is not valid XML ({exc})."
                             ) from exc
    rows = []
    for n, ntry in enumerate((e for e in root.iter()
                              if _local(e.tag) == "Ntry"), start=1):
        status = _text(ntry, "Sts/Cd") or _text(ntry, "Sts")
        if status and status.upper() not in ("BOOK", "BOOKED"):
            continue
        amount = _amount(_text(ntry, "Amt"), f"Entry {n}")
        if _text(ntry, "CdtDbtInd").upper() == "DBIT":
            amount = str(-abs(Decimal(amount)))
        day = (_text(ntry, "BookgDt/Dt") or _text(ntry, "BookgDt/DtTm")
               or _text(ntry, "ValDt/Dt"))[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise StatementError(f"Entry {n}: no booking date")
        tx = _find(ntry, "NtryDtls/TxDtls")
        text = " ".join(filter(None, (
            _text(tx, "RmtInf/Ustrd") if tx is not None else "",
            _text(ntry, "AddtlNtryInf")))).strip()
        payee = ""
        if tx is not None:
            party = "Cdtr" if amount.startswith("-") else "Dbtr"
            payee = (_text(tx, f"RltdPties/{party}/Nm")
                     or _text(tx, f"RltdPties/{party}/Pty/Nm"))
        rows.append({"Date": day, "Amount": amount,
                     "Description": text or payee or "Bank entry",
                     "Payee": payee})
    if not rows:
        raise StatementError(
            "No booked entries were found in this CAMT.053 file. Export the "
            "account statement (camt.053), not a notification (camt.054).")
    return rows
