"""0.5.1: testing a backup and the one-time Store rating prompt."""
import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import update

from app.db import SessionLocal
from app.models import SchemaVersion
from app.services import backup as bk
from app.services import rating
from conftest import make_account

DATA = Path(os.environ["PFI_DATA_DIR"])


@pytest.fixture(autouse=True)
def plain_backups():
    bk.save_config(DATA, None, False, clear_password=True)
    yield
    bk.save_config(DATA, None, False, clear_password=True)


def add(api, acc, day, amount, desc="x"):
    r = api.post("/api/transactions", json={
        "account_id": acc, "txn_date": day, "amount": amount,
        "description": desc})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- testing a backup --------------------------------------------------------
def test_fresh_backup_matches_live_data(api):
    acc = make_account(api, opening="100")
    savings = make_account(api, "Savings", type_="savings", opening="0")
    for d in range(1, 11):
        add(api, acc, f"2026-03-{d:02d}", "-12.34")
    add(api, savings, "2026-03-05", "500.00")
    name = api.post("/api/backups").json()["name"]
    r = api.post(f"/api/backups/{name}/test")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["matches"] is True
    assert out["transactions_backup"] == out["transactions_live"] == 11
    assert out["sampled"] == 11 and out["sample_mismatches"] == 0
    balances = {a["name"]: a["backup_balance"] for a in out["accounts"]}
    assert balances == {"Checking": "-23.40", "Savings": "500.00"}
    assert all(a["same"] for a in out["accounts"])


def test_changes_after_the_backup_are_reported(api):
    acc = make_account(api, opening="0")
    first = add(api, acc, "2026-04-01", "-10.00", "coffee")
    name = api.post("/api/backups").json()["name"]
    add(api, acc, "2026-04-02", "-5.00", "tea")
    api.patch(f"/api/transactions/{first}", json={"description": "lunch"})
    make_account(api, "New card", type_="credit_card", opening="0")
    out = api.post(f"/api/backups/{name}/test").json()
    assert out["matches"] is False
    assert (out["transactions_backup"], out["transactions_live"]) == (1, 2)
    assert out["sample_mismatches"] == 1
    rows = {a["name"]: a for a in out["accounts"]}
    assert rows["Checking"]["backup_balance"] == "-10.00"
    assert rows["Checking"]["live_balance"] == "-15.00"
    assert rows["New card"]["backup_count"] is None
    assert rows["New card"]["live_count"] == 0


def test_encrypted_backup_needs_its_password(api, tmp_path):
    make_account(api)
    api.put("/api/backups/settings", json={
        "encrypt": True, "password": "correct horse"})
    name = api.post("/api/backups").json()["name"]
    api.put("/api/backups/settings", json={"clear_password": True})
    locked = api.post(f"/api/backups/{name}/test")
    assert locked.status_code == 423
    ok = api.post(f"/api/backups/{name}/test",
                  json={"password": "correct horse"})
    assert ok.status_code == 200 and ok.json()["matches"] is True


def test_damaged_backup_is_rejected(api):
    make_account(api)
    b = api.post("/api/backups").json()
    path = Path(b["folder"]) / b["name"]
    data = bytearray(path.read_bytes())
    data[len(data) // 2:len(data) // 2 + 64] = b"\0" * 64
    path.write_bytes(bytes(data))
    r = api.post(f"/api/backups/{b['name']}/test")
    assert r.status_code == 422
    assert "damaged" in r.json()["detail"] or "not a PFI" in \
        r.json()["detail"]
    assert api.post("/api/backups/pfi-manual-20990101-000000.pfibak/test"
                    ).status_code == 404


def test_testing_does_not_change_live_data(api):
    acc = make_account(api, opening="0")
    add(api, acc, "2026-05-01", "-1.00")
    name = api.post("/api/backups").json()["name"]
    before = api.get("/api/transactions").json()["items"]
    api.post(f"/api/backups/{name}/test")
    assert api.get("/api/transactions").json()["items"] == before
    leftovers = [p for p in DATA.iterdir() if p.name.startswith("pfi-test-")]
    assert leftovers == []


# --- rating prompt -----------------------------------------------------------
def _age_database(days: int) -> None:
    with SessionLocal() as db:
        db.execute(update(SchemaVersion).values(
            applied_at=date.today() - timedelta(days=days)))
        db.commit()


def test_rating_waits_for_use_and_data(api):
    _age_database(0)
    acc = make_account(api, opening="0")
    for d in range(1, 21):
        add(api, acc, f"2026-06-{d:02d}", "-1.00")
    assert api.get("/api/rating").json()["due"] is False   # too new
    _age_database(rating.MIN_DAYS)
    st = api.get("/api/rating").json()
    assert st["due"] is True and st["transactions"] == 20
    first = api.get("/api/transactions").json()["items"][0]["id"]
    api.delete(f"/api/transactions/{first}")
    assert api.get("/api/rating").json()["due"] is False   # 19 left


def test_demo_transactions_do_not_count(api):
    _age_database(60)
    assert api.post("/api/demo").status_code == 200
    st = api.get("/api/rating").json()
    assert st["transactions"] == 0 and st["due"] is False
    api.delete("/api/demo")


def test_rating_answers_are_final_or_snoozed(api):
    _age_database(60)
    acc = make_account(api, opening="0")
    for d in range(1, 21):
        add(api, acc, f"2026-07-{d:02d}", "-1.00")
    day = date.today()
    with SessionLocal() as db:
        assert rating.record(db, "later", day) == f"later:{day.isoformat()}"
        assert rating.status(db, day + timedelta(days=19))["due"] is False
        assert rating.status(db, day + timedelta(days=30))["due"] is True
        assert rating.record(db, "later", day + timedelta(days=30)) \
            == "dismissed"
        assert rating.status(db, day + timedelta(days=200))["due"] is False
    for final in ("rated", "declined"):
        r = api.post("/api/rating", json={"outcome": final})
        assert r.status_code == 200
        assert r.json()["state"] == final and r.json()["due"] is False
    bad = api.post("/api/rating", json={"outcome": "maybe"})
    assert bad.status_code == 422 and "Unknown rating answer" in \
        bad.json()["detail"]
    with SessionLocal() as db:
        rating.prefs.put(db, rating.KEY, "")
        db.commit()
