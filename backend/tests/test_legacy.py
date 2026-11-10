"""Moving a PFI 0.3 PostgreSQL database (and .dump backups) into SQLite.

Needs ``PFI_TEST_PG_BIN``; skipped otherwise.
"""
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import legacy
from app.db import make_engine, sqlite_url
from app.models import Transaction
from app.pg_embedded import EmbeddedPostgres, _free_port

PG_BIN = os.environ.get("PFI_TEST_PG_BIN")
pytestmark = pytest.mark.skipif(not PG_BIN,
                                reason="needs PFI_TEST_PG_BIN")


def make_v03_cluster(data_dir: Path) -> None:
    legacy.make_v03_cluster(Path(PG_BIN), data_dir)


def _sqlite_total(path: Path) -> tuple[int, Decimal]:
    eng = make_engine(sqlite_url(path))
    with eng.connect() as c:
        n = c.scalar(select(func.count(Transaction.id)))
        total = c.scalar(select(func.sum(Transaction.amount)))
    eng.dispose()
    return n, total


def test_cluster_is_moved_and_kept(tmp_path):
    make_v03_cluster(tmp_path)
    assert legacy.has_cluster(tmp_path)
    dest = tmp_path / "pfi.sqlite"
    counts = legacy.migrate_cluster(Path(PG_BIN), tmp_path, dest,
                                    _free_port())
    assert counts["transactions"] == 300 and counts["accounts"] == 1
    n, total = _sqlite_total(dest)
    assert n == 300
    assert total == Decimal("-12.35") * 200 + Decimal("4500.10") * 100
    assert not legacy.has_cluster(tmp_path)
    assert (tmp_path / "pgdata-0.3" / "PG_VERSION").is_file()
    assert not (tmp_path / "runtime").exists()
    eng = make_engine(sqlite_url(dest))
    with eng.connect() as c:
        from app.models import Account, ExchangeRate, SchemaVersion
        acc = c.execute(select(Account)).one()
        assert acc.opening_balance == Decimal("1000.05")
        assert c.scalar(select(ExchangeRate.rate)) == Decimal("0.93456789")
        assert max(c.scalars(select(SchemaVersion.version))) >= 4
    eng.dispose()


def test_failed_copy_changes_nothing(tmp_path, monkeypatch):
    make_v03_cluster(tmp_path)

    def broken(*args, **kwargs):
        raise legacy.LegacyError("simulated")

    monkeypatch.setattr(legacy, "_verify", broken)
    with pytest.raises(legacy.LegacyError):
        legacy.migrate_cluster(Path(PG_BIN), tmp_path, tmp_path / "x.db",
                               _free_port())
    assert legacy.has_cluster(tmp_path)
    assert not (tmp_path / "x.db").exists()
    assert not list(tmp_path.glob("x.db.part*"))


def test_old_dump_backup_becomes_sqlite(tmp_path):
    src_dir = tmp_path / "old"
    make_v03_cluster(src_dir)
    pg = EmbeddedPostgres(Path(PG_BIN), src_dir, _free_port())
    pg.start()
    dump = tmp_path / "pfi-manual-20250601-120000.dump"
    subprocess.run([pg.tool("pg_dump"), "--format=custom", "--no-owner",
                    f"--file={dump}"], env=pg.client_env(), check=True)
    pg.stop()
    dest = tmp_path / "restored.sqlite"
    counts = legacy.dump_to_sqlite(Path(PG_BIN), tmp_path, dump, dest)
    assert counts["transactions"] == 300
    assert _sqlite_total(dest)[0] == 300
    assert not list(tmp_path.glob("pfi-legacy-*"))


def test_selftest_with_store_style_copy(tmp_path):
    result = legacy.selftest(Path(PG_BIN), tmp_path / "self", relocate=True)
    assert result["transactions"] == 300
    assert result["runtime_copy"].startswith("pgsql-")
