"""Receipt reading: amount, date, shop and currency from OCR text."""
from datetime import date
from decimal import Decimal

import pytest

from app.services import receipts

TODAY = date(2026, 11, 22)

MIGROS = """MIGROS
Filiale Bern Bahnhof
Tel. 058 567 89 00
Bananen        1.95
Vollmilch 1l   1.60
Brot           3.20
Total CHF      6.75
Bar            10.00
Rückgeld       3.25
MWST 2.6%      0.17
21.11.2026 18:42
"""

MARJANE = """*** MARJANE ***
Bienvenue
Hay Riad Rabat
LAIT CENTRALE      7,50
PAIN               2,00
HUILE 1L          24,90
SOUS-TOTAL        34,40
NET A PAYER       34,40 DH
ESPECES           50,00
RENDU             15,60
Le 14/10/2026 a 11:05
"""

US = """Whole Foods Market
www.wholefoods.com
Organic apples   4.99
Coffee beans    12.49
Subtotal        17.48
Tax              1.40
TOTAL          $18.88
VISA CARD      $18.88
03/04/2026 09:12
"""

SPLIT_LINES = """CAFE DU MONDE
2 x Espresso
Montant TTC
9,80 €
Date: 2 nov. 2026
"""

FRENCH_THOUSANDS = """BRICO DEPOT
Perceuse                1 249,00
TOTAL TTC               1 249,00 EUR
05.09.2026
"""


@pytest.mark.parametrize("text, amount, when, shop, currency", [
    (MIGROS, "6.75", "2026-11-21", "Migros", "CHF"),
    (MARJANE, "34.40", "2026-10-14", "Marjane", "MAD"),
    (SPLIT_LINES, "9.80", "2026-11-02", "Cafe Du Monde", "EUR"),
    (FRENCH_THOUSANDS, "1249.00", "2026-09-05", "Brico Depot", "EUR"),
])
def test_reads_receipts(text, amount, when, shop, currency):
    found = receipts.parse_receipt(text, today=TODAY)
    assert found["amount"] == amount
    assert found["amount_source"] == "total"
    assert found["date"] == when
    assert found["merchant"] == shop
    assert found["currency"] == currency


def test_us_receipt_is_month_first_and_skips_subtotal_and_tax():
    found = receipts.parse_receipt(US, today=TODAY, dayfirst=False)
    assert found["amount"] == "18.88"
    assert found["date"] == "2026-03-04"
    assert found["merchant"] == "Whole Foods Market"
    assert found["currency"] == "USD"
    # The same text read day first gives 3 April.
    assert receipts.parse_receipt(US, today=TODAY)["date"] == "2026-04-03"


def test_falls_back_to_largest_amount_and_ignores_future_dates():
    found = receipts.parse_receipt("Kiosk\nA 2.50\nB 4.10\n01.01.2099",
                                   today=TODAY)
    assert found["amount"] == "4.10"
    assert found["amount_source"] == "largest"
    assert found["date"] is None


def test_nothing_readable():
    found = receipts.parse_receipt("", today=TODAY)
    assert found == {"amount": None, "amount_source": "none", "date": None,
                     "merchant": None, "currency": None, "lines": []}


@pytest.mark.parametrize("token, value", [
    ("1'234.50", "1234.50"), ("1.234,50", "1234.50"),
    ("1,234.50", "1234.50"), ("12,5", "12.50"), ("7", "7.00"),
    ("abc", None),
])
def test_parse_amount(token, value):
    got = receipts.parse_amount(token)
    assert got == (Decimal(value) if value else None)


def test_parse_endpoint_guesses_category_from_history(api):
    groceries = api.post("/api/categories", json={
        "name": "Supermarket runs", "kind": "expense"}).json()
    account = api.post("/api/accounts", json={
        "name": "Card", "type": "checking", "currency": "CHF",
        "opening_date": "2026-01-01"}).json()
    api.post("/api/transactions", json={
        "account_id": account["id"], "txn_date": "2026-10-01",
        "amount": "-12.00", "kind": "expense", "description": "MIGROS BERN",
        "category_id": groceries["id"]}).raise_for_status()
    found = api.post("/api/receipts/parse", json={"text": MIGROS}).json()
    assert found["amount"] == "6.75"
    assert found["category_id"] == groceries["id"]


def test_scan_without_windows_ocr_says_so(api, monkeypatch):
    monkeypatch.setattr(receipts, "ocr_available", lambda: False)
    assert api.get("/api/receipts/status").json() == {"ocr": False}
    res = api.post("/api/receipts/scan",
                   files={"file": ("r.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert res.status_code == 501
    assert "Windows" in res.json()["detail"]


@pytest.mark.skipif(not receipts.ocr_available(),
                    reason="Windows text recognition is only on Windows")
def test_windows_ocr_reads_a_rendered_receipt():
    """Runs on the PC build: Windows.Media.Ocr reads a drawn receipt."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 700), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(["MIGROS", "Brot 3.20", "Milch 1.60",
                              "TOTAL CHF 4.80", "21.11.2026"]):
        draw.text((60, 60 + i * 110), line, fill="black", font=font)
    buf = BytesIO()
    img.save(buf, "PNG")
    try:
        text = receipts.ocr_image(buf.getvalue())
    except receipts.OcrUnavailable as exc:
        pytest.skip(str(exc))
    found = receipts.parse_receipt(text, today=TODAY)
    assert found["amount"] == "4.80", text
    assert found["date"] == "2026-11-21", text
