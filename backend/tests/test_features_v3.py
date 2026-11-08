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
    res = api.post("/api/prices/update").json()
    assert res["updated"] == 1 and res["new_prices"] == 1
    assert "s=vt.us" in calls[0]
    rows = {p["price_date"]: p for p in
            api.get(f"/api/holdings/{h}/prices").json()}
    assert rows["2026-11-06"]["price"] == 999
    assert rows["2026-11-05"]["source"] == "stooq"


def test_price_update_reports_errors(api, monkeypatch):
    _portfolio(api)
    monkeypatch.setattr(prices, "_get", lambda url, timeout=20.0: b"No data")
    res = api.post("/api/prices/update").json()
    assert res["updated"] == 0 and "vt.us" in res["errors"][0]["error"]


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
