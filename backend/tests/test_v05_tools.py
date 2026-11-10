"""0.5: bulk edit, reconciliation, debt payoff, spending calendar."""
import re
from datetime import date

from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.migrations import MIGRATIONS, run_migrations
from app.services import planning_tools as pt
from conftest import cat_id, make_account


def txn(api, acc, day, amount, desc="x", cat=None):
    r = api.post("/api/transactions", json={
        "account_id": acc, "txn_date": day, "amount": amount,
        "description": desc, "category_id": cat})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_bulk_update_and_delete(api):
    acc = make_account(api)
    other = make_account(api, "Savings", type_="savings")
    groceries = cat_id(api, "Groceries")
    ids = [txn(api, acc, "2026-03-0%d" % d, -10 * d) for d in (1, 2, 3)]
    split = txn(api, acc, "2026-03-04", -40)
    assert api.put(f"/api/transactions/{split}/splits", json={"parts": [
        {"category_id": groceries, "amount": -30},
        {"category_id": cat_id(api, "Home & Garden"), "amount": -10}]}
    ).status_code == 200
    transfer = api.post("/api/transfers", json={
        "from_account_id": acc, "to_account_id": other,
        "txn_date": "2026-03-05", "amount": 50}).json()[0]["id"]
    r = api.post("/api/transactions/bulk", json={
        "ids": ids + [split, transfer], "category_id": groceries,
        "add_tags": ["Holiday", "Kids"], "cleared": True}).json()
    assert r["updated"] == 3 and r["skipped"] == 2
    assert r["reasons"] == {"split": 1, "transfer": 1}
    rows = {t["id"]: t for t in api.get("/api/transactions").json()["items"]}
    assert all(rows[i]["category_id"] == groceries for i in ids)
    assert all(rows[i]["tags"] == ["Holiday", "Kids"] and rows[i]["cleared"]
               for i in ids)
    r = api.post("/api/transactions/bulk", json={
        "ids": ids, "remove_tags": ["kids"], "account_id": other}).json()
    assert r["updated"] == 3
    rows = {t["id"]: t for t in api.get("/api/transactions").json()["items"]}
    assert rows[ids[0]]["tags"] == ["Holiday"]
    assert rows[ids[0]]["account_id"] == other
    assert not rows[ids[0]]["cleared"]
    r = api.post("/api/transactions/bulk", json={
        "ids": [ids[0], transfer], "action": "delete"}).json()
    assert r["deleted"] == 3
    left = {t["id"] for t in api.get("/api/transactions").json()["items"]}
    assert ids[0] not in left and transfer not in left
    assert api.post("/api/transactions/bulk", json={
        "ids": []}).status_code == 422


def test_reconcile_lock_and_undo(api):
    acc = make_account(api, opening="1000")
    a = txn(api, acc, "2026-04-01", -100)
    b = txn(api, acc, "2026-04-03", -50)
    c = txn(api, acc, "2026-04-20", 200)
    start = api.get(f"/api/accounts/{acc}/reconcile",
                    params={"statement_date": "2026-04-10"}).json()
    assert start["cleared_balance"] == 1000
    assert [t["id"] for t in start["transactions"]] == [a, b]
    bad = api.post(f"/api/accounts/{acc}/reconcile", json={
        "statement_date": "2026-04-10", "statement_balance": "850",
        "ids": [a]})
    assert bad.status_code == 422 and "50.00" in bad.json()["detail"]
    late = api.post(f"/api/accounts/{acc}/reconcile", json={
        "statement_date": "2026-04-10", "statement_balance": "1050",
        "ids": [a, c]})
    assert late.status_code == 422
    ok = api.post(f"/api/accounts/{acc}/reconcile", json={
        "statement_date": "2026-04-10", "statement_balance": "850",
        "ids": [a, b]}).json()
    assert ok["reconciled"] == 2
    locked = api.patch(f"/api/transactions/{a}", json={"amount": "-90"})
    assert locked.status_code == 409
    assert api.delete(f"/api/transactions/{a}").status_code == 409
    assert api.patch(f"/api/transactions/{a}",
                     json={"notes": "fine"}).status_code == 200
    r = api.post("/api/transactions/bulk", json={
        "ids": [a], "action": "delete"}).json()
    assert r["reasons"] == {"reconciled": 1}
    hist = api.get(f"/api/accounts/{acc}/reconciliations").json()
    assert hist[0]["statement_balance"] == 850 and hist[0]["transactions"] == 2
    nxt = api.get(f"/api/accounts/{acc}/reconcile",
                  params={"statement_date": "2026-04-30"}).json()
    assert nxt["cleared_balance"] == 850 and nxt["last"]
    assert [t["id"] for t in nxt["transactions"]] == [c]
    assert api.delete(
        f"/api/accounts/{acc}/reconciliations/latest").status_code == 200
    row = next(t for t in api.get("/api/transactions").json()["items"]
               if t["id"] == a)
    assert row["cleared"] and not row["reconciled"]
    assert api.patch(f"/api/transactions/{a}",
                     json={"amount": "-90"}).status_code == 200


def test_payoff_strategies():
    debts = [pt.Debt(1, "Card", 3000, 20, 90),
             pt.Debt(2, "Car", 8000, 5, 200),
             pt.Debt(3, "Store", 500, 10, 25)]
    ava = pt.payoff_plan(debts, 300, "avalanche")
    snow = pt.payoff_plan(debts, 300, "snowball")
    low = pt.payoff_plan(debts, 300, "minimum")
    assert ava.months and snow.months and low.months
    assert ava.interest <= snow.interest < low.interest
    assert ava.months < low.months
    assert snow.debts[0]["account_id"] == 3
    assert ava.debts[0]["account_id"] == 1
    assert abs(ava.paid - (11500 + ava.interest)) < 0.05
    never = pt.payoff_plan([pt.Debt(1, "Card", 5000, 24, 50)], 0, "minimum")
    assert never.months is None
    d = ava.to_dict(date(2026, 11, 10))
    assert d["payoff_date"].day == 1 and len(d["schedule"]) == ava.months
    assert pt.payoff_plan([], 100, "avalanche").months == 0


def test_debt_endpoints(api):
    card = make_account(api, "Visa", type_="credit_card", opening="-2000")
    loan = make_account(api, "Car loan", type_="loan", opening="-6000")
    plain = make_account(api)
    assert api.put(f"/api/debts/{plain}", json={
        "apr": 3, "min_payment": 10}).status_code == 422
    api.put(f"/api/debts/{card}", json={"apr": "19.9", "min_payment": 60})
    api.put(f"/api/debts/{loan}", json={"apr": "4.5", "min_payment": 250})
    debts = api.get("/api/debts").json()["debts"]
    assert {d["name"]: d["owed"] for d in debts} == {
        "Car loan": 6000, "Visa": 2000}
    plan = api.post("/api/debts/plan", json={"extra": 200}).json()
    assert plan["plans"]["avalanche"]["debts"][0]["name"] == "Visa"
    assert (plan["plans"]["avalanche"]["months"]
            < plan["plans"]["minimum"]["months"])


def test_calendar(api):
    acc = make_account(api, opening_date="2025-01-01")
    food = cat_id(api, "Groceries")
    txn(api, acc, "2025-06-01", -400, cat=food)
    txn(api, acc, "2026-02-02", -30, "Bakery", food)
    txn(api, acc, "2026-02-02", -20, "Coffee", food)
    txn(api, acc, "2026-02-03", -500, "Laptop")
    txn(api, acc, "2026-02-25", 3000, "Salary",
        cat_id(api, "Salary", "income"))
    cal = api.get("/api/analytics/calendar", params={"year": 2026}).json()
    days = {d["date"]: d for d in cal["days"]}
    assert days["2026-02-02"]["spend"] == 50
    assert days["2026-02-25"]["income"] == 3000
    assert cal["max_spend"] == 500 and cal["first_year"] == 2025
    rv = cal["review"]
    assert rv["spend"] == 550 and rv["income"] == 3000 and rv["net"] == 2450
    assert rv["biggest"]["spend"] == 500
    assert rv["top_categories"][0]["category"] == "Uncategorized"
    assert rv["previous"]["spend"] == 400
    assert rv["months"][1]["spend"] == 550 and rv["highest_month"] == 2
    review = pt.calendar(*_frames(), 2026, today=date(2026, 2, 10))["review"]
    assert review["days"] == 41 and review["no_spend_days"] == 39


def _frames():
    import pandas as pd
    exp = pd.DataFrame({
        "id": [1, 2], "txn_date": [date(2026, 2, 2), date(2026, 2, 3)],
        "spend": [50.0, 500.0], "top_category": ["Food", None],
        "description": ["a", "b"], "merchant": [None, None]})
    inc = pd.DataFrame({"txn_date": [], "amount_base": []})
    return exp, inc


def test_migration_from_v04(tmp_path):
    from sqlalchemy.schema import CreateTable
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite'}")
    new = ("transactions", "reconciliations", "debt_terms")
    with engine.begin() as conn:
        Base.metadata.create_all(conn, tables=[
            t for t in Base.metadata.sorted_tables if t.name not in new])
        ddl = str(CreateTable(Base.metadata.tables["transactions"])
                  .compile(engine))
        ddl = "\n".join(line for line in ddl.splitlines()
                        if "cleared" not in line
                        and "reconciliation" not in line)
        conn.execute(text(re.sub(r",\s*\n\)", "\n)", ddl)))
        for version, name, _ in MIGRATIONS[:4]:
            conn.execute(text("INSERT INTO schema_version (version, name) "
                              "VALUES (:v, :n)"), {"v": version, "n": name})
    assert run_migrations(engine) == 5
    cols = {c["name"] for c in inspect(engine).get_columns("transactions")}
    assert {"cleared", "reconciliation_id"} <= cols
    assert "debt_terms" in inspect(engine).get_table_names()
    with engine.begin() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
