"""0.4 import: OFX/QIF/CAMT.053 statements and the duplicate review."""
import json

from conftest import make_account

OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CHF<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260302120000<TRNAMT>-45.20
<FITID>1<NAME>MIGROS BERN<MEMO>Card payment 1234
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260325<TRNAMT>6500.00
<FITID>2<NAME>University of Bern
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

QIF = """!Type:Bank
D03/04/2026
T-12.50
PCoop
MLunch
^
D31/03/2026
T1,200.00
PSalary
^
"""

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.04">
<BkToCstmrStmt><Stmt>
<Ntry><Amt Ccy="CHF">89.90</Amt><CdtDbtInd>DBIT</CdtDbtInd>
<Sts>BOOK</Sts><BookgDt><Dt>2026-04-05</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Swisscom</Nm></Cdtr></RltdPties>
<RmtInf><Ustrd>Invoice April</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="CHF">250.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
<Sts>BOOK</Sts><BookgDt><Dt>2026-04-06</Dt></BookgDt>
<AddtlNtryInf>Refund health insurance</AddtlNtryInf></Ntry>
<Ntry><Amt Ccy="CHF">10.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
<Sts>PDNG</Sts><BookgDt><Dt>2026-04-07</Dt></BookgDt></Ntry>
</Stmt></BkToCstmrStmt></Document>
"""


def _import(api, acc, name, content, **extra):
    files = {"file": (name, content.encode(), "application/octet-stream")}
    prev = api.post("/api/import/preview", files=files)
    assert prev.status_code == 200, prev.text
    p = prev.json()
    g = p["guess"]
    mapping = {"account_id": acc, "date_column": g["date_column"],
               "description_column": g["description_column"],
               "amount_column": g["amount_column"],
               "merchant_column": g["merchant_column"],
               "date_format": g.get("date_format"), "decimal": g["decimal"]}
    res = api.post("/api/import/commit", files=files,
                   data={"mapping": json.dumps(mapping), **extra}).json()
    return p, mapping, res


def _txns(api, acc):
    return api.get("/api/transactions",
                   params={"account_id": acc}).json()["items"]


def test_ofx_qif_camt_statements(api):
    acc = make_account(api)
    p, _, res = _import(api, acc, "statement.ofx", OFX)
    assert p["format"] == "ofx" and res["rows_imported"] == 2
    p, _, res = _import(api, acc, "export.qif", QIF)
    assert p["format"] == "qif" and res["rows_imported"] == 2
    p, _, res = _import(api, acc, "camt053.xml", CAMT)
    assert p["format"] == "camt" and res["rows_imported"] == 2
    by = {t["description"]: t for t in _txns(api, acc)}
    assert by["Card payment 1234"]["amount"] == -45.20
    assert by["Card payment 1234"]["merchant"] == "MIGROS BERN"
    assert by["University of Bern"]["amount"] == 6500.0
    assert by["Lunch"]["txn_date"] == "2026-04-03"
    assert by["Salary"]["amount"] == 1200.0
    assert by["Invoice April"]["amount"] == -89.90
    assert by["Invoice April"]["merchant"] == "Swisscom"
    assert by["Refund health insurance"]["amount"] == 250.0
    again = _import(api, acc, "statement.ofx", OFX)[2]
    assert again["rows_imported"] == 0 and again["rows_duplicate"] == 2


def test_bad_statement_messages(api):
    files = {"file": ("x.ofx", b"OFXHEADER:100\n<OFX></OFX>", "text/plain")}
    r = api.post("/api/import/preview", files=files)
    assert r.status_code == 422 and "No transactions" in r.json()["detail"]


CSV1 = """Date;Text;Amount
01.05.2026;COOP 123 BERN;-20.00
01.05.2026;COOP 123 BERN;-20.00
02.05.2026;SBB TICKET;-8.40
"""
CSV2 = """Date;Text;Amount
01.05.2026;COOP-123 BERN CH;-20.00
02.05.2026;SBB TICKET;-8.40
03.05.2026;NEW SHOP;-5.00
"""


def test_possible_duplicates_review(api):
    acc = make_account(api)
    _, mapping, res = _import(api, acc, "may1.csv", CSV1)
    assert res["rows_imported"] == 3
    files = {"file": ("may2.csv", CSV2.encode(), "text/csv")}
    check = api.post("/api/import/check", files=files,
                     data={"mapping": json.dumps(mapping)}).json()
    assert check["rows_duplicate"] == 1 and check["rows_new"] == 1
    [pos] = check["possible"]
    assert pos["description"] == "COOP-123 BERN CH"
    assert pos["existing"]["description"] == "COOP 123 BERN"
    commit = api.post("/api/import/commit", files=files, data={
        "mapping": json.dumps(mapping),
        "skip_lines": json.dumps([pos["line"]])}).json()
    assert commit["rows_imported"] == 1 and commit["rows_skipped"] == 1
    assert commit["rows_duplicate"] == 2
    assert len(_txns(api, acc)) == 4
    bad = api.post("/api/import/commit", files=files, data={
        "mapping": json.dumps(mapping), "skip_lines": "nope"})
    assert bad.status_code == 422


def test_possible_duplicate_is_imported_unless_skipped(api):
    acc = make_account(api)
    _, mapping, _ = _import(api, acc, "may1.csv", CSV1)
    files = {"file": ("may2.csv", CSV2.encode(), "text/csv")}
    res = api.post("/api/import/commit", files=files,
                   data={"mapping": json.dumps(mapping)}).json()
    assert res["rows_imported"] == 2 and res["rows_skipped"] == 0


def test_saved_mapping_is_recognised(api):
    acc = make_account(api)
    _, _, res = _import(api, acc, "may1.csv", CSV1,
                        save_preset="My bank")
    assert res["preset"] == "My bank"
    files = {"file": ("june.csv", CSV2.encode(), "text/csv")}
    prev = api.post("/api/import/preview", files=files).json()
    assert prev["preset"]["name"] == "My bank"
