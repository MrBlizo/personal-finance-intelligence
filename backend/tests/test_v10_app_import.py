"""Importing Cashew and Mint exports."""

CASHEW = (
    "account,amount,currency,title,note,date,income,type,category name,"
    "subcategory name,color,icon,emoji,budget,objective\n"
    "Wallet,-12.5,EUR,Bakery,,2026-03-02 08:15:00.000,false,null,Food,"
    "Groceries,,,,,\n"
    "Wallet,2500,EUR,Salary,March,2026-03-01 09:00:00.000,true,null,"
    "Salary,,,,,,\n"
    "Card,-60,USD,Gym,,2026-03-05 18:00:00.000,false,null,Fitness,,,,,,\n")
MINT = (
    '"Date","Description","Original Description","Amount",'
    '"Transaction Type","Category","Account Name","Labels","Notes"\n'
    '"3/04/2026","Whole Foods","WHOLEFDS #123","54.20","debit",'
    '"Groceries","Checking","",""\n'
    '"3/01/2026","Acme Payroll","ACME","3,100.00","credit","Paycheck",'
    '"Checking","",""\n'
    '"3/06/2026","Card payment","PAYMENT","200.00","debit",'
    '"Credit Card Payment","Checking","",""\n'
    '"3/07/2026","Shell","SHELL","40.00","debit","Auto & Transport",'
    '"Checking","",""\n')


def _post(api, text, **form):
    return api.post("/api/import/app", data={"currency": "USD", **form},
                    files={"file": ("export.csv", text.encode(),
                                    "text/csv")})


def test_cashew_import_and_reimport(api):
    dry = _post(api, CASHEW).json()
    assert dry["source"] == "cashew" and dry["transactions"] == 3
    assert api.get("/api/transactions").json()["total"] == 0
    done = _post(api, CASHEW, dry_run="false").json()
    assert set(done["accounts_created"]) == {"Wallet", "Card"}
    assert "Fitness" in done["categories_created"]
    accs = {a["name"]: a for a in api.get("/api/accounts").json()}
    assert accs["Wallet"]["currency"] == "EUR"
    assert accs["Card"]["currency"] == "USD"
    txns = api.get("/api/transactions").json()["items"]
    bakery = next(t for t in txns if t["description"] == "Bakery")
    assert bakery["amount"] == -12.5 and bakery["txn_date"] == "2026-03-02"
    assert next(t for t in txns if t["description"] == "Salary")["kind"] \
        == "income"
    again = _post(api, CASHEW, dry_run="false").json()
    assert again["transactions"] == 0 and again["duplicates"] == 3


def test_mint_import(api):
    done = _post(api, MINT, dry_run="false").json()
    assert done["source"] == "mint"
    assert done["transactions"] == 3  # the card payment is a transfer
    txns = {t["description"]: t
            for t in api.get("/api/transactions").json()["items"]}
    assert txns["Whole Foods"]["amount"] == -54.2
    assert txns["Acme Payroll"]["amount"] == 3100
    assert txns["Shell"]["category_name"].endswith("Transport")


def test_unknown_file_explains(api):
    r = _post(api, "Datum;Betrag\n1.3.2026;-5\n")
    assert r.status_code == 422 and "Cashew or Mint" in r.json()["detail"]
    bad = _post(api, CASHEW.replace("-12.5", "twelve"), dry_run="false")
    assert bad.status_code == 422 and "row 2" in bad.json()["detail"]
