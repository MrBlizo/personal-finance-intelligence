"""1.0 planning: what-if scenarios, independence, year-end and tax."""
import csv
import io
from datetime import date, timedelta

from app.services.planning import add_months


def _setup(api, months=8, pay=5000, rent=-1500, other=-1200):
    acc = api.post("/api/accounts", json={
        "name": "Main", "type": "checking", "currency": "CHF",
        "opening_balance": "2000",
        "opening_date": (date.today() - timedelta(days=400)).isoformat()
    }).json()["id"]
    cats = {c["name"]: c["id"] for c in api.get("/api/categories").json()}
    first = add_months(date.today().replace(day=1), -months)
    for i in range(months + 1):
        day = add_months(first, i)
        for amount, kind, cat in ((pay, "income", "Salary"),
                                  (rent, "expense", "Rent"),
                                  (other, "expense", "Groceries")):
            api.post("/api/transactions", json={
                "account_id": acc, "txn_date": day.isoformat(),
                "amount": str(amount), "kind": kind, "description": cat,
                "category_id": cats[cat]})
    return acc, cats


def test_what_if_shifts_the_forecast(api):
    _setup(api)
    base = api.post("/api/forecast/what-if", json={
        "changes": [], "horizon_days": 120}).json()
    car = api.post("/api/forecast/what-if", json={
        "changes": [{"kind": "once", "amount": -100000, "label": "Car"}],
        "horizon_days": 120}).json()
    save = api.post("/api/forecast/what-if", json={
        "changes": [{"kind": "monthly", "amount": 300}],
        "horizon_days": 120}).json()
    assert base["baseline"] == base["scenario"]
    assert car["changes"] == ["Car"]
    assert car["verdict"] == "not_affordable"
    gap = base["end"]["scenario"] - car["end"]["scenario"]
    assert abs(gap - 100000) < 1e-6
    months = (save["end"]["scenario"] - save["end"]["baseline"]) / 300
    assert months in (4, 5)
    bad = api.post("/api/forecast/what-if", json={
        "changes": [{"kind": "lottery"}]})
    assert bad.status_code == 422 and "monthly" in bad.json()["detail"]


def test_what_if_percentage_of_a_bill(api):
    acc, cats = _setup(api)
    rec = api.post("/api/recurring", json={
        "name": "Rent", "account_id": acc, "category_id": cats["Rent"],
        "amount": "-1500", "frequency": "monthly",
        "start_date": date.today().replace(day=1).isoformat(),
        "is_active": True}).json()
    out = api.post("/api/forecast/what-if", json={
        "changes": [{"kind": "recurring_pct", "recurring_id": rec["id"],
                     "pct": 10}], "horizon_days": 95}).json()
    diff = out["end"]["baseline"] - out["end"]["scenario"]
    assert diff in (450, 600)  # three or four rent payments, 150 more each
    assert api.get("/api/forecast/what-if/choices").json()[0]["name"] == \
        "Rent"


def test_independence(api):
    _setup(api, months=13)
    fi = api.get("/api/planning/independence",
                 params={"return_pct": 5, "withdrawal_pct": 4}).json()
    assert fi["annual_income"] == 60000 and fi["annual_spending"] == 32400
    assert fi["target"] == 32400 / 0.04
    assert fi["years"] is not None and fi["years"] > 0
    assert fi["path"][0]["value"] == fi["invested"]
    faster = api.get("/api/planning/independence",
                     params={"extra_monthly": 1000}).json()
    assert faster["years"] < fi["years"]


def test_year_report_and_tax_export(api):
    acc, cats = _setup(api, months=14)
    year = date.today().year - 1
    gift = api.post("/api/transactions", json={
        "account_id": acc, "txn_date": f"{year}-06-15", "amount": "-250",
        "kind": "expense", "description": "Red Cross",
        "category_id": cats["Donations"]}).json()
    assert gift["id"]
    r = api.put("/api/reports/tax-groups",
                json={str(cats["Family & Gifts"]): "donations"})
    assert r.status_code == 200, r.text
    assert r.json()["categories"] == {str(cats["Family & Gifts"]):
                                      "donations"}
    bad = api.put("/api/reports/tax-groups",
                  json={str(cats["Rent"]): "yachts"})
    assert bad.status_code == 422 and "donations" in bad.json()["detail"]
    data = api.get("/api/reports/yearly", params={"year": year}).json()
    assert data["tax_groups"] == [{"group": "donations",
                                   "label": "Donations", "amount": 250.0}]
    assert data["expenses"] > 0 and data["months"]
    pdf = api.get("/api/reports/yearly.pdf", params={"year": year})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    csv_text = api.get("/api/reports/tax.csv",
                       params={"year": year}).content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0][0] == "tax_group" and len(rows) == 2
    assert rows[1][0] == "Donations" and rows[1][3] == "Red Cross"
