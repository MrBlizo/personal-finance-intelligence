"""0.6: envelopes, period budgets, IOUs, loans, review, search, reports,
YNAB import and sync-ready rows."""
import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text

from app.db import Base, SessionLocal
from app.migrations import MIGRATIONS, run_migrations
from app.models import SYNCED_TABLES
from app.services import budgeting as bg
from app.services import envelope as env
from conftest import cat_id, make_account

M1, M2 = "2026-03", "2026-04"


def add(api, acc, day, amount, desc="x", cat=None, merchant=None):
    r = api.post("/api/transactions", json={
        "account_id": acc, "txn_date": day, "amount": amount,
        "description": desc, "category_id": cat, "merchant": merchant})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def row(view, name):
    return next(i for g in view["groups"] for i in g["items"]
                if i["name"] == name)


# --- sync-ready rows ---------------------------------------------------------
def test_new_rows_get_uid_and_deletions_are_recorded(api):
    acc = make_account(api)
    tid = add(api, acc, "2026-03-02", "-10")
    with SessionLocal() as db:
        uid, stamp = db.execute(text(
            "SELECT uid, updated_at FROM transactions WHERE id=:i"),
            {"i": tid}).one()
        assert uid and len(uid) == 32
        db.execute(text("INSERT INTO tags (name) VALUES ('raw')"))
        assert db.scalar(text(
            "SELECT uid FROM tags WHERE name='raw'"))
        db.execute(text("UPDATE transactions SET description='y' WHERE "
                        "id=:i"), {"i": tid})
        assert db.scalar(text("SELECT updated_at FROM transactions WHERE "
                              "id=:i"), {"i": tid}) != stamp
        db.commit()
    assert api.delete(f"/api/transactions/{tid}").status_code == 204
    with SessionLocal() as db:
        assert db.scalar(text(
            "SELECT count(*) FROM sync_tombstones WHERE uid=:u AND "
            "table_name='transactions'"), {"u": uid}) == 1


def test_migration_from_v05_fills_uids(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v05.sqlite'}")
    new = {"budget_assignments", "budget_targets", "period_budgets",
           "period_budget_categories", "ious", "iou_payments",
           "sync_tombstones"}
    with engine.begin() as conn:
        Base.metadata.create_all(conn, tables=[
            t for t in Base.metadata.sorted_tables if t.name not in new])
        for table in SYNCED_TABLES:
            if table in new:
                continue
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN uid"))
            if table != "transactions":
                conn.execute(text(
                    f"ALTER TABLE {table} DROP COLUMN updated_at"))
        conn.execute(text("ALTER TABLE categories DROP COLUMN icon"))
        conn.execute(text("ALTER TABLE transactions DROP COLUMN reviewed"))
        conn.execute(text(
            "INSERT INTO accounts (name, type, currency, opening_balance, "
            "opening_date, is_archived, is_demo) VALUES "
            "('Old', 'checking', 'CHF', 0, '2025-01-01', 0, 0)"))
        for version, name, _ in MIGRATIONS[:5]:
            conn.execute(text("INSERT INTO schema_version (version, name) "
                              "VALUES (:v, :n)"), {"v": version, "n": name})
    assert run_migrations(engine) == MIGRATIONS[-1][0]
    with engine.begin() as conn:
        uid = conn.scalar(text("SELECT uid FROM accounts"))
        assert uid and len(uid) == 32
        cols = {c["name"] for c in inspect(conn).get_columns(
            "transactions")}
        assert {"uid", "reviewed", "updated_at"} <= cols
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


# --- envelope budgeting ------------------------------------------------------
def test_envelope_ready_to_assign_and_carry_over(api):
    acc = make_account(api, opening="1000", opening_date="2026-03-01")
    food, fun = cat_id(api, "Groceries"), cat_id(api, "Entertainment")
    assert api.put(f"/api/envelopes/{M1}/{food}",
                   json={"amount": "300"}).status_code == 200
    api.put(f"/api/envelopes/{M1}/{fun}", json={"amount": "50"})
    add(api, acc, "2026-03-05", "-100", cat=food)
    add(api, acc, "2026-03-06", "-80", cat=fun)
    add(api, acc, "2026-03-07", "-10")
    v = api.get(f"/api/envelopes?month={M1}").json()
    assert row(v, "Groceries")["available"] == 200
    assert row(v, "Entertainment")["available"] == -30
    assert row(v, "Entertainment")["status"] == "overspent"
    assert row(v, "Uncategorized")["available"] == -10
    # cash 810, envelopes 200 - 30 - 10 = 160
    assert v["ready_to_assign"] == 650
    v2 = api.get(f"/api/envelopes?month={M2}").json()
    assert row(v2, "Groceries")["carry_in"] == 200
    assert row(v2, "Entertainment")["available"] == 0
    # overspending of March is now taken from Ready to Assign
    assert v2["ready_to_assign"] == 610


def test_move_money_and_quick_assign(api):
    make_account(api, opening="1000", opening_date="2026-03-01")
    food, fun = cat_id(api, "Groceries"), cat_id(api, "Entertainment")
    api.put(f"/api/envelopes/{M1}/{food}", json={"amount": "300"})
    r = api.post("/api/envelopes/move", json={
        "month": M1, "amount": "50", "from_category_id": food,
        "to_category_id": fun})
    assert r.status_code == 200, r.text
    assert row(r.json(), "Groceries")["assigned"] == 250
    assert row(r.json(), "Entertainment")["assigned"] == 50
    assert api.put(f"/api/budget-targets/{fun}", json={
        "kind": "monthly", "amount": "120"}).status_code == 200
    v = api.get(f"/api/envelopes?month={M1}").json()
    assert row(v, "Entertainment")["shortfall"] == 70
    assert row(v, "Entertainment")["status"] == "underfunded"
    prev = api.post("/api/envelopes/quick-assign", json={
        "month": M1, "mode": "underfunded"}).json()
    assert prev["total"] == 70 and not prev["applied"]
    api.post("/api/envelopes/quick-assign", json={
        "month": M1, "mode": "underfunded", "apply": True})
    v = api.get(f"/api/envelopes?month={M1}").json()
    assert row(v, "Entertainment")["status"] == "funded"
    last = api.post("/api/envelopes/quick-assign", json={
        "month": M2, "mode": "last_month", "apply": True}).json()
    names = {c["name"] for c in last["changes"]}
    assert names == {"Groceries", "Entertainment"}
    bad = api.post("/api/envelopes/move", json={
        "month": M1, "amount": "5", "from_category_id": food,
        "to_category_id": food})
    assert bad.status_code == 422
    salary = cat_id(api, "Salary", "income")
    assert api.put(f"/api/envelopes/{M1}/{salary}",
                   json={"amount": "1"}).status_code == 422


def test_target_needs():
    class T:
        def __init__(self, kind, amount, due=None):
            self.kind, self.amount, self.due_date = kind, Decimal(amount), \
                due
    m = date(2026, 3, 1)
    assert env.target_need(T("yearly", "1200"), m, Decimal(0)) == 100
    assert env.target_need(T("by_date", "600", date(2026, 8, 15)), m,
                           Decimal(0)) == 100
    assert env.target_need(T("by_date", "600", date(2026, 8, 15)), m,
                           Decimal(300)) == 50
    # March 2026 has five Mondays
    assert env.target_need(T("weekly", "10"), m, Decimal(0)) == 50


# --- period budgets ----------------------------------------------------------
def test_weekly_and_custom_budgets(api):
    acc = make_account(api)
    food = cat_id(api, "Groceries")
    today = date.today()
    add(api, acc, today.isoformat(), "-40", cat=food)
    add(api, acc, (today - timedelta(days=7)).isoformat(), "-25", cat=food)
    r = api.post("/api/period-budgets", json={
        "name": "Food week", "amount": "100", "period": "weekly",
        "start_date": (today - timedelta(days=21)).isoformat(),
        "category_ids": [cat_id(api, "Food")]})
    assert r.status_code == 201, r.text
    bad = api.post("/api/period-budgets", json={
        "name": "Trip", "amount": "500", "period": "custom",
        "start_date": "2026-06-01"})
    assert bad.status_code == 422
    items = api.get("/api/period-budgets").json()
    week = items[0]
    assert week["current"]["spent"] == 40
    assert [h["spent"] for h in week["history"]][-1] == 25
    assert len(week["history"]) == 3


def test_monthly_period_windows():
    pb = type("PB", (), {"period": "monthly",
                         "start_date": date(2026, 1, 31), "end_date": None})
    assert bg.period_window(pb, 1) == (date(2026, 2, 28), date(2026, 3, 30))
    assert bg.current_index(pb, date(2026, 3, 5)) == 1


# --- IOUs and loans ----------------------------------------------------------
def test_iou_payments_and_settle(api):
    r = api.post("/api/ious", json={
        "person": "Sam", "direction": "lent", "amount": "100",
        "currency": "chf", "iou_date": "2026-03-01"})
    iou = r.json()["id"]
    api.post(f"/api/ious/{iou}/payments", json={
        "paid_on": "2026-03-10", "amount": "40"})
    data = api.get("/api/ious").json()
    assert data["items"][0]["open"] == 60
    assert data["owed_to_me"] == 60
    assert data["people"] == [{"person": "Sam", "balance": 60.0}]
    assert api.post(f"/api/ious/{iou}/settle").json()["settled_on"]
    assert api.get("/api/ious").json()["owed_to_me"] == 0


def test_amortization_and_payment_to_finish(api):
    plan = bg.amortization(1000, 12, 100, date(2026, 4, 1))
    assert plan["months"] == 11 and not plan["never"]
    assert plan["rows"][0]["interest"] == 10
    assert bg.amortization(1000, 12, 10, date(2026, 4, 1))["never"]
    assert bg.payment_to_finish(1000, 0, 10) == 100
    assert abs(bg.payment_to_finish(1000, 12, 12) - 88.85) < 0.01
    loan = make_account(api, "Car loan", type_="loan", opening="-5000")
    api.put(f"/api/debts/{loan}", json={"apr": "6", "min_payment": "200"})
    out = api.get(f"/api/debts/{loan}/schedule",
                  params={"finish_by": "2027-12-31"}).json()
    assert out["owed"] == 5000 and out["schedule"]["months"] > 20
    assert out["payment_to_finish"] > 200


# --- review queue, search and payees -----------------------------------------
def test_review_queue(api):
    acc = make_account(api)
    tid = add(api, acc, "2026-03-02", "-10")
    with SessionLocal() as db:
        db.execute(text("UPDATE transactions SET reviewed=0"))
        db.commit()
    assert api.get("/api/review/count").json()["count"] == 1
    page = api.get("/api/transactions", params={"reviewed": False}).json()
    assert [t["id"] for t in page["items"]] == [tid]
    assert api.post("/api/review/approve", json={}).json()["approved"] == 1
    assert api.get("/api/review/count").json()["count"] == 0


def test_search_syntax(api):
    acc = make_account(api, "UBS card")
    food = cat_id(api, "Groceries")
    add(api, acc, "2026-03-02", "-12.50", "weekly shop", food, "Migros")
    add(api, acc, "2026-03-03", "-80", "shoes", None, "Zalando")
    add(api, acc, "2026-03-04", "2000", "salary")

    def ids(q):
        page = api.get("/api/transactions", params={"q": q}).json()
        return sorted(t["description"] for t in page["items"]), \
            page["problems"]
    assert ids("payee:migros")[0] == ["weekly shop"]
    assert ids("amount:>50")[0] == ["salary", "shoes"]
    assert ids("amount:10..20")[0] == ["weekly shop"]
    assert ids("category:food")[0] == ["weekly shop"]
    found = ids('account:"ubs card" is:uncategorized')[0]
    assert found == ["salary", "shoes"]
    assert ids("before:2026-03-03")[0] == ["weekly shop"]
    assert ids("is:nonsense")[1]


def test_payee_memory(api):
    acc = make_account(api)
    food = cat_id(api, "Groceries")
    add(api, acc, "2026-03-02", "-12", "x", food, "Migros")
    add(api, acc, "2026-03-09", "-15", "x", None, "Migros")
    out = api.get("/api/payees", params={"q": "mig"}).json()
    assert out[0]["payee"] == "Migros" and out[0]["category_id"] == food
    assert out[0]["count"] == 2


# --- reports -----------------------------------------------------------------
def test_new_reports(api):
    acc = make_account(api, opening="500", opening_date="2025-01-01")
    add(api, acc, "2026-01-05", "3000", "pay", cat_id(api, "Salary",
                                                      "income"))
    for d in range(12):
        add(api, acc, f"2026-01-{10 + d:02d}", "-50", "shop",
            cat_id(api, "Groceries"), "Coop")
    for name in ("money_flow", "balance_history", "age_of_money"):
        r = api.get(f"/api/analytics/charts/{name}",
                    params={"start": "2025-12-01", "end": "2026-02-28"})
        assert r.status_code == 200, (name, r.text)
        assert "data" in r.json()
    payees = api.get("/api/analytics/payees", params={
        "start": "2026-01-01", "end": "2026-01-31"}).json()["payees"]
    assert payees[0]["payee"] == "Coop" and payees[0]["total"] == 600
    age = api.get("/api/analytics/age-of-money",
                  params={"end": "2026-01-31", "months": 2}).json()
    assert age["age"] is not None and age["age"] >= 0


# --- YNAB import -------------------------------------------------------------
REGISTER = (
    '"Account","Flag","Date","Payee","Category Group/Category",'
    '"Category Group","Category","Memo","Outflow","Inflow","Cleared"\n'
    '"Checking","","01/03/2026","Employer","Inflow: Ready to Assign",'
    '"Inflow","Ready to Assign","","$0.00","$2,000.00","Cleared"\n'
    '"Checking","","05/03/2026","Coop","Food: Groceries","Food",'
    '"Groceries","","$120.50","$0.00","Cleared"\n'
    '"Checking","","13/03/2026","Transfer : Savings","","","","",'
    '"$300.00","$0.00","Cleared"\n'
    '"Savings","","13/03/2026","Transfer : Checking","","","","",'
    '"$0.00","$300.00","Cleared"\n'
    '"Checking","","20/03/2026","Ikea","Home: Furniture","Home",'
    '"Furniture","Split (1/2) desk","$200.00","$0.00","Uncleared"\n'
    '"Checking","","20/03/2026","Ikea","Food: Groceries","Food",'
    '"Groceries","Split (2/2) snacks","$10.00","$0.00","Uncleared"\n')
PLAN = (
    '"Month","Category Group/Category","Category Group","Category",'
    '"Assigned","Activity","Available"\n'
    '"Mar 2026","Food: Groceries","Food","Groceries","$200.00",'
    '"-$130.50","$69.50"\n'
    '"Mar 2026","Home: Furniture","Home","Furniture","$250.00",'
    '"-$200.00","$50.00"\n')


def _zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("My Plan as of 2026-03-31 - Register.csv", REGISTER)
        z.writestr("My Plan as of 2026-03-31 - Plan.csv", PLAN)
    return buf.getvalue()


def test_ynab_import(api):
    files = {"file": ("export.zip", _zip(), "application/zip")}
    dry = api.post("/api/import/ynab", files=files,
                   data={"currency": "CHF", "dry_run": "true"})
    assert dry.status_code == 200, dry.text
    assert dry.json()["transactions"] == 5
    assert api.get("/api/accounts").json() == []
    real = api.post("/api/import/ynab", files=files,
                    data={"currency": "CHF", "dry_run": "false"}).json()
    assert real["transfers"] == 1 and real["splits"] == 1
    assert real["assignments"] == 2
    assert sorted(real["accounts_created"]) == ["Checking", "Savings"]
    assert real["differences"] == []
    again = api.post("/api/import/ynab", files=files,
                     data={"currency": "CHF", "dry_run": "false"}).json()
    assert again["duplicates"] == 5 and again["transactions"] == 0
    assert api.get("/api/settings").json()["budget_mode"] == "envelope"
    bad = api.post("/api/import/ynab", files={
        "file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
        data={"currency": "CHF"})
    assert bad.status_code == 422


def test_ynab_amounts_and_dates():
    from app.services.ynab import parse_amount, parse_date, parse_month
    assert parse_amount("$1,234.56") == Decimal("1234.56")
    assert parse_amount("1.234,56 €") == Decimal("1234.56")
    assert parse_amount("-$5.00") == Decimal("-5.00")
    assert parse_amount("CHF 12") == Decimal("12")
    assert parse_date("2026-03-05", "mdy") == date(2026, 3, 5)
    assert parse_date("03/05/2026", "mdy") == date(2026, 3, 5)
    assert parse_date("05.03.2026", "dmy") == date(2026, 3, 5)
    assert parse_month("Mar 2026") == date(2026, 3, 1)
    assert parse_month("March 2026") == date(2026, 3, 1)


# --- settings ----------------------------------------------------------------
def test_new_settings(api):
    r = api.put("/api/settings", json={
        "budget_mode": "envelope", "accent_color": "#2E7D32",
        "home_layout": [{"id": "budgets", "hidden": False},
                        {"id": "net_worth", "hidden": True}]})
    assert r.status_code == 200, r.text
    s = api.get("/api/settings").json()
    assert s["budget_mode"] == "envelope"
    assert s["accent_color"] == "#2E7D32"
    assert s["home_layout"][:2] == [{"id": "budgets", "hidden": False},
                                    {"id": "net_worth", "hidden": True}]
    assert len(s["home_layout"]) == 9
    assert api.put("/api/settings", json={
        "accent_color": "green"}).status_code == 422
