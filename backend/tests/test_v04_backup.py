"""0.4: exact decimals on SQLite, backup folder, encryption, moving PCs."""
import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Transaction
from app.services import backup as bk
from conftest import make_account

DATA = Path(os.environ["PFI_DATA_DIR"])


@pytest.fixture(autouse=True)
def plain_backups():
    """Every test starts with the default folder and no password."""
    bk.save_config(DATA, None, False, clear_password=True)
    yield
    bk.save_config(DATA, None, False, clear_password=True)


def test_amounts_and_sums_stay_exact(api):
    acc = make_account(api, opening="0")
    for _ in range(10):
        api.post("/api/transactions", json={
            "account_id": acc, "txn_date": "2026-03-01", "amount": "0.10",
            "description": "ten cents"})
    api.post("/api/transactions", json={
        "account_id": acc, "txn_date": "2026-03-02",
        "amount": "-1234567.89", "description": "big"})
    with SessionLocal() as db:
        total = db.scalar(select(func.sum(Transaction.amount)))
    assert total == Decimal("-1234566.89")
    bal = next(a for a in api.get("/api/accounts").json() if a["id"] == acc)
    assert bal["balance"] == -1234566.89


def test_backup_folder_and_fallback(api, tmp_path):
    folder = tmp_path / "OneDrive" / "PFI"
    folder.mkdir(parents=True)
    r = api.put("/api/backups/settings", json={"folder": str(folder)})
    assert r.status_code == 200 and r.json()["chosen_folder"] == str(folder)
    b = api.post("/api/backups").json()
    assert Path(b["folder"]) == folder and b["warning"] is None
    assert (folder / b["name"]).is_file()
    assert b["name"] in [x["name"] for x in
                         api.get("/api/backups").json()["backups"]]
    folder.rename(tmp_path / "unplugged")
    b2 = api.post("/api/backups").json()
    assert Path(b2["folder"]) == DATA / "backups"
    assert "does not exist" in b2["warning"]
    missing = api.put("/api/backups/settings",
                      json={"folder": str(tmp_path / "nope")})
    assert missing.status_code == 422 and "does not exist" in \
        missing.json()["detail"]
    relative = api.put("/api/backups/settings", json={"folder": "PFI"})
    assert relative.status_code == 422


def test_encrypted_backup_needs_the_password(api, tmp_path):
    make_account(api, "Before")
    short = api.put("/api/backups/settings",
                    json={"encrypt": True, "password": "short"})
    assert short.status_code == 422
    assert api.put("/api/backups/settings",
                   json={"encrypt": True}).status_code == 422
    s = api.put("/api/backups/settings", json={
        "encrypt": True, "password": "correct horse battery"}).json()
    assert s["encrypt"] and s["has_password"]
    assert "correct horse" not in (DATA / bk.SECRET_FILE).read_text()
    b = api.post("/api/backups").json()
    assert b["encrypted"]
    raw = (Path(b["folder"]) / b["name"]).read_bytes()
    assert raw.startswith(bk.MAGIC) and b"pfi.sqlite" not in raw
    make_account(api, "After")
    # The saved password is used automatically on this PC ...
    assert api.post(f"/api/backups/{b['name']}/restore").status_code == 200
    assert [a["name"] for a in api.get("/api/accounts").json()] == ["Before"]
    # ... on another PC the password has to be typed in.
    bk.save_config(DATA, None, False, clear_password=True)
    locked = api.post(f"/api/backups/{b['name']}/restore")
    assert locked.status_code == 423 and "password" in \
        locked.json()["detail"]
    wrong = api.post(f"/api/backups/{b['name']}/restore",
                     json={"password": "wrong password!"})
    assert wrong.status_code == 423 and "wrong" in wrong.json()["detail"]
    ok = api.post(f"/api/backups/{b['name']}/restore",
                  json={"password": "correct horse battery"})
    assert ok.status_code == 200


def test_tampered_or_truncated_encrypted_file(tmp_path):
    src = tmp_path / "plain.bin"
    src.write_bytes(os.urandom(bk.CHUNK * 2 + 123))
    enc = tmp_path / "enc.bin"
    bk.encrypt_file(src, enc, "a long password")
    out = tmp_path / "out.bin"
    bk.decrypt_file(enc, out, "a long password")
    assert out.read_bytes() == src.read_bytes()
    cut = tmp_path / "cut.bin"
    data = enc.read_bytes()
    cut.write_bytes(data[: len(data) - (123 + 16 + 4)])
    with pytest.raises(bk.PasswordError):
        bk.decrypt_file(cut, out, "a long password")
    flipped = bytearray(data)
    flipped[100] ^= 1
    cut.write_bytes(bytes(flipped))
    with pytest.raises(bk.PasswordError):
        bk.decrypt_file(cut, out, "a long password")


def test_move_to_another_pc_backup_and_upload(api):
    make_account(api, "Old PC")
    move = api.post("/api/backups", json={"kind": "move"}).json()
    assert move["name"].startswith("pfi-move-")
    content = api.get(f"/api/backups/{move['name']}/download").content
    assert api.post("/api/backups", json={"kind": "auto"}).status_code == 422
    make_account(api, "Should disappear")
    up = api.post("/api/backups/upload", files={
        "file": ("pfi-move.pfibak", content, "application/octet-stream")})
    name = up.json()["name"]
    assert api.post(f"/api/backups/{name}/restore").status_code == 200
    assert [a["name"] for a in api.get("/api/accounts").json()] == ["Old PC"]
    assert api.get("/api/info").json()["empty"] is False


def test_auto_backup_keeps_eight(api, monkeypatch):
    from datetime import datetime, timedelta
    s = api.get("/api/info").json()
    db = Path(s["database_file"])
    for f in (DATA / "backups").glob("pfi-auto-*"):
        f.unlink()
    start = datetime(2026, 1, 1)
    for week in range(10):
        made = bk.auto_backup_if_due(DATA, db, start + timedelta(weeks=week))
        assert made is not None
        ts = (start + timedelta(weeks=week)).timestamp()
        os.utime(Path(made.folder) / made.name, (ts, ts))
    assert bk.auto_backup_if_due(DATA, db, start + timedelta(weeks=9,
                                                             days=1)) is None
    autos = [b for b in bk.list_backups(DATA) if b.kind == "auto"]
    assert len(autos) == bk.KEEP_AUTO


def test_restore_rejects_foreign_files(api, tmp_path):
    import zipfile
    path = DATA / "backups" / "pfi-uploaded-20260101-000000.pfibak"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("hello.txt", "not a backup")
    r = api.post(f"/api/backups/{path.name}/restore")
    assert r.status_code == 422 and "not a PFI backup" in r.json()["detail"]
    path.unlink()
