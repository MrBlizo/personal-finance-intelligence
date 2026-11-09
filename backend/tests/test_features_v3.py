"""Tests for v0.3: automation, learned categories, investments, reports."""
import io
import json
from datetime import date, timedelta

import pytest

from app.db import SessionLocal
from app.services import automation, performance, prices
from conftest import cat_id, make_account


# --- settings ----------------------------------------------------------------
def test_partial_settings_and_validation(api):
    r = api.put("/api/settings", json={"language": "ar", "app_lock": "hello",
                                       "lock_after_minutes": 10})
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["language"], s["app_lock"], s["lock_after_minutes"]) == (
        "ar", "hello", 10)
    assert s["base_currency"] == "CHF"
    assert api.put("/api/settings", json={"language": "de"}).status_code \
        == 422
    bad = api.put("/api/settings", json={
        "allocation_targets": {"etf": 50, "bond": 20}})
    assert bad.status_code == 422 and "100" in bad.text
    ok = api.put("/api/settings", json={
        "allocation_targets": {"etf": 60, "bond": 40}}).json()
    assert ok["allocation_targets"] == {"etf": 60.0, "bond": 40.0}


# --- recurring auto-post and reminders -----------------------------------
def test_auto_post_is_idempotent_and_never_backfills(api):
    acc = make_account(api)
    rent = cat_id(api, "Rent")
    today = date.today()
    start = today - timedelta(days=200)
    r = api.post("/api/recurring", json={
        "name": "Rent", "account_id": acc, "category_id": rent,
        "amount": "-1850", "frequency": "monthly",
        "start_date": start.isoformat(), "auto_post": True,
        "remind_days": 5})
    assert r.status_code == 201, r.text
    item = r.json()
    # Switching auto-post on must not book the 6 past months.
    assert item["last_posted"] == (today - timedelta(days=1)).isoformat()
    assert api.post("/api/recurring/post-due").json()["posted"] in (0, 1)
    with SessionLocal() as db:
        later = today + timedelta(days=70)
        first = automation.post_due(db, later)
        db.commit()
        again = automation.post_due(db, later)
        db.commit()
    assert len(first) in (2, 3) and again == []
    txns = api.get("/api/transactions").json()["items"]
    assert all(t["amount"] == -1850 and t["category_id"] == rent
               for t in txns)
    assert len({t["txn_date"] for t in txns}) == len(txns)


def test_reminders_and_notifications_once(api):
    acc = make_account(api)
    due = date.today() + timedelta(days=2)
    api.post("/api/recurring", json={
        "name": "Phone", "account_id": acc, "amount": "-45",
        "frequency": "monthly", "start_date": due.isoformat(),
        "remind_days": 3})
    rem = api.get("/api/reminders").json()
    assert [r["name"] for r in rem] == ["Phone"]
    assert rem[0]["days_left"] == 2
    first = api.post("/api/reminders/notifications").json()
    second = api.post("/api/reminders/notifications").json()
    assert len(first) == 1 and second == []


# --- learned categorisation ------------------------------------------------
def _history(api, acc):
    groc, bus, subs = (cat_id(api, "Groceries"),
                       cat_id(api, "Public Transport"),
                       cat_id(api, "Subscriptions"))
    day = date(2026, 1, 1)
    patterns = [("MIGROS BERN BAHNHOF", "-54.20", groc),
                ("COOP PRONTO 4021", "-18.90", groc),
                ("SBB CFF FFS TICKET", "-12.60", bus),
                ("BERNMOBIL APP", "-4.60", bus),
                ("NETFLIX.COM", "-15.90", subs),
                ("SPOTIFY P1A2B3", "-12.95", subs)]
    for i in range(36):
        text, amount, cat = patterns[i % len(patterns)]
        api.post("/api/transactions", json={
            "account_id": acc, "txn_date": (day + timedelta(days=i)
                                            ).isoformat(),
            "amount": amount, "description": text, "category_id": cat})
    return groc, bus, subs


def test_learner_validation_and_suggestions(api):
    acc = make_account(api)
    groc, bus, subs = _history(api, acc)
    st = api.get("/api/learn/status").json()
    assert st["n_train"] == 28 and st["n_test"] == 8
    assert st["accuracy"] >= st["baseline"]
    assert st["accuracy"] >= 0.75
    for text in ("MIGROS ZURICH HB", "SBB MOBILE TICKET", "NETFLIX"):
        api.post("/api/transactions", json={
            "account_id": acc, "txn_date": "2026-03-01", "amount": "-9.99",
            "description": text})
    sug = {s["description"]: s for s in
           api.get("/api/learn/suggestions").json()}
    assert sug["MIGROS ZURICH HB"]["category_id"] == groc
    assert sug["SBB MOBILE TICKET"]["category_id"] == bus
    assert sug["NETFLIX"]["category_id"] == subs
    assert "migros" in sug["MIGROS ZURICH HB"]["why"]
    res = api.post("/api/learn/apply", json={"min_confidence": 0.5}).json()
    assert res["updated"] == 3
    # Model-assigned categories are not used as training data.
    assert api.get("/api/learn/status").json()["examples"] == 36


def test_import_uses_learned_categories(api):
    acc = make_account(api)
    groc, *_ = _history(api, acc)
    api.put("/api/settings", json={"auto_categorize_threshold": 0.7})
    csv = "Date,Description,Amount\n05.04.2026,MIGROS BASEL,-33.10\n" \
          "06.04.2026,UNKNOWN SHOP XYZ,-10.00\n"
    files = {"file": ("s.csv", csv.encode(), "text/csv")}
    mapping = {"account_id": acc, "date_column": "Date",
               "description_column": "Description",
               "amount_column": "Amount"}
    res = api.post("/api/import/commit", files=files,
                   data={"mapping": json.dumps(mapping)}).json()
    assert res["rows_imported"] == 2 and res["learned"] >= 1
    rows = api.get("/api/transactions", params={"q": "MIGROS BASEL"}
                   ).json()["items"]
    assert rows[0]["category_id"] == groc


# --- investments -------------------------------------------------------------
def test_xirr_known_values():
    d0 = date(2024, 1, 1)
    assert performance.xirr([(d0, -1000), (date(2024, 12, 31), 1100)]) \
        == pytest.approx(0.1003, abs=2e-3)
    assert performance.xirr([(d0, -100), (date(2025, 1, 1), -100)]) is None


def _portfolio(api):
    acc = make_account(api, "Broker", type_="investment", opening="5000")
    h = api.post("/api/holdings", json={
        "account_id": acc, "symbol": "VT", "name": "World ETF",
        "asset_class": "etf", "currency": "CHF", "price_source": "stooq",
        "price_symbol": "vt.us"}).json()["id"]
    api.post(f"/api/holdings/{h}/trades", json={
        "trade_date": "2025-01-02", "trade_type": "buy", "quantity": "10",
        "price": "100"})
    api.post(f"/api/holdings/{h}/trades", json={
        "trade_date": "2025-07-01", "trade_type": "dividend",
        "cash_amount": "20"})
    api.post(f"/api/holdings/{h}/prices", json={
        "price_date": "2026-01-02", "price": "110"})
    return acc, h


def test_performance_endpoint(api):
    _, h = _portfolio(api)
    api.put("/api/settings", json={"allocation_targets": {"etf": 80,
                                                          "bond": 20}})
    p = api.get("/api/investments/performance").json()
    row = p["holdings"][0]
    assert row["value_base"] == pytest.approx(1100)
    # Independent check: the flows discounted at XIRR must sum to ~0.
    r, today = row["xirr"], date.today()
    flows = [(date(2025, 1, 2), -1000), (date(2025, 7, 1), 20),
             (today, 1100)]
    npv = sum(v / (1 + r) ** ((d - flows[0][0]).days / 365)
              for d, v in flows)
    assert abs(npv) < 0.01 and 0.03 < r < 0.10
    assert p["total"]["twr_cumulative"] == pytest.approx(0.12, abs=0.005)
    assert p["dividends_by_year"] == [{"year": 2025, "amount": 20.0}]
    alloc = {a["asset_class"]: a for a in p["allocation"]}
    assert alloc["etf"]["actual_pct"] == pytest.approx(100)
    assert alloc["etf"]["drift_pp"] == pytest.approx(20)
    assert alloc["bond"]["rebalance"] == pytest.approx(220)


STOOQ = ("Date,Open,High,Low,Close,Volume\n2026-11-05,1,1,1,121.5,10\n"
         "2026-11-06,1,1,1,122.25,10\n")


def test_price_update_keeps_manual_prices(api, monkeypatch):
    _, h = _portfolio(api)
    api.post(f"/api/holdings/{h}/prices", json={
        "price_date": "2026-11-06", "price": "999"})
    calls = []

    def fake(url, timeout=20.0):
        calls.append(url)
        return STOOQ.encode()
    monkeypatch.setattr(prices, "_get", fake)
    no_key = api.post("/api/prices/update").json()
    assert no_key["updated"] == 0 and "API key" in no_key["errors"][0]["error"]
    s = api.put("/api/settings", json={"stooq_api_key": "abc123XYZ"}).json()
    assert s["stooq_api_key_set"] and s["stooq_api_key_hint"] == "3XYZ"
    assert "abc123XYZ" not in json.dumps(s)
    res = api.post("/api/prices/update").json()
    assert res["updated"] == 1 and res["new_prices"] == 1
    assert "s=vt.us" in calls[0] and "apikey=abc123XYZ" in calls[0]
    rows = {p["price_date"]: p for p in
            api.get(f"/api/holdings/{h}/prices").json()}
    assert rows["2026-11-06"]["price"] == 999
    assert rows["2026-11-05"]["source"] == "stooq"


def test_price_update_reports_errors(api, monkeypatch):
    _portfolio(api)
    api.put("/api/settings", json={"stooq_api_key": "k"})
    monkeypatch.setattr(prices, "_get", lambda url, timeout=20.0: b"No data")
    res = api.post("/api/prices/update").json()
    assert res["updated"] == 0 and "vt.us" in res["errors"][0]["error"]
    page = b"Get your apikey:\n 1. Open https://stooq.com/q/d/?s=spy.us"
    monkeypatch.setattr(prices, "_get", lambda url, timeout=20.0: page)
    res = api.post("/api/prices/update").json()
    assert "did not accept the API key" in res["errors"][0]["error"]


TWELVE = {"meta": {"symbol": "VT", "currency": "USD"}, "status": "ok",
          "values": [{"datetime": "2026-11-06", "close": "122.25000"},
                     {"datetime": "2026-11-05", "close": "121.50000"}]}
ALPHA = {"Meta Data": {"2. Symbol": "TSCO.LON"}, "Time Series (Daily)": {
    "2026-11-06": {"1. open": "1", "4. close": "3.9000"},
    "2026-11-05": {"1. open": "1", "4. close": "3.8500"},
    "2020-01-02": {"1. open": "1", "4. close": "1.0000"}}}


def test_twelvedata_and_alphavantage_sources(api, monkeypatch):
    acc = make_account(api, "Broker", type_="investment", opening="0")
    td = api.post("/api/holdings", json={
        "account_id": acc, "symbol": "VT", "name": "World ETF",
        "asset_class": "etf", "currency": "USD",
        "price_source": "twelvedata"})
    assert td.status_code == 201, td.text
    td = td.json()
    av = api.post("/api/holdings", json={
        "account_id": acc, "symbol": "TSCO", "name": "Tesco",
        "asset_class": "stock", "currency": "GBP",
        "price_source": "alphavantage", "price_symbol": "TSCO.LON"}).json()
    listed = {h["id"]: h for h in api.get("/api/holdings").json()}
    assert listed[td["id"]]["price_source"] == "twelvedata"
    calls = []

    def fake(url, timeout=20.0, headers=None):
        calls.append((url, headers or {}))
        return json.dumps(TWELVE if "twelvedata" in url else ALPHA).encode()
    monkeypatch.setattr(prices, "_get", fake)
    res = api.post("/api/prices/update").json()
    msgs = " ".join(e["error"] for e in res["errors"])
    assert res["updated"] == 0 and "twelvedata.com/account/api-keys" in msgs
    assert "alphavantage.co/support" in msgs and not calls
    s = api.put("/api/settings", json={
        "twelvedata_api_key": "td_KEY1234",
        "alphavantage_api_key": "AVKEY987"}).json()
    assert s["twelvedata_api_key_hint"] == "1234"
    assert s["alphavantage_api_key_set"] and s["stooq_api_key_set"] is False
    dumped = json.dumps(s)
    assert "td_KEY1234" not in dumped and "AVKEY987" not in dumped
    res = api.post("/api/prices/update").json()
    assert res["updated"] == 2 and res["new_prices"] == 4, res
    td_url, td_headers = next(c for c in calls if "twelvedata" in c[0])
    av_url = next(c[0] for c in calls if "alphavantage" in c[0])
    # Twelve Data gets its key in a header, never in the URL.
    assert "symbol=VT" in td_url and "td_KEY1234" not in td_url
    assert td_headers == {"Authorization": "apikey td_KEY1234"}
    assert "symbol=TSCO.LON" in av_url and "apikey=AVKEY987" in av_url
    rows = {p["price_date"]: p for p in
            api.get(f"/api/holdings/{av['id']}/prices").json()}
    # only days inside the requested window are stored
    assert rows["2026-11-06"]["price"] == 3.9 and "2020-01-02" not in rows
    assert rows["2026-11-06"]["source"] == "alphavantage"


def test_twelvedata_and_alphavantage_errors(monkeypatch):
    d0, d1 = date(2026, 11, 1), date(2026, 11, 7)

    def answer(payload):
        monkeypatch.setattr(prices, "_get", lambda url, timeout=20.0,
                            headers=None: json.dumps(payload).encode())
    answer({"code": 401, "message": "**apikey** is invalid",
            "status": "error"})
    with pytest.raises(prices.PriceFetchError, match="did not accept"):
        prices.fetch_twelvedata("VT", d0, d1, "k")
    answer({"code": 403, "message": "This symbol is available starting "
            "with the Grow plan.", "status": "error"})
    with pytest.raises(prices.PriceFetchError, match="Alpha Vantage"):
        prices.fetch_twelvedata("NESN", d0, d1, "k")
    answer({"code": 429, "message": "run out of credits",
            "status": "error"})
    with pytest.raises(prices.PriceFetchError, match="8 requests a minute"):
        prices.fetch_twelvedata("VT", d0, d1, "k")
    answer({"Error Message": "Invalid API call."})
    with pytest.raises(prices.PriceFetchError, match="exchange suffix"):
        prices.fetch_alphavantage("NOPE", d0, d1, "k")
    answer({"Information": "Thank you for using Alpha Vantage! Our standard "
            "API rate limit is 25 requests per day."})
    with pytest.raises(prices.PriceFetchError, match="25 requests a day"):
        prices.fetch_alphavantage("IBM", d0, d1, "k")
    monkeypatch.setattr(prices, "_get", lambda url, timeout=20.0,
                        headers=None: b"<html>down</html>")
    with pytest.raises(prices.PriceFetchError, match="unreadable"):
        prices.fetch_alphavantage("IBM", d0, d1, "k")


def test_coingecko_parsing(monkeypatch):
    payload = {"prices": [[1762300800000, 90000.0], [1762387200000, 91000.5]]}
    monkeypatch.setattr(prices, "_get",
                        lambda url, timeout=20.0: json.dumps(payload).encode())
    out = prices.fetch_coingecko("bitcoin", "CHF", 30)
    assert list(out.values()) == [90000.0, 91000.5]


# --- reports -----------------------------------------------------------------
def test_reports_and_exports(api):
    acc = make_account(api)
    _history(api, acc)
    api.post("/api/transactions", json={
        "account_id": acc, "txn_date": "2026-01-25", "amount": "7450",
        "description": "Salary", "category_id": cat_id(api, "Salary",
                                                       "income")})
    data = api.get("/api/reports/monthly", params={"month": "2026-01"}
                   ).json()
    assert data["income"] == 7450
    assert data["expenses"] == pytest.approx(sum(
        float(x) for x in ["54.20", "18.90", "12.60", "4.60", "15.90",
                           "12.95"]) * 5 + 54.20)
    pdf = api.get("/api/reports/monthly.pdf", params={"month": "2026-01",
                                                      "lang": "fr"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "attachment" in pdf.headers["content-disposition"]
    assert api.get("/api/reports/monthly.pdf",
                   params={"month": "2026-13"}).status_code == 422
    xlsx = api.get("/api/export/workbook.xlsx")
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert {"Transactions", "Accounts", "Holdings"} <= set(wb.sheetnames)
    assert wb["Transactions"].max_row == 38
    csv = api.get("/api/export/transactions.csv").content
    assert csv.startswith("﻿".encode()) and b"amount_base" in csv
    nw = api.get("/api/reports/net-worth", params={"months": 6}).json()
    assert len(nw["points"]) >= 6 and "change" in nw["points"][-1]


def test_transactions_without_payee_do_not_break_analysis(api):
    """A hand-entered expense without merchant must not fail any report."""
    from datetime import date, timedelta

    acc = make_account(api, opening_date="2025-01-01")
    when = (date.today() - timedelta(days=3)).isoformat()
    for i in range(4):
        r = api.post("/api/transactions", json={
            "account_id": acc, "txn_date": when,
            "amount": str(-900 - i), "description": f"Cash withdrawal {i}"})
        assert r.status_code == 201 and r.json()["merchant"] is None
    # one row with a payee makes pandas infer its string dtype (NaN gaps)
    api.post("/api/transactions", json={
        "account_id": acc, "txn_date": when, "amount": "-5",
        "description": "Coffee", "merchant": "Bakery"})
    assert api.get("/api/insights").status_code == 200
    month = date.today().strftime("%Y-%m")
    rep = api.get("/api/reports/monthly", params={"month": month})
    assert rep.status_code == 200, rep.text
    assert rep.json()["largest"][0]["description"].startswith("Cash")
    csv = api.get("/api/export/transactions.csv")
    assert csv.status_code == 200 and "nan" not in csv.text.lower()
