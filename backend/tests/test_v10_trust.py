"""1.0 trust features: data checks, update check, upgrades from old DBs."""
import gzip
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app import __version__
from app.db import SessionLocal, get_engine
from app.migrations import MIGRATIONS
from app.services import updates

FIXTURES = Path(__file__).parent / "fixtures" / "old_db"


def _acc(api, name, typ="checking"):
    r = api.post("/api/accounts", json={
        "name": name, "type": typ, "currency": "CHF",
        "opening_date": "2026-01-01"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_clean_database_has_no_findings(api):
    a, b = _acc(api, "A"), _acc(api, "B")
    api.post("/api/transfers", json={
        "from_account_id": a, "to_account_id": b, "amount": "10",
        "txn_date": "2026-02-01"})
    r = api.get("/api/system/check").json()
    assert r["ok"] is True and r["issues"] == [] and r["checked"] == 2


def test_check_finds_and_fixes_problems(api):
    a, b = _acc(api, "A"), _acc(api, "B")
    legs = api.post("/api/transfers", json={
        "from_account_id": a, "to_account_id": b, "amount": "10",
        "txn_date": "2026-02-01"}).json()
    leg_ids = [leg["id"] for leg in (legs["legs"] if "legs" in legs
                                     else legs)]
    salary = next(c["id"] for c in api.get("/api/categories").json()
                  if c["kind"] == "income")
    bad = api.post("/api/transactions", json={
        "account_id": a, "txn_date": "2026-02-02", "amount": "-5",
        "kind": "expense", "description": "coffee"}).json()["id"]
    with get_engine().begin() as conn:
        # The API refuses this, but older versions or a sync could not.
        conn.execute(text("UPDATE transactions SET category_id = :c "
                          "WHERE id = :i"), {"c": salary, "i": bad})
        # One side of the transfer lost, and a second one-sided transfer.
        conn.execute(text("DELETE FROM transactions WHERE id = :i"),
                     {"i": leg_ids[1]})
        conn.execute(text(
            "INSERT INTO transactions (account_id, txn_date, amount, kind, "
            "description, transfer_group, cleared, reviewed) "
            "VALUES (:a, '2026-02-03', 700, 'transfer', 'x', NULL, 0, 1)"),
            {"a": a})
    r = api.get("/api/system/check").json()
    codes = {i["code"]: i for i in r["issues"]}
    assert r["ok"] is False
    assert codes["transfer_legs"]["transaction_ids"] == [leg_ids[0]]
    assert codes["transfer_orphan"]["count"] == 1
    assert codes["category_kind"]["transaction_ids"] == [bad]
    assert codes["category_kind"]["fixable"] is True
    assert all(i["fix"] for i in r["issues"])
    no = api.post("/api/system/check/fix", json={"code": "transfer_legs"})
    assert no.status_code == 422 and "decision" in no.json()["detail"]
    done = api.post("/api/system/check/fix",
                    json={"code": "category_kind"}).json()
    assert done["changed"] == 1
    assert "category_kind" not in {i["code"] for i in done["issues"]}
    with get_engine().connect() as conn:
        cat, reviewed = conn.execute(text(
            "SELECT category_id, reviewed FROM transactions WHERE id = :i"),
            {"i": bad}).one()
    assert cat is None and not reviewed


def test_version_compare():
    assert updates.parse_version("v1.0.0") > updates.parse_version("0.9.0")
    assert updates.parse_version("1.10.0") > updates.parse_version("1.9.9")
    assert updates.parse_version("v1.0.0-beta") == (1, 0, 0)


def test_update_status_caches_and_reports(api):
    calls = []

    def fake():
        calls.append(1)
        return {"version": "99.0.0", "url": "https://example.org/r",
                "notes": "New things"}

    with SessionLocal() as db:
        first = updates.status(db, force=True, fetch=fake)
        again = updates.status(db, fetch=fake)
    assert first["newer"] is True and first["latest"] == "99.0.0"
    assert first["current"] == __version__
    assert again["latest"] == "99.0.0" and len(calls) == 1

    def offline():
        raise OSError("no network")

    with SessionLocal() as db:
        out = updates.status(db, force=True, fetch=offline)
    assert out["newer"] is False and "internet" in out["error"]


def test_update_check_can_be_turned_off(api):
    api.put("/api/settings", json={"update_check": False})
    with SessionLocal() as db:
        out = updates.status(db, fetch=lambda: pytest.fail("fetched"))
    assert out["enabled"] is False and out["latest"] is None
    api.put("/api/settings", json={"update_check": True})


def test_setup_done_setting(api):
    assert api.get("/api/settings").json()["setup_done"] is False
    api.put("/api/settings", json={"setup_done": True})
    assert api.get("/api/settings").json()["setup_done"] is True


UPGRADE = """
import json, sqlite3, sys
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    out = {
        "health": c.get("/api/health").status_code,
        "summary": c.get("/api/analytics/summary").status_code,
        "months": c.get("/api/analytics/months").status_code,
        "dashboard": c.get("/api/analytics/dashboard").status_code,
        "check": c.get("/api/system/check").json(),
        "txns": c.get("/api/transactions", params={"limit": 1}).status_code,
    }
db = sys.argv[1]
con = sqlite3.connect(db)
out["version"] = con.execute("select max(version) from schema_version"
                             ).fetchone()[0]
out["count"] = con.execute("select count(*) from transactions").fetchone()[0]
print(json.dumps(out))
"""


@pytest.mark.parametrize("fixture", sorted(p.name for p in
                                           FIXTURES.glob("*.sqlite.gz")))
def test_old_databases_upgrade_cleanly(fixture, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    db = data / "pfi.sqlite"
    with gzip.open(FIXTURES / fixture) as src, open(db, "wb") as dst:
        shutil.copyfileobj(src, dst)
    import sqlite3
    before = sqlite3.connect(db).execute(
        "select count(*) from transactions").fetchone()[0]
    env = dict(os.environ, PFI_DATA_DIR=str(data))
    run = subprocess.run([sys.executable, "-c", UPGRADE, str(db)],
                         cwd=Path(__file__).parents[1], env=env,
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["version"] == MIGRATIONS[-1][0]
    assert out["count"] == before > 0
    for key in ("health", "summary", "months", "dashboard", "txns"):
        assert out[key] == 200, (key, out)
    errors = [i for i in out["check"]["issues"] if i["level"] == "error"]
    assert errors == [], errors
