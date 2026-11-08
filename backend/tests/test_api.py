"""API tests against a real (embedded) PostgreSQL database."""
import json
import os
import stat
from datetime import date, timedelta
from pathlib import Path

from conftest import cat_id, make_account

from app.security import TokenMiddleware


def test_health_settings_and_seed(api):
    assert api.get("/api/health").json()["status"] == "ok"
    s = api.get("/api/settings").json()
    assert s["base_currency"] == "CHF"
    cats = api.get("/api/categories").json()
    rent = next(c for c in cats if c["name"] == "Rent")
    assert rent["full_name"] == "Housing › Rent"


def test_transactions_balances_and_transfers(api):
    chk = make_account(api)
    sav = make_account(api, "Savings", type_="savings", opening="0")
    r = api.post("/api/transactions", json={
        "account_id": chk, "txn_date": "2026-02-01", "amount": "-1850",
        "description": "Rent", "category_id": cat_id(api, "Rent")})
    assert r.status_code == 201 and r.json()["kind"] == "expense"
    assert r.json()["amount"] == -1850.0
    api.post("/api/transactions", json={
        "account_id": chk, "txn_date": "2026-02-25", "amount": "6500",
        "description": "Salary"})
    legs = api.post("/api/transfers", json={
        "from_account_id": chk, "to_account_id": sav,
        "txn_date": "2026-02-26", "amount": "800"}).json()
    assert [leg["amount"] for leg in legs] == [-800, 800]
    accs = {a["name"]: a for a in api.get("/api/accounts").json()}
    assert accs["Checking"]["balance"] == 1000 - 1850 + 6500 - 800
    assert accs["Savings"]["balance_base"] == 800
    summary = api.get("/api/analytics/summary", params={
        "start": "2026-01-01", "end": "2026-12-31"}).json()
    assert summary["income"] == 6500 and summary["expenses"] == 1850
    assert summary["net_worth"] == 1000 - 1850 + 6500
    assert api.delete(f"/api/transactions/{legs[0]['id']}").status_code \
        == 204
    left = api.get("/api/transactions", params={"kind": "transfer"})
    assert left.json()["total"] == 0
    bad = api.patch(f"/api/transactions/{r.json()['id']}",
                    json={"amount": "0"})
    assert bad.status_code == 422


def test_multi_currency_and_missing_rates(api):
    make_account(api, "EUR Cash", "EUR", "cash", "100")
    missing = api.get("/api/fx-rates/missing").json()
    assert missing["missing"] == ["EUR"]
    assert api.get("/api/analytics/summary").json()["missing_fx"] == ["EUR"]
    api.post("/api/fx-rates", json={"rate_date": "2026-01-01",
                                    "from_currency": "eur",
                                    "to_currency": "CHF", "rate": "0.94"})
    accs = api.get("/api/accounts").json()
    assert accs[0]["balance_base"] == 94.0
    assert api.get("/api/fx-rates/missing").json()["missing"] == []


SWISS_CSV = """Kontoauszug Musterbank
Konto: CH00 0000 0000
Datum;Buchungstext;Belastung;Gutschrift
01.03.2026;MIGROS BERN 123;45.60;
02.03.2026;Lohn Universität;;6'500.00
02.03.2026;Coffee;4.50;
02.03.2026;Coffee;4.50;
03.03.2026;Broken row;abc;
"""


def test_csv_import_preview_commit_dedupe(api, client):
    acc = make_account(api)
    api.post("/api/rules", json={"pattern": "migros",
                                 "category_id": cat_id(api, "Groceries")})
    files = {"file": ("bank.csv", SWISS_CSV.encode("cp1252"), "text/csv")}
    prev = api.post("/api/import/preview", params={"skip_rows": 2},
                    files=files).json()
    assert prev["delimiter"] == ";" and prev["encoding"] == "cp1252"
    assert prev["guess"]["date_column"] == "Datum"
    assert prev["guess"]["debit_column"] == "Belastung"
    mapping = {"account_id": acc, "date_column": "Datum",
               "description_column": "Buchungstext",
               "debit_column": "Belastung", "credit_column": "Gutschrift",
               "skip_rows": 2, "dayfirst": True}
    res = api.post("/api/import/commit", files=files,
                   data={"mapping": json.dumps(mapping)}).json()
    assert res["rows_imported"] == 4 and res["rows_failed"] == 1
    assert res["categorized"] == 1 and "Line 8" in res["errors"][0]
    again = api.post("/api/import/commit", files=files,
                     data={"mapping": json.dumps(mapping)}).json()
    assert again["rows_imported"] == 0 and again["rows_duplicate"] == 4
    txns = api.get("/api/transactions", params={"account_id": acc}).json()
    by_text = {t["description"]: t for t in txns["items"]}
    assert by_text["Lohn Universität"]["amount"] == 6500.0
    assert by_text["MIGROS BERN 123"]["category_name"] == \
        "Food › Groceries"
    archived = list(Path(os.environ["PFI_DATA_DIR"], "imports").iterdir())
    assert archived and not archived[0].stat().st_mode & stat.S_IWUSR
    assert archived[0].read_bytes() == SWISS_CSV.encode("cp1252")
    batch = api.get("/api/import/batches").json()[-1]
    assert api.delete(f"/api/import/batches/{batch['id']}").json()[
        "removed"] == 4


def test_investments_cash_legs_and_valuation(api):
    inv = make_account(api, "Broker", type_="investment", opening="5000")
    chk = make_account(api, "Chk2")
    bad = api.post("/api/holdings", json={
        "account_id": chk, "symbol": "x", "name": "X",
        "asset_class": "stock", "currency": "CHF"})
    assert bad.status_code == 422
    hid = api.post("/api/holdings", json={
        "account_id": inv, "symbol": "vwrl", "name": "All-World ETF",
        "asset_class": "etf", "currency": "CHF"}).json()["id"]
    url = f"/api/holdings/{hid}/trades"
    api.post(url, json={"trade_date": "2026-01-10", "trade_type": "buy",
                        "quantity": "10", "price": "100", "fees": "5"})
    api.post(url, json={"trade_date": "2026-02-10", "trade_type":
                        "dividend", "cash_amount": "12"})
    over = api.post(url, json={"trade_date": "2026-03-01",
                               "trade_type": "sell", "quantity": "50",
                               "price": "100"})
    assert over.status_code == 422
    api.post(f"/api/holdings/{hid}/prices",
             json={"price_date": "2026-03-01", "price": "110"})
    h = api.get("/api/holdings").json()[0]
    assert h["symbol"] == "VWRL" and h["market_value"] == 1100
    assert h["unrealized_pl"] == 1100 - 1005 and h["dividends"] == 12
    acc = next(a for a in api.get("/api/accounts").json()
               if a["id"] == inv)
    assert acc["balance"] == 5000 - 1005 + 12
    assert acc["holdings_base"] == 1100
    summary = api.get("/api/analytics/summary").json()
    assert summary["investments"] == 5000 - 1005 + 12 + 1100


def test_budgets_goals_recurring(api):
    chk = make_account(api)
    today = date.today()
    food = cat_id(api, "Food")
    api.post("/api/budgets", json={"category_id": food,
                                   "monthly_amount": "500"})
    dup = api.post("/api/budgets", json={"category_id": food,
                                         "monthly_amount": "1"})
    assert dup.status_code == 409
    api.post("/api/transactions", json={
        "account_id": chk, "txn_date": today.isoformat(),
        "amount": "-600", "category_id": cat_id(api, "Groceries")})
    status = api.get("/api/budgets/status").json()
    assert status["items"][0]["spent"] == 600
    assert status["items"][0]["status"] == "over"
    goal = api.post("/api/goals", json={
        "name": "Trip", "target_amount": "2000", "currency": "CHF",
        "target_date": (today + timedelta(days=365)).isoformat(),
        "account_id": chk}).json()
    assert goal["saved_amount"] == 400 and goal["progress"] == 0.2
    assert goal["status"] in ("behind", "on_track")
    rec = api.post("/api/recurring", json={
        "name": "Rent", "account_id": chk, "amount": "-1850",
        "frequency": "monthly", "start_date": "2026-01-31",
        "category_id": cat_id(api, "Rent")}).json()
    assert rec["next_date"] >= today.isoformat()


def test_forecast_reproducible(api):
    chk = make_account(api, opening="3000",
                       opening_date=(date.today() - timedelta(days=200))
                       .isoformat())
    fc = api.get("/api/forecast", params={"horizon_days": 30}).json()
    assert fc["lookback_days_used"] == 0 and fc["notes"]
    for i in range(120):
        api.post("/api/transactions", json={
            "account_id": chk, "amount": "-20", "description": "food",
            "txn_date": (date.today() - timedelta(days=i)).isoformat()})
    api.post("/api/recurring", json={
        "name": "Salary", "account_id": chk, "amount": "3000",
        "frequency": "monthly", "start_date": "2026-01-25"})
    a = api.get("/api/forecast", params={"horizon_days": 60}).json()
    b = api.get("/api/forecast", params={"horizon_days": 60}).json()
    assert a["p50"] == b["p50"] and len(a["dates"]) == 60
    assert a["discretionary_daily_mean"] < 0
    assert 0 <= a["prob_below_threshold"] <= 1
    assert a["scheduled_total"] in (6000, 3000, 9000)
    assert a["figure"]["data"]


def test_demo_dashboard_charts_insights(api):
    r = api.post("/api/demo")
    assert r.status_code == 200 and r.json()["transactions"] > 500
    assert api.post("/api/demo").status_code == 409
    dash = api.get("/api/analytics/dashboard").json()
    assert dash["summary"]["income"] > 0
    for name in ("monthly_cashflow", "savings_rate", "category_breakdown",
                 "category_trend", "weekday_heatmap", "top_merchants",
                 "budget_vs_actual", "net_worth", "allocation"):
        fig = api.get(f"/api/analytics/charts/{name}").json()
        assert fig["data"], name
    ins = api.get("/api/insights").json()["insights"]
    assert any(i["type"] == "subscription" for i in ins)
    fc = api.get("/api/forecast").json()
    assert fc["lookback_days_used"] >= 28
    goals = api.get("/api/goals").json()
    assert {g["currency"] for g in goals} == {"CHF", "MAD"}
    assert api.delete("/api/demo").json()["removed_accounts"] == 5
    assert api.get("/api/accounts").json() == []


def test_token_middleware():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.add_middleware(TokenMiddleware, token="s3cret")

    @app.get("/api/x")
    def x():
        return {"ok": True}

    with TestClient(app) as c:
        assert c.get("/api/x").status_code == 401
        r = c.get("/auth/bootstrap", params={"token": "s3cret",
                                             "next": "//evil"},
                  follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert c.get("/api/x").json() == {"ok": True}
        assert c.get("/auth/bootstrap", params={"token": "no"}
                     ).status_code == 403


def test_forecast_does_not_double_count_recurring(api):
    """A salary that is also a recurring item contributes only its
    deviation (bonus) to the simulated discretionary flows."""
    today = date.today()
    chk = make_account(api, opening="0",
                       opening_date=(today - timedelta(days=200))
                       .isoformat())
    salary = cat_id(api, "Salary", "income")
    start = (today.replace(day=1) - timedelta(days=150)).replace(day=1)
    api.post("/api/recurring", json={
        "name": "Salary", "account_id": chk, "amount": "6000",
        "category_id": salary, "frequency": "monthly",
        "start_date": start.isoformat()})
    day, bonus_paid = start, False
    while day <= today:
        amount = "7200" if not bonus_paid else "6000"
        bonus_paid = True
        api.post("/api/transactions", json={
            "account_id": chk, "txn_date": (day + timedelta(days=2))
            .isoformat(), "amount": amount, "category_id": salary})
        day = (day + timedelta(days=32)).replace(day=1)
    for i in range(150):
        api.post("/api/transactions", json={
            "account_id": chk, "amount": "-10", "description": "x",
            "txn_date": (today - timedelta(days=i)).isoformat()})
    fc = api.get("/api/forecast", params={"lookback_days": 180}).json()
    window = fc["lookback_days_used"]
    expected = (-10 * 150 + 1200) / window
    assert abs(fc["discretionary_daily_mean"] - expected) < 1e-6


def test_static_ui_mime_types(tmp_path):
    """UI assets must be served with JavaScript/CSS MIME types (Windows
    registries often map .js to text/plain, which blanks the WebView)."""
    import mimetypes
    mimetypes.add_type("text/plain", ".js")   # simulate a bad registry
    from importlib import reload
    import app.main as main
    reload(main)
    assert mimetypes.guess_type("x.js")[0] == "text/javascript"
    assert mimetypes.guess_type("x.css")[0] == "text/css"
