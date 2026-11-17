"""0.8: built-in US bank layouts and automatic CSV detection."""
import json

import pytest

from app.services import bank_presets, importer
from conftest import make_account

CHASE_CARD = ("Transaction Date,Post Date,Description,Category,Type,"
              "Amount,Memo\n") + """\
11/03/2026,11/04/2026,STARBUCKS 123,Food,Sale,-6.45,
11/14/2026,11/15/2026,AUTOMATIC PAYMENT - THANK,,Payment,250.00,
"""
CHASE_CHECKING = ("Details,Posting Date,Description,Amount,Type,Balance,"
                  "Check or Slip #\n") + """\
DEBIT,11/02/2026,"TRADER JOE'S #552",-48.12,DEBIT_CARD,1951.88,,
CREDIT,11/15/2026,ACME PAYROLL,2100.00,ACH_CREDIT,4051.88,,
"""
BOFA_CHECKING = """Description,,Summary Amt.
Beginning balance as of 11/01/2026,,"2,000.00"
Total credits,,"2,100.00"
Ending balance as of 11/30/2026,,"4,051.88"

Date,Description,Amount,Running Bal.
11/01/2026,Beginning balance as of 11/01/2026,,"2,000.00"
11/02/2026,"SAFEWAY #1234","-48.12","1,951.88"
11/15/2026,"ACME PAYROLL DES:PAYROLL","2,100.00","4,051.88"
"""
WELLS = """"11/02/2026","-48.12","*","","SAFEWAY STORE 1234"
"11/15/2026","2100.00","*","","ACME PAYROLL"
"""
AMEX = """Date,Description,Card Member,Account #,Amount
11/03/2026,UBER TRIP,J DOE,-12345,23.10
11/20/2026,ONLINE PAYMENT - THANK YOU,J DOE,-12345,-500.00
"""
CITI = """Status,Date,Description,Debit,Credit
Cleared,11/03/2026,WHOLE FOODS,54.20,
Cleared,11/20/2026,ONLINE PAYMENT,,-300.00
"""
CAPONE = ("Transaction Date,Posted Date,Card No.,Description,Category,"
          "Debit,Credit\n") + """\
2026-11-03,2026-11-04,1234,SHELL OIL,Gas/Automotive,41.00,
2026-11-21,2026-11-21,1234,CAPITAL ONE AUTOPAY,Payment/Credit,,200.00
"""


def _go(api, acc, name, content):
    files = {"file": (name, content.encode(), "text/csv")}
    p = api.post("/api/import/preview", files=files)
    assert p.status_code == 200, p.text
    p = p.json()
    m = dict(p["preset"]["mapping"] if p["preset"] else p["guess"])
    m = {k: v for k, v in m.items() if k in {
        "date_column", "description_column", "amount_column",
        "debit_column", "credit_column", "merchant_column", "date_format",
        "dayfirst", "decimal", "invert_sign"}}
    m.update(account_id=acc, skip_rows=p["skip_rows"])
    m.setdefault("invert_sign", p["guess"].get("mostly_positive", False))
    r = api.post("/api/import/commit", files=files,
                 data={"mapping": json.dumps(m)})
    assert r.status_code in (200, 201), r.text
    rows = api.get("/api/transactions", params={"account_id": acc}).json()
    got = sorted((t["txn_date"], float(t["amount"])) for t in rows["items"])
    return p, got


@pytest.mark.parametrize("name, text, bank, expected", [
    ("Chase.csv", CHASE_CARD, "Chase credit card",
     [("2026-11-03", -6.45), ("2026-11-14", 250.0)]),
    ("Chase1234_Activity.csv", CHASE_CHECKING, "Chase checking",
     [("2026-11-02", -48.12), ("2026-11-15", 2100.0)]),
    ("stmt.csv", BOFA_CHECKING, "Bank of America checking",
     [("2026-11-02", -48.12), ("2026-11-15", 2100.0)]),
    ("Checking1.csv", WELLS, "Wells Fargo",
     [("2026-11-02", -48.12), ("2026-11-15", 2100.0)]),
    ("activity.csv", AMEX, "American Express",
     [("2026-11-03", -23.10), ("2026-11-20", 500.0)]),
    ("citi.csv", CITI, "Citi credit card",
     [("2026-11-03", -54.20), ("2026-11-20", 300.0)]),
    ("capone.csv", CAPONE, "Capital One credit card",
     [("2026-11-03", -41.0), ("2026-11-21", 200.0)]),
])
def test_us_bank_layouts_import_with_right_signs(api, name, text, bank,
                                                 expected):
    acc = make_account(api, currency="USD")
    p, got = _go(api, acc, name, text)
    assert p["preset"] and p["preset"]["name"] == bank
    assert p["preset"]["builtin"] is True
    assert got == expected


def test_bofa_summary_lines_are_skipped():
    assert importer.detect_skip(BOFA_CHECKING.encode()) == 5
    assert importer.detect_skip(CHASE_CARD.encode()) == 0


def test_saved_mapping_wins_over_builtin(api):
    acc = make_account(api, currency="USD")
    files = {"file": ("Chase.csv", CHASE_CARD.encode(), "text/csv")}
    m = {"account_id": acc, "date_column": "Post Date",
         "description_column": "Memo", "amount_column": "Amount",
         "dayfirst": False}
    api.post("/api/import/commit", files=files,
             data={"mapping": json.dumps(m), "save_preset": "My Chase"})
    p = api.post("/api/import/preview", files=files).json()
    assert p["preset"]["name"] == "My Chase"


def test_unknown_layout_has_no_builtin():
    assert bank_presets.match(["Date", "Text", "Betrag"]) is None


def test_date_order_is_read_from_the_file():
    us = importer.read_csv(b"Date,Text,Amount\n11/28/2026,a,-1\n")[0]
    eu = importer.read_csv(b"Date,Text,Amount\n28/11/2026,a,-1\n")[0]
    both = importer.read_csv(b"Date,Text,Amount\n03/04/2026,a,-1\n")[0]
    assert importer.guess_mapping(us)["dayfirst"] is False
    assert importer.guess_mapping(eu)["dayfirst"] is True
    assert importer.guess_mapping(both)["dayfirst"] is None
