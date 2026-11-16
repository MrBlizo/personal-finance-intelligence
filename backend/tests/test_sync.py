"""0.7: sync between two devices through a shared folder."""
import base64
import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.db import make_engine, sqlite_url
from app.migrations import run_migrations
from app.seed import seed_defaults
from app.services import sync


class Device:
    """One PFI installation with its own database and data folder."""

    def __init__(self, root: Path, name: str):
        self.data = root / name
        self.data.mkdir()
        self.engine = make_engine(sqlite_url(self.data / "pfi.sqlite"))
        run_migrations(self.engine)
        self.db = Session(bind=self.engine, autoflush=False,
                          expire_on_commit=False)
        seed_defaults(self.db, "CHF")

    def setup(self, folder: Path, passphrase="correct horse"):
        return sync.setup(self.db, self.data, str(folder), passphrase,
                          self.data.name)

    def run(self):
        return sync.run(self.db, self.data)

    def account(self, name):
        return self.db.scalar(select(models.Account).where(
            models.Account.name == name))

    def category(self, name, kind="expense"):
        return self.db.scalar(select(models.Category).where(
            models.Category.name == name, models.Category.kind == kind))

    def txns(self):
        return self.db.scalars(select(models.Transaction).order_by(
            models.Transaction.txn_date, models.Transaction.description)
        ).all()

    def close(self):
        self.db.close()
        self.engine.dispose()


@pytest.fixture()
def pair(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PBKDF2_ITERATIONS", 1000)
    a, b = Device(tmp_path, "pc"), Device(tmp_path, "phone")
    folder = tmp_path / "cloud" / "PFI Sync"
    yield a, b, folder
    a.close()
    b.close()


def _add_account(dev, name, currency="CHF"):
    acc = models.Account(name=name, type="checking", currency=currency,
                         opening_balance=Decimal("100"),
                         opening_date=date(2026, 1, 1))
    dev.db.add(acc)
    dev.db.commit()
    return acc


def _add_txn(dev, acc, amount, desc, category=None, day=10):
    t = models.Transaction(
        account_id=acc.id, txn_date=date(2026, 11, day),
        amount=Decimal(amount), kind="expense" if Decimal(amount) < 0
        else "income", description=desc,
        category_id=category.id if category else None)
    dev.db.add(t)
    dev.db.commit()
    return t


def _tick():
    time.sleep(1.05)  # ORM timestamps have one-second resolution


def test_crypto_round_trip_and_wrong_key():
    key = b"k" * 32
    blob = sync.seal(key, "dev/00000001", {"x": "é"})
    assert blob[:4] == b"PFS1"
    assert sync.unseal(key, "dev/00000001", blob) == {"x": "é"}
    with pytest.raises(sync.SyncError, match="passphrase"):
        sync.unseal(b"z" * 32, "dev/00000001", blob)
    with pytest.raises(sync.SyncError):
        sync.unseal(key, "dev/00000002", blob)  # renamed file


def test_setup_creates_folder_and_checks_passphrase(pair):
    a, b, folder = pair
    st = a.setup(folder)
    assert st.enabled and (folder / "pfi-sync.json").exists()
    manifest = json.loads((folder / "pfi-sync.json").read_text())
    assert manifest["format"] == 1 and manifest["kdf"]["iterations"] == 1000
    with pytest.raises(sync.SyncError, match="does not match"):
        b.setup(folder, "wrong passphrase")
    with pytest.raises(sync.SyncError, match="8 characters"):
        b.setup(folder, "short")
    assert b.setup(folder).enabled
    assert a.db.execute(text("SELECT value FROM sync_state WHERE "
                             "key='device_id'")).scalar() != \
        b.db.execute(text("SELECT value FROM sync_state WHERE "
                          "key='device_id'")).scalar()


def test_two_devices_converge(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc = _add_account(a, "Salary account")
    food = a.category("Groceries")
    _add_txn(a, acc, "-42.50", "Migros", food)
    _add_txn(a, acc, "3000", "Salary")
    sent = a.run()
    assert sent.sent > 0 and sent.received == 0
    got = b.run()
    assert got.received > 0 and got.pending == 0
    bacc = b.account("Salary account")
    assert bacc is not None and bacc.uid == acc.uid
    txns = b.txns()
    assert [(t.description, t.amount) for t in txns] == [
        ("Migros", Decimal("-42.50")), ("Salary", Decimal("3000.00"))]
    # category merged by name+kind with b's own default "Groceries"
    assert txns[0].category_id == b.category("Groceries").id
    # nothing is echoed back
    assert b.run().sent == 0
    assert a.run().received == 0


def test_edit_and_delete_propagate(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc = _add_account(a, "Cash")
    t1 = _add_txn(a, acc, "-10", "Coffee")
    t2_id = _add_txn(a, acc, "-20", "Lunch").id
    t1_uid = t1.uid
    a.run()
    b.run()
    _tick()
    bt = next(t for t in b.txns() if t.description == "Coffee")
    bt.amount = Decimal("-12.30")
    bt.notes = "with cake"
    b.db.commit()
    b.db.delete(next(t for t in b.txns() if t.description == "Lunch"))
    b.db.commit()
    b.run()
    res = a.run()
    assert res.received == 2
    a.db.expire_all()
    left = a.txns()
    assert [(t.description, t.amount, t.notes) for t in left] == [
        ("Coffee", Decimal("-12.30"), "with cake")]
    assert a.db.get(models.Transaction, t2_id) is None
    assert t1_uid == left[0].uid


def test_last_writer_wins(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc = _add_account(a, "Card")
    t = _add_txn(a, acc, "-5", "Bus")
    a.run()
    b.run()
    _tick()
    t.description = "Bus (A)"
    a.db.commit()
    _tick()
    bt = b.txns()[0]
    bt.description = "Bus (B, later)"
    b.db.commit()
    a.run()
    b.run()   # gets A's older edit: keeps its own
    a.run()   # gets B's newer edit
    a.db.expire_all()
    b.db.expire_all()
    assert a.txns()[0].description == "Bus (B, later)"
    assert b.txns()[0].description == "Bus (B, later)"


def test_delete_is_not_undone_by_older_copy(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc = _add_account(a, "Wallet")
    _add_txn(a, acc, "-1", "Gum")
    a.run()
    b.run()
    _tick()
    a.db.delete(a.txns()[0])
    a.db.commit()
    a.run()
    b.run()
    assert b.txns() == []
    # a stale record of the deleted row (e.g. a late file) is ignored
    gone = b.db.execute(text("SELECT uid FROM sync_tombstones WHERE "
                             "table_name='transactions'")).scalar()
    changed, waiting, problems = sync.apply_changes(b.db.connection(), [{
        "t": "transactions", "uid": gone, "u": "2026-01-01 00:00:00",
        "row": {"account_id": acc.uid, "txn_date": "2026-11-10",
                "amount": -100, "kind": "expense", "description": "Gum"}}])
    assert changed == 0 and not waiting and not problems


def test_same_account_created_on_both_devices_is_merged(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc_a = _add_account(a, "Cash")
    acc_b = _add_account(b, "Cash")
    assert acc_a.uid != acc_b.uid
    _add_txn(b, acc_b, "-3", "Bread")
    b.run()
    a.run()
    _add_txn(a, acc_a, "-4", "Milk")
    a.run()
    b.run()
    a.db.expire_all()
    b.db.expire_all()
    for dev in (a, b):
        accounts = dev.db.scalars(select(models.Account).where(
            models.Account.name == "Cash")).all()
        assert len(accounts) == 1
        assert sorted(t.description for t in dev.txns()) == \
            ["Bread", "Milk"]


def test_child_before_parent_waits(pair):
    a, b, folder = pair
    b.setup(folder)
    conn = b.db.connection()
    rec_txn = {"t": "transactions", "uid": "t" * 32,
               "u": "2026-11-16 10:00:00.000",
               "row": {"account_id": "a" * 32, "txn_date": "2026-11-10",
                       "amount": -500, "kind": "expense",
                       "description": "Later parent", "reviewed": 1,
                       "cleared": 0}}
    changed, waiting, _ = sync.apply_changes(conn, [rec_txn])
    assert changed == 0 and waiting == [rec_txn]
    rec_acc = {"t": "accounts", "uid": "a" * 32,
               "u": "2026-11-16 09:00:00.000",
               "row": {"name": "Remote", "type": "cash", "currency": "CHF",
                       "opening_balance": 0, "opening_date": "2026-01-01",
                       "is_archived": 0, "is_demo": 0}}
    changed, waiting, problems = sync.apply_changes(conn,
                                                    [rec_txn, rec_acc])
    assert (changed, waiting, problems) == (2, [], [])
    b.db.commit()
    assert b.txns()[0].account.name == "Remote"


def test_pending_survives_between_runs(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    acc = _add_account(a, "Later")
    _add_txn(a, acc, "-9", "Waits")
    a.run()
    # simulate files arriving out of order: drop the account record
    # into a second, later file
    files = sorted((folder / "changes").rglob("*.pfisync"))
    dev = files[0].parent.name
    key = sync._load_key(a.data)
    payload = sync.unseal(key, f"{dev}/00000001", files[0].read_bytes())
    acc_recs = [r for r in payload["changes"] if r["t"] == "accounts"]
    payload["changes"] = [r for r in payload["changes"]
                          if r["t"] != "accounts"]
    files[0].write_bytes(sync.seal(key, f"{dev}/00000001", payload))
    assert b.run().pending == 1
    sync.FolderStore(folder).write(dev, 2, sync.seal(
        key, f"{dev}/00000002", {"format": 1, "device": dev, "seq": 2,
                                 "changes": acc_recs}))
    res = b.run()
    assert res.pending == 0
    assert [t.description for t in b.txns()] == ["Waits"]


def test_status_and_disable(pair):
    a, b, folder = pair
    a.setup(folder)
    b.setup(folder)
    a.run()
    b.run()
    st = sync.status(b.db, b.data)
    assert st.enabled and st.folder == str(folder)
    assert [d["name"] for d in st.devices] == ["pc"]
    assert st.last_sync and not st.last_error
    st = sync.disable(b.db, b.data)
    assert not st.enabled
    with pytest.raises(sync.SyncError, match="not set up"):
        b.run()


def test_norm_time_orders_mixed_precision():
    assert sync.norm_time("2026-11-16 10:00:00") < \
        sync.norm_time("2026-11-16 10:00:00.001")
    assert sync.norm_time("2026-11-16T10:00:00.5+00:00") == \
        "2026-11-16 10:00:00.500000"


def test_attachments_are_not_sent(pair):
    a, b, folder = pair
    a.setup(folder)
    assert "attachments" not in sync.sync_tables()
    assert sync.sync_tables().index("accounts") < \
        sync.sync_tables().index("transactions")


def test_key_is_not_stored_in_plain_database(pair):
    a, _, folder = pair
    a.setup(folder)
    stored = a.db.execute(text("SELECT group_concat(value) FROM "
                               "sync_state")).scalar()
    key = sync._load_key(a.data)
    assert key and base64.b64encode(key).decode() not in stored


def test_sync_api(api, tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PBKDF2_ITERATIONS", 1000)
    r = api.get("/api/sync")
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = api.post("/api/sync/run")
    assert r.status_code == 422 and "not set up" in r.json()["detail"]
    folder = tmp_path / "api-sync"
    r = api.post("/api/sync/setup", json={
        "folder": str(folder), "passphrase": "correct horse",
        "device_name": "Test PC"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] and body["device_name"] == "Test PC"
    assert body["sent"] > 0          # default categories went out
    assert list((folder / "changes").rglob("*.pfisync"))
    r = api.post("/api/sync/run")
    assert r.status_code == 200 and r.json()["result"]["sent"] == 0
    r = api.post("/api/sync/setup", json={
        "folder": str(folder), "passphrase": "wrong passphrase"})
    assert r.status_code == 422 and "does not match" in r.json()["detail"]
    assert api.post("/api/sync/disable").json()["enabled"] is False


def test_emptied_folder_gets_everything_again(pair):
    """The folder is cleared and set up again: the PC sends all again."""
    import shutil
    a, b, folder = pair
    a.setup(folder)
    acc = _add_account(a, "Cash")
    _add_txn(a, acc, "-5", "Bread")
    assert a.run().sent > 0
    shutil.rmtree(folder)            # the user empties the cloud folder
    a.setup(folder)                  # ...and sets up sync again
    assert a.run().sent > 0, "everything must be sent to the new folder"
    b.setup(folder)
    b.run()
    assert [t.description for t in b.txns()] == ["Bread"]


def test_own_files_removed_are_sent_again(pair):
    import shutil
    a, b, folder = pair
    a.setup(folder)
    acc = _add_account(a, "Cash")
    _add_txn(a, acc, "-5", "Milk")
    a.run()
    shutil.rmtree(folder / "changes")   # only the change files disappear
    assert a.run().sent > 0
    b.setup(folder)
    b.run()
    assert [t.description for t in b.txns()] == ["Milk"]


def test_folder_reset_on_another_device_is_reported(pair, tmp_path):
    import shutil
    a, b, folder = pair
    a.setup(folder)
    a.run()
    shutil.rmtree(folder)
    b.setup(folder, "another passphrase")   # b creates a new folder
    with pytest.raises(sync.SyncError, match="set up again"):
        a.run()


def test_phone_can_find():
    assert sync.phone_can_find(r"C:\Users\me\OneDrive\Apps\PFI Sync")
    assert sync.phone_can_find("/home/me/Dropbox/Apps/PFI Sync")
    assert not sync.phone_can_find(r"C:\Users\me\Documents\PFI Sync")
    assert not sync.phone_can_find(r"C:\Users\me\OneDrive\PFI Sync")
    assert not sync.phone_can_find(None)
