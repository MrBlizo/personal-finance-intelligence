"""Month-by-month overview (1.0)."""
from datetime import date

from app.services.planning import add_months


def _txn(api, account_id, day, amount, kind, **extra):
    r = api.post("/api/transactions", json={
        "account_id": account_id, "txn_date": day, "amount": amount,
        "kind": kind, "description": extra.pop("description", "x"), **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_month_spent_paid_saved(api):
    acc = api.post("/api/accounts", json={
        "name": "Main", "type": "checking", "currency": "CHF",
        "opening_date": "2026-01-01"}).json()
    card = api.post("/api/accounts", json={
        "name": "Card", "type": "credit_card", "currency": "CHF",
        "opening_date": "2026-01-01"}).json()
    sav = api.post("/api/accounts", json={
        "name": "Rainy day", "type": "savings", "currency": "CHF",
        "opening_date": "2026-01-01"}).json()
    food = api.post("/api/categories", json={
        "name": "Market food", "kind": "expense"}).json()
    _txn(api, acc["id"], "2026-03-01", 3000, "income")
    _txn(api, acc["id"], "2026-03-05", -120.5, "expense",
         category_id=food["id"], description="Market")
    _txn(api, acc["id"], "2026-02-10", -80, "expense",
         category_id=food["id"])
    for to, amount in ((card["id"], 200), (sav["id"], 500)):
        r = api.post("/api/transfers", json={
            "from_account_id": acc["id"], "to_account_id": to,
            "amount": amount, "txn_date": "2026-03-20"})
        assert r.status_code in (200, 201), r.text

    d = api.get("/api/analytics/months/2026-03").json()
    assert d["totals"]["income"] == 3000
    assert d["totals"]["spent"] == 120.5
    assert d["totals"]["debt_payments"] == 200
    assert d["totals"]["paid"] == 200
    assert d["totals"]["saved"] == 500
    assert d["totals"]["net"] == 3000 - 120.5
    assert d["previous"]["spent"] == 80
    assert d["categories"][0] == {"category": "Market food", "amount": 120.5,
                                  "share": 1.0, "previous": 80.0}
    assert d["debt_payments"] == [{"account": "Card", "amount": 200.0}]
    assert d["biggest"][0]["description"] == "Market"
    assert len(d["daily"]["this"]) == 31
    assert d["daily"]["this"][4] == 120.5 and d["daily"]["this"][-1] == 120.5

    tl = api.get("/api/analytics/months",
                 params={"count": 3}).json()["months"]
    assert all(m["month"] <= date.today().strftime("%Y-%m") for m in tl)


def test_bad_month_says_how_to_fix(api):
    r = api.get("/api/analytics/months/March")
    assert r.status_code == 422 and "YYYY-MM" in r.json()["detail"]


def test_timeline_covers_requested_months(api):
    acc = api.post("/api/accounts", json={
        "name": "Main", "type": "checking", "currency": "CHF",
        "opening_date": "2020-01-01"}).json()
    first = add_months(date.today().replace(day=1), -2)
    _txn(api, acc["id"], first.isoformat(), -10, "expense")
    tl = api.get("/api/analytics/months",
                 params={"count": 3}).json()["months"]
    assert [m["month"] for m in tl] == [
        add_months(first, i).strftime("%Y-%m") for i in range(3)]
    assert tl[0]["spent"] == 10 and tl[1]["spent"] == 0
