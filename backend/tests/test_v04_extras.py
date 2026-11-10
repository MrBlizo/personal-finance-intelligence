"""0.4: split transactions, tags and receipt attachments."""
import os
from pathlib import Path

from app.db import SessionLocal
from app.services.frame import expenses, load_transactions
from app.services.fx import FxConverter
from conftest import cat_id, make_account

DATA = Path(os.environ["PFI_DATA_DIR"])
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
       b"\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _txn(api, acc, amount="-100.00", **extra):
    r = api.post("/api/transactions", json={
        "account_id": acc, "txn_date": "2026-05-10", "amount": amount,
        "description": "Supermarket", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_split_counts_each_part_in_its_category(api):
    acc = make_account(api)
    groceries = cat_id(api, "Groceries")
    household = cat_id(api, "Home & Garden")
    tid = _txn(api, acc, category_id=groceries)
    api.post("/api/budgets", json={"category_id": household,
                                   "monthly_amount": "50"})
    r = api.put(f"/api/transactions/{tid}/splits", json={"parts": [
        {"category_id": groceries, "amount": "-60.00", "note": "food"},
        {"category_id": household, "amount": "-40.00"}]})
    assert r.status_code == 200 and len(r.json()) == 2
    with SessionLocal() as db:
        df = load_transactions(db, FxConverter.from_db(db), "CHF")
    exp = expenses(df)
    by_cat = exp.groupby("category")["spend"].sum().to_dict()
    assert by_cat == {"Groceries": 60.0, "Home & Garden": 40.0}
    assert df["split"].all() and set(df["id"]) == {tid}
    status = api.get("/api/budgets/status",
                     params={"month": "2026-05"}).json()
    hh = next(b for b in status["items"] if b["category_id"] == household) \
        if isinstance(status, dict) else \
        next(b for b in status if b["category_id"] == household)
    assert hh["spent"] == 40.0
    item = api.get("/api/transactions").json()["items"][0]
    assert item["category_id"] is None and len(item["splits"]) == 2
    assert item["splits"][1]["category_name"].endswith("Home & Garden")
    found = api.get("/api/transactions",
                    params={"category_id": household}).json()
    assert found["total"] == 1
    assert api.get("/api/transactions", params={
        "uncategorized": True}).json()["total"] == 0
    locked = api.patch(f"/api/transactions/{tid}", json={"amount": "-90"})
    assert locked.status_code == 409 and "split" in locked.json()["detail"]
    assert api.patch(f"/api/transactions/{tid}", json={
        "description": "Migros"}).status_code == 200
    assert api.put(f"/api/transactions/{tid}/splits",
                   json={"parts": []}).json() == []
    assert api.get("/api/transactions").json()["items"][0]["splits"] == []


def test_split_validation(api):
    acc = make_account(api)
    groceries = cat_id(api, "Groceries")
    tid = _txn(api, acc)
    bad_sum = api.put(f"/api/transactions/{tid}/splits", json={"parts": [
        {"category_id": groceries, "amount": "-60"},
        {"category_id": groceries, "amount": "-30"}]})
    assert bad_sum.status_code == 422 and "add up" in \
        bad_sum.json()["detail"]
    one = api.put(f"/api/transactions/{tid}/splits", json={"parts": [
        {"category_id": groceries, "amount": "-100"}]})
    assert one.status_code == 422
    salary = cat_id(api, "Salary", "income")
    wrong_kind = api.put(f"/api/transactions/{tid}/splits", json={"parts": [
        {"category_id": groceries, "amount": "-60"},
        {"category_id": salary, "amount": "-40"}]})
    assert wrong_kind.status_code == 422 and "income" in \
        wrong_kind.json()["detail"]
    other = make_account(api, "Savings", type_="savings")
    tr = api.post("/api/transfers", json={
        "from_account_id": acc, "to_account_id": other,
        "txn_date": "2026-05-11", "amount": "50"}).json()
    leg = tr["legs"][0]["id"] if "legs" in tr else tr[0]["id"]
    assert api.put(f"/api/transactions/{leg}/splits", json={"parts": [
        {"amount": "-25"}, {"amount": "-25"}]}).status_code == 409


def test_tags_filter_and_report(api):
    acc = make_account(api)
    a = _txn(api, acc, "-120.00", category_id=cat_id(api, "Groceries"))
    b = _txn(api, acc, "-30.00")
    _txn(api, acc, "-5.00")
    assert api.put(f"/api/transactions/{a}/tags", json={
        "tags": ["Holiday 2026", "holiday 2026", " Italy "]}).json() == [
        "Holiday 2026", "Italy"]
    api.put(f"/api/transactions/{b}/tags", json={"tags": ["HOLIDAY 2026"]})
    tags = {t["name"]: t["count"] for t in api.get("/api/tags").json()}
    assert tags == {"Holiday 2026": 2, "Italy": 1}
    page = api.get("/api/transactions",
                   params={"tag": "holiday 2026"}).json()
    assert page["total"] == 2
    assert sorted(page["items"][0]["tags"]) in (["Holiday 2026"],
                                                ["Holiday 2026", "Italy"])
    report = api.get("/api/analytics/tags").json()["items"]
    assert report[0] == {"tag": "Holiday 2026", "spent": 150.0,
                         "received": 0.0, "transactions": 2}
    too_long = api.put(f"/api/transactions/{b}/tags",
                       json={"tags": ["x" * 61]})
    assert too_long.status_code == 422
    italy = next(t for t in api.get("/api/tags").json()
                 if t["name"] == "Italy")
    assert api.patch(f"/api/tags/{italy['id']}",
                     json={"name": "Italia"}).json()["name"] == "Italia"
    assert api.delete(f"/api/tags/{italy['id']}").status_code == 204
    assert api.get("/api/transactions").json()["items"][-1]["tags"] == [
        "Holiday 2026"]


def test_attachments_upload_backup_and_cleanup(api):
    acc = make_account(api)
    tid = _txn(api, acc)
    up = api.post(f"/api/transactions/{tid}/attachments",
                  files={"file": ("receipt.png", PNG, "image/png")})
    assert up.status_code == 201, up.text
    att = up.json()
    assert att["filename"] == "receipt.png" and att["size"] == len(PNG)
    assert api.get("/api/transactions").json()["items"][0]["attachments"] \
        == 1
    got = api.get(f"/api/attachments/{att['id']}")
    assert got.status_code == 200 and got.content == PNG
    exe = api.post(f"/api/transactions/{tid}/attachments", files={
        "file": ("virus.exe", b"MZ", "application/x-msdownload")})
    assert exe.status_code == 415
    backup = api.post("/api/backups").json()
    files = list((DATA / "attachments").iterdir())
    assert len(files) == 1
    assert api.delete(f"/api/transactions/{tid}").status_code == 204
    assert not list((DATA / "attachments").iterdir())
    assert api.post(f"/api/backups/{backup['name']}/restore"
                    ).status_code == 200
    restored = api.get("/api/transactions").json()["items"]
    assert restored and restored[0]["attachments"] == 1
    assert api.get(f"/api/attachments/{att['id']}").content == PNG
    assert api.delete(f"/api/attachments/{att['id']}").status_code == 204
    assert not list((DATA / "attachments").iterdir())
