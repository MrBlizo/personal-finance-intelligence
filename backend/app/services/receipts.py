"""Read the amount, date and shop from a photographed receipt.

The text comes from the operating system's own offline OCR: Windows.Media.Ocr
on the PC (through the ``winrt`` packages) and ML Kit on the phone, which
runs the same rules in Dart. Nothing leaves the device.

:func:`parse_receipt` is plain text processing and works anywhere;
:func:`ocr_image` needs Windows and raises :class:`OcrUnavailable`
elsewhere.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Transaction


class OcrUnavailable(RuntimeError):
    """Raised when this computer has no usable text recognition."""


# Words that introduce the amount actually paid, strongest first. Lower
# case, accents removed (see _plain).
TOTAL_WORDS = (
    "net a payer", "total a payer", "montant a payer", "a payer",
    "amount due", "total due", "balance due", "grand total",
    "total ttc", "montant ttc", "zu zahlen", "gesamtbetrag", "gesamt",
    "summe", "totale", "total chf", "total eur", "total mad", "total",
    "montant", "betrag", "importe", "المجموع", "المبلغ",
)
NOT_TOTAL = ("subtotal", "sous-total", "sous total", "zwischensumme",
             "tva", "tax", "mwst", "vat", "rendu", "change", "monnaie",
             "rabais", "remise", "discount", "points", "cash", "especes",
             "bar", "carte", "card")
SKIP_SHOP = ("receipt", "ticket", "facture", "invoice", "quittung",
             "beleg", "bienvenue", "welcome", "willkommen", "merci",
             "thank", "danke", "tel", "tél", "www", "http", "@")
CURRENCIES = (("CHF", "CHF"), ("EUR", "EUR"), ("€", "EUR"), ("MAD", "MAD"),
              ("DH", "MAD"), ("DHS", "MAD"), ("USD", "USD"), ("$", "USD"),
              ("GBP", "GBP"), ("£", "GBP"), ("درهم", "MAD"))
MONTHS = {m: i + 1 for i, names in enumerate((
    "jan janv januar enero", "feb fev fevr februar febrero",
    "mar mars marz marzo", "apr avr avril april abril",
    "may mai mayo", "jun juin juni junio", "jul juil juli julio",
    "aug aout august agosto", "sep sept septembre september septiembre",
    "oct octobre oktober octubre", "nov novembre november noviembre",
    "dec decembre dezember diciembre")) for m in names.split()}

# 1'234.50  1 234,50  1.234,50  1,234.50  12.5  12,50  -> one amount
AMOUNT = re.compile(
    r"(?<![\d.,'])(\d{1,3}(?:[ '., ]\d{3})+|\d+)([.,]\d{1,2})?"
    r"(?![\d])")
NUMERIC_DATE = re.compile(
    r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"
    r"|\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")
WORD_DATE = re.compile(r"\b(\d{1,2})\.?\s+([a-z]{3,9})\.?\s+(\d{2,4})\b")


def _plain(text: str) -> str:
    """Lower-case and drop accents so "Net à payer" matches "net a payer"."""
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_amount(token: str) -> Decimal | None:
    """Read one printed amount, whatever the thousands and decimal marks.

    Parameters
    ----------
    token : str
        The text of one amount, such as ``"1'234.50"`` or ``"12,50"``.

    Returns
    -------
    Decimal or None
        The value, or None when the text is not an amount.
    """
    s = token.strip().replace(" ", " ")
    m = re.fullmatch(r"(.*?)([.,])(\d{1,2})", s)
    whole, cents = (m.group(1), m.group(3)) if m else (s, "")
    whole = re.sub(r"[ '.,]", "", whole)
    if not whole.isdigit():
        return None
    try:
        return Decimal(f"{whole}.{cents or '0'}").quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _amounts(line: str) -> list[Decimal]:
    """All amounts with cents on a line (whole numbers are often codes)."""
    out = []
    for m in AMOUNT.finditer(line):
        if not m.group(2):
            continue
        value = parse_amount(m.group(0))
        if value is not None and value > 0:
            out.append(value)
    return out


def _valid(y: int, m: int, d: int, today: date) -> date | None:
    if y < 100:
        y += 2000
    try:
        found = date(y, m, d)
    except ValueError:
        return None
    return found if date(2000, 1, 1) <= found <= today else None


def find_date(text: str, today: date | None = None,
              dayfirst: bool = True) -> date | None:
    """Return the first plausible purchase date printed on the receipt.

    Parameters
    ----------
    text : str
        The recognised text.
    today : date, optional
        The latest acceptable date; dates after it are ignored.
    dayfirst : bool
        The reading of ambiguous dates such as 03/04/2026: day first
        (Europe, Morocco) when True, month first (United States) otherwise.

    Returns
    -------
    date or None
        The date, or None when none could be read.
    """
    today = today or date.today()
    for m in NUMERIC_DATE.finditer(text):
        if m.group(1):
            found = _valid(int(m.group(1)), int(m.group(2)),
                           int(m.group(3)), today)
        else:
            a, b, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
            d, mo = (a, b) if dayfirst or a > 12 else (b, a)
            if mo > 12:
                d, mo = mo, d
            found = _valid(y, mo, d, today)
        if found:
            return found
    for m in WORD_DATE.finditer(_plain(text)):
        month = MONTHS.get(m.group(2)[:4]) or MONTHS.get(m.group(2)[:3])
        if month:
            found = _valid(int(m.group(3)), month, int(m.group(1)), today)
            if found:
                return found
    return None


def find_total(lines: list[str]) -> tuple[Decimal | None, str]:
    """Return the amount paid and how it was found.

    Parameters
    ----------
    lines : list of str
        The receipt's lines, top to bottom.

    Returns
    -------
    tuple of (Decimal or None, str)
        The amount and ``"total"`` (next to a total word), ``"largest"``
        (the biggest amount on the receipt) or ``"none"``.
    """
    plain = [_plain(x) for x in lines]
    for word in TOTAL_WORDS:
        for i, line in enumerate(plain):
            if word not in line or any(n in line for n in NOT_TOTAL
                                       if n not in word):
                continue
            # The amount is on the same line or, in two-column layouts that
            # OCR splits, on the next line.
            for candidate in (lines[i], lines[i + 1] if i + 1 < len(lines)
                              else ""):
                found = _amounts(candidate)
                if found:
                    return found[-1], "total"
    every = [a for line in lines for a in _amounts(line)]
    return (max(every), "largest") if every else (None, "none")


def find_shop(lines: list[str]) -> str | None:
    """Return the shop name: the first line near the top that reads as one.

    Parameters
    ----------
    lines : list of str
        The receipt's lines, top to bottom.

    Returns
    -------
    str or None
        The name, title-cased when printed in capitals, or None.
    """
    for line in lines[:8]:
        text = line.strip(" *-=#:.")
        letters = sum(c.isalpha() for c in text)
        if letters < 3 or letters < len(text) / 2:
            continue
        if any(w in _plain(text) for w in SKIP_SHOP):
            continue
        if NUMERIC_DATE.search(text):
            continue
        return text.title() if text.isupper() else text
    return None


def find_currency(text: str) -> str | None:
    """Return the ISO code of the currency printed on the receipt, if any."""
    counts = Counter()
    for mark, code in CURRENCIES:
        pattern = (re.escape(mark) if not mark.isalpha()
                   else rf"(?<![A-Za-z]){mark}(?![A-Za-z])")
        counts[code] += len(re.findall(pattern, text, re.IGNORECASE))
    code, n = counts.most_common(1)[0]
    return code if n else None


def parse_receipt(text: str, today: date | None = None,
                  dayfirst: bool = True) -> dict:
    """Read amount, date, shop and currency from recognised receipt text.

    Parameters
    ----------
    text : str
        The text recognised on the receipt, one printed line per line.
    today : date, optional
        The latest acceptable purchase date (defaults to today).
    dayfirst : bool
        The reading of ambiguous numeric dates (see :func:`find_date`).

    Returns
    -------
    dict
        ``amount`` (str or None), ``amount_source``, ``date`` (ISO string
        or None), ``merchant``, ``currency`` and the cleaned ``lines``.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    amount, source = find_total(lines)
    found = find_date(text, today, dayfirst)
    return {
        "amount": str(amount) if amount is not None else None,
        "amount_source": source,
        "date": found.isoformat() if found else None,
        "merchant": find_shop(lines),
        "currency": find_currency(text),
        "lines": lines,
    }


def guess_category(db: Session, merchant: str | None) -> int | None:
    """Return the category used most often for this shop before, if any.

    Parameters
    ----------
    db : Session
        The open database session.
    merchant : str or None
        The shop name read from the receipt.

    Returns
    -------
    int or None
        A category id, or None when the shop is new.
    """
    if not merchant or len(merchant) < 3:
        return None
    key = f"%{merchant.lower()[:40]}%"
    row = db.execute(
        select(Transaction.category_id, func.count())
        .where(Transaction.category_id.is_not(None),
               Transaction.amount < 0,
               (func.lower(Transaction.merchant).like(key))
               | (func.lower(Transaction.description).like(key)))
        .group_by(Transaction.category_id)
        .order_by(func.count().desc()).limit(1)).first()
    return row[0] if row else None


def ocr_available() -> bool:
    """Return True when Windows text recognition can be used here."""
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
    except Exception:
        return False
    return True


async def _ocr(data: bytes) -> str:
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode, BitmapDecoder, BitmapInterpolationMode,
        BitmapPixelFormat, BitmapTransform, ColorManagementMode,
        ExifOrientationMode)
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import (
        DataWriter, InMemoryRandomAccessStream)

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    # Phone photos are larger than the engine accepts (about 2600 px) and
    # often stored sideways with an EXIF rotation: scale down (scaling
    # applies before rotation, so one factor fits both sides) and turn
    # upright.
    transform = BitmapTransform()
    biggest = max(decoder.pixel_width, decoder.pixel_height)
    scale = min(1.0, OcrEngine.max_image_dimension / biggest)
    transform.scaled_width = max(1, int(decoder.pixel_width * scale))
    transform.scaled_height = max(1, int(decoder.pixel_height * scale))
    transform.interpolation_mode = BitmapInterpolationMode.FANT
    bitmap = await decoder.get_software_bitmap_async(
        BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED, transform,
        ExifOrientationMode.RESPECT_EXIF_ORIENTATION,
        ColorManagementMode.DO_NOT_COLOR_MANAGE)
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable(
            "Windows has no text-recognition language installed. Add one in "
            "Settings > Time & language > Language & region (for example "
            "English or French with the 'Optical character recognition' "
            "feature), then try again.")
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def ocr_image(data: bytes) -> str:
    """Recognise the text in a receipt photo with Windows' offline OCR.

    Parameters
    ----------
    data : bytes
        The image file's content (JPEG, PNG, BMP, TIFF, GIF or HEIC when the
        HEIF extension is installed).

    Returns
    -------
    str
        The recognised text, one line per printed line.

    Raises
    ------
    OcrUnavailable
        When not running on Windows, the ``winrt`` packages are missing or
        no OCR language is installed.
    ValueError
        When Windows cannot decode the image.
    """
    if not ocr_available():
        raise OcrUnavailable(
            "Receipt reading uses the text recognition built into Windows "
            "10/11, which is not available here. On the phone app the camera "
            "reads receipts instead; on this computer type the amount in.")
    try:
        return asyncio.run(_ocr(data))
    except OcrUnavailable:
        raise
    except OSError as exc:
        raise ValueError(
            "Windows could not open this image. Save it as JPEG or PNG and "
            f"drop it again. ({exc})") from exc
