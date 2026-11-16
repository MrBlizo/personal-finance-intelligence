"""Cross-check sync between the PC (Python) and the phone app (Dart).

``make <dir>``: a PC database with demo data syncs into ``<dir>/cloud`` and
``<dir>/expected.json`` records what the phone must see.
``verify <dir>``: the PC syncs again and checks the transaction the phone
app's test added.
Used by .github/workflows/mobile.yml.
"""
import json
import sys
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import make_engine, sqlite_url  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.seed import seed_defaults  # noqa: E402
from app.services import sync  # noqa: E402
from app.services.demo import seed_demo  # noqa: E402

PASSPHRASE = "interop passphrase"
sync.PBKDF2_ITERATIONS = 20_000


def _open(root: Path) -> tuple[Session, Path]:
    data = root / "pc"
    data.mkdir(parents=True, exist_ok=True)
    engine = make_engine(sqlite_url(data / "pfi.sqlite"))
    run_migrations(engine)
    return Session(bind=engine), data


def make(root: Path) -> None:
    db, data = _open(root)
    seed_defaults(db, "CHF")
    seed_demo(db)
    db.commit()
    sync.setup(db, data, str(root / "cloud"), PASSPHRASE, "CI PC")
    res = sync.run(db, data)
    conn = db.connection()
    expected = {
        "passphrase": PASSPHRASE,
        "sent": res.sent,
        "accounts": db.scalar(select(func.count(models.Account.id))),
        "categories": db.scalar(select(func.count(models.Category.id))),
        "transactions": db.scalar(select(func.count(models.Transaction.id))),
        "amount_sum": conn.execute(text(
            "SELECT sum(amount) FROM transactions")).scalar(),
        "splits": db.scalar(select(func.count(models.TransactionSplit.id))),
    }
    (root / "expected.json").write_text(json.dumps(expected, indent=1))
    print(json.dumps(expected))


def verify(root: Path) -> None:
    db, data = _open(root)
    res = sync.run(db, data)
    print(f"PC received {res.received} changes, {res.pending} waiting, "
          f"problems: {res.problems}")
    txn = db.scalar(select(models.Transaction).where(
        models.Transaction.description == "Added on the phone"))
    assert txn is not None, "the phone's transaction did not arrive"
    assert str(txn.amount) == "-12.34", txn.amount
    assert txn.category is not None and txn.category.name == "Groceries"
    edited = db.scalar(select(func.count(models.Transaction.id)).where(
        models.Transaction.notes == "edited on the phone"))
    assert edited == 1, edited
    assert not res.problems and res.pending == 0
    print("PC sees the phone's changes: OK")


if __name__ == "__main__":
    {"make": make, "verify": verify}[sys.argv[1]](Path(sys.argv[2]))
