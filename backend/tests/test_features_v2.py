"""Tests for v0.2 features: refunds, presets, rate download, backups."""
import json
from datetime import date

import pytest
from conftest import cat_id, make_account

from app.services import fx_fetch


def test_budget_progress_never_negative(api):
    chk = make_account(api)
    clothing = cat_id(api, "Clothing")
    api.post("/api/budgets", json={"category_id": clothing,
                                   "monthly_amount": "2000"})
    api.post("/api/transactions", json={
        "account_id": chk, "txn_date": date.today().isoformat(),
        "amount": "910", "category_id": clothing, "description": "refund"})
    item = api.get("/api/budgets/status").json()["items"][0]
    assert item["spent"] == -910 and item["pct"] == 0
    assert item["projected"] == 0 and item["status"] == "ok"


CSV_POSITIVE = ("Date,Description,Amount\n01.10.2026,Shop,45.60\n"
                "02.10.2026,Cafe,4.50\n03.10.2026,Rent,1850.00\n")


def test_presets_and_positive_hint(api):
    acc = make_account(api)
    files = {"file": ("b.csv", CSV_POSITIVE.encode(), "text/csv")}
    prev = api.post("/api/import/preview", files=files).json()
    assert prev["guess"]["mostly_positive"] is True
    assert prev["preset"] is None
    mapping = {"account_id": acc, "date_column": "Date",
               "description_column": "Description", "amount_column": "Amount",
               "invert_sign": True}
    res = api.post("/api/import/commit", files=files, data={
        "mapping": json.dumps(mapping), "save_preset": "My Bank"}).json()
    assert res["rows_imported"] == 3 and res["preset"] == "My Bank"
    txns = api.get("/api/transactions").json()["items"]
    assert all(t["amount"] < 0 for t in txns)
    again = api.post("/api/import/preview", files=files).json()
    assert again["preset"]["name"] == "My Bank"
    assert again["preset"]["mapping"]["invert_sign"] is True
    presets = api.get("/api/import/presets").json()
    assert [p["name"] for p in presets] == ["My Bank"]
    assert api.delete(f"/api/import/presets/{presets[0]['id']}"
                      ).status_code == 204


def _fake_tables(calls):
    def fake(url, timeout=15.0):
        calls.append(url)
        if "jsdelivr" in url and "latest" in url:
            raise OSError("primary down")       # exercise the fallback
        day = url.split("currency-api@")[-1].split("/")[0] \
            if "jsdelivr" in url else url.split("//")[1].split(".")[0]
        day = date.today().isoformat() if day == "latest" else day
        return {"date": day, "chf": {"eur": 1.07, "mad": 11.2, "usd": 1.25}}
    return fake


def test_rate_download_with_fallback_and_backfill(api, monkeypatch):
    calls = []
    monkeypatch.setattr(fx_fetch, "_get_json", _fake_tables(calls))
    make_account(api, "EUR", "EUR", "cash", "100")
    make_account(api, "MAD", "MAD", "cash", "1120")
    api.post("/api/fx-rates", json={"rate_date": date.today().isoformat(),
                                    "from_currency": "CHF",
                                    "to_currency": "EUR", "rate": "1.00"})
    res = api.post("/api/fx-rates/fetch").json()
    assert set(res["currencies"]) == {"EUR", "MAD"} and not res["missing"]
    assert any("pages.dev" in c for c in calls)
    rates = api.get("/api/fx-rates").json()
    manual = [r for r in rates if r["source"] == "manual"]
    assert manual and manual[0]["rate"] == 1.0      # never overwritten
    accs = {a["name"]: a for a in api.get("/api/accounts").json()}
    assert accs["MAD"]["balance_base"] == pytest.approx(100.0)
    s = api.get("/api/settings").json()
    assert s["fx_auto_update"] is True
    assert s["fx_last_update"] == date.today().isoformat()
    api.put("/api/settings", json={"base_currency": "CHF",
                                   "fx_auto_update": False})
    assert api.get("/api/settings").json()["fx_auto_update"] is False


def test_rate_download_offline_reports_error(api, monkeypatch):
    def offline(url, timeout=15.0):
        raise OSError("no network")
    monkeypatch.setattr(fx_fetch, "_get_json", offline)
    make_account(api, "EUR", "EUR", "cash", "100")
    r = api.post("/api/fx-rates/fetch")
    assert r.status_code == 502 and "manually" in r.json()["detail"]


def test_backup_and_restore(api):
    make_account(api, "Keep me")
    b = api.post("/api/backups").json()
    assert b["kind"] == "manual" and b["size"] > 0
    acc = make_account(api, "Added after backup")
    assert len(api.get("/api/accounts").json()) == 2
    r = api.post(f"/api/backups/{b['name']}/restore").json()
    assert r["safety_backup"].startswith("pfi-pre-restore-")
    names = [a["name"] for a in api.get("/api/accounts").json()]
    assert names == ["Keep me"]
    assert acc not in [a["id"] for a in api.get("/api/accounts").json()]
    listing = api.get("/api/backups").json()
    assert listing["available"] and len(listing["backups"]) >= 2
    dl = api.get(f"/api/backups/{b['name']}/download")
    assert dl.status_code == 200 and dl.content.startswith(b"PK")
    up = api.post("/api/backups/upload", files={
        "file": ("x.pfibak", dl.content, "application/octet-stream")}).json()
    assert up["name"].startswith("pfi-uploaded-")
    assert up["name"].endswith(".pfibak")
    bad = api.post("/api/backups/upload", files={
        "file": ("x.dump", b"hello", "application/octet-stream")})
    assert bad.status_code == 422
    assert api.post("/api/backups/..%2F..%2Fsecret/restore"
                    ).status_code == 404
