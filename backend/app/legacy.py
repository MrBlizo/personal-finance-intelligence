"""Move data from the PostgreSQL era (0.1-0.3) into SQLite.

Up to 0.3 the app ran a private PostgreSQL cluster in ``<data_dir>/pgdata``
and wrote backups with ``pg_dump`` (``.dump``). Since 0.4 the data lives in
one SQLite file. This module

* moves an existing cluster into SQLite on the first start of 0.4
  (``migrate_cluster``): the cluster is started one last time, every table
  is copied, row counts and the sum of all amounts are compared, and only
  then is ``pgdata`` renamed to ``pgdata-0.3`` (never deleted);
* turns an old ``.dump`` backup into a SQLite database
  (``dump_to_sqlite``) through a temporary cluster.

Both need the bundled PostgreSQL binaries (``PFI_PG_BIN``).
"""
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, MetaData, func, select, text

from .db import Base, make_engine, sqlite_url
from .migrations import run_migrations
from .pg_embedded import (NO_WINDOW, EmbeddedPostgres, _free_port,
                          in_store_package, relocate_binaries)

log = logging.getLogger(__name__)
BATCH = 2000
RETIRED = "pgdata-0.3"


class LegacyError(RuntimeError):
    """Raised when old PostgreSQL data cannot be moved to SQLite."""


def has_cluster(data_dir: Path) -> bool:
    """Return whether ``data_dir`` holds a 0.3.x PostgreSQL cluster.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    """
    return (Path(data_dir) / "pgdata" / "PG_VERSION").is_file()


def _plain(value):
    """Return ``value`` in a form SQLite stores consistently."""
    if hasattr(value, "tzinfo") and getattr(value, "tzinfo", None):
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def copy_database(src: Engine, dest_path: Path) -> dict[str, int]:
    """Copy every application table from ``src`` into a new SQLite file.

    The copy is written to ``<dest>.part`` and renamed only after the
    checks pass: the same number of rows in every table, the same sum of
    transaction amounts, and no broken foreign keys.

    Parameters
    ----------
    src : Engine
        The engine of the source (PostgreSQL) database, already migrated
        to the newest 0.3 schema.
    dest_path : Path
        The SQLite file to create; it must not exist yet.

    Returns
    -------
    dict of str to int
        The number of rows copied per table.

    Raises
    ------
    LegacyError
        If a check fails; the partial copy is removed.
    """
    dest_path = Path(dest_path)
    part = dest_path.with_name(dest_path.name + ".part")
    for leftover in (part, Path(f"{part}-wal"), Path(f"{part}-shm")):
        leftover.unlink(missing_ok=True)
    dest = make_engine(sqlite_url(part))
    counts: dict[str, int] = {}
    try:
        run_migrations(dest)
        source = MetaData()
        source.reflect(src)
        with src.connect() as sconn, dest.begin() as dconn:
            dconn.execute(text("PRAGMA foreign_keys = OFF"))
            for table in Base.metadata.sorted_tables:
                if table.name == "schema_version":
                    continue
                stable = source.tables.get(table.name)
                if stable is None:
                    counts[table.name] = 0
                    continue
                cols = [c.name for c in table.columns
                        if c.name in stable.columns]
                dconn.execute(table.delete())
                n = 0
                result = sconn.execute(select(*[stable.c[c] for c in cols]))
                while rows := result.fetchmany(BATCH):
                    dconn.execute(table.insert(), [
                        {c: _plain(v) for c, v in zip(cols, row)}
                        for row in rows])
                    n += len(rows)
                counts[table.name] = n
            _verify(sconn, dconn, source, counts)
        dest.dispose()
        os.replace(part, dest_path)
    except Exception as exc:
        dest.dispose()
        part.unlink(missing_ok=True)
        if isinstance(exc, LegacyError):
            raise
        raise LegacyError(
            f"Copying the 0.3 database into SQLite failed: {exc}. Nothing "
            "was changed; the old data is still in use. Free some disk "
            "space and restart, or report the error with the log file."
        ) from exc
    log.info("Copied PostgreSQL data into %s: %s", dest_path, counts)
    return counts


def _verify(sconn, dconn, source: MetaData, counts: dict[str, int]) -> None:
    for name, n in counts.items():
        if name not in source.tables:
            continue
        src_n = sconn.scalar(select(func.count()).select_from(
            source.tables[name]))
        if src_n != n:
            raise LegacyError(
                f"Table {name}: {src_n} rows in PostgreSQL but {n} copied. "
                "Nothing was changed; restart the app to try again.")
    if "transactions" in source.tables:
        from .models import Transaction
        src_sum = sconn.scalar(select(func.coalesce(func.sum(
            source.tables["transactions"].c.amount), 0)))
        dest_sum = dconn.scalar(select(func.sum(Transaction.amount)))
        if Decimal(str(src_sum)) != (dest_sum or Decimal("0.00")):
            raise LegacyError(
                f"The transaction total differs after copying ({src_sum} vs "
                f"{dest_sum}). Nothing was changed; report this with the log "
                "file.")
    broken = dconn.execute(text("PRAGMA foreign_key_check")).fetchall()
    if broken:
        raise LegacyError(
            f"{len(broken)} broken references after copying. Nothing was "
            "changed; report this with the log file.")


def _usable_bin(pg_bin: Path, data_dir: Path) -> Path:
    """Return a bin folder PostgreSQL can run from (Store-folder safe)."""
    if in_store_package(Path(pg_bin)):
        return relocate_binaries(Path(pg_bin), Path(data_dir))
    return Path(pg_bin)


def migrate_cluster(pg_bin: Path, data_dir: Path, dest_path: Path,
                    port: int) -> dict[str, int]:
    """Move the 0.3.x cluster in ``data_dir`` into ``dest_path``.

    Parameters
    ----------
    pg_bin : Path
        The bundled PostgreSQL ``bin`` folder.
    data_dir : Path
        The application data directory holding ``pgdata``.
    dest_path : Path
        The SQLite database file to create.
    port : int
        The preferred TCP port for the temporary server.

    Returns
    -------
    dict of str to int
        The rows copied per table.

    Raises
    ------
    LegacyError
        If PostgreSQL cannot be started or the copy fails its checks.
    """
    data_dir = Path(data_dir)
    if not pg_bin:
        raise LegacyError(
            "This data folder holds a database from PFI 0.3, but the bundled "
            "PostgreSQL needed to move it is missing. Reinstall PFI 0.4 "
            "(it includes PostgreSQL once for this step) and start it again.")
    log.info("Moving the 0.3 PostgreSQL database into SQLite")
    pg = EmbeddedPostgres(_usable_bin(pg_bin, data_dir), data_dir, port,
                          relocate=False)
    try:
        src = make_engine(pg.start())
    except Exception as exc:
        raise LegacyError(
            f"Could not start the 0.3 database to move it: {exc}. Nothing "
            "was changed. Restart PFI; if it keeps failing, send the log "
            "file from the logs folder.") from exc
    try:
        run_migrations(src)
        counts = copy_database(src, dest_path)
    finally:
        src.dispose()
        pg.stop()
    target = data_dir / RETIRED
    n = 1
    while target.exists():
        target = data_dir / f"{RETIRED}-{n}"
        n += 1
    (data_dir / "pgdata").rename(target)
    log.info("Old database kept (unused) in %s", target)
    return counts


def dump_to_sqlite(pg_bin: Path, data_dir: Path, dump: Path,
                   dest_path: Path) -> dict[str, int]:
    """Turn an old ``pg_dump`` backup into a SQLite database file.

    A throw-away cluster is created in a temporary folder, the dump is
    restored into it and then copied with ``copy_database``.

    Parameters
    ----------
    pg_bin : Path
        The bundled PostgreSQL ``bin`` folder.
    data_dir : Path
        The application data directory (for the Store-safe binary copy).
    dump : Path
        The ``.dump`` file written by PFI 0.3.
    dest_path : Path
        The SQLite file to create.

    Returns
    -------
    dict of str to int
        The rows copied per table.

    Raises
    ------
    LegacyError
        If PostgreSQL is missing or the dump cannot be read.
    """
    if not pg_bin:
        raise LegacyError(
            "Restoring a .dump backup from PFI 0.3 needs the bundled "
            "PostgreSQL, which is missing. Use PFI 0.4 from the Store or "
            "the installer.")
    tmp = Path(tempfile.mkdtemp(prefix="pfi-legacy-", dir=data_dir))
    pg = EmbeddedPostgres(_usable_bin(pg_bin, data_dir), tmp, _free_port(),
                          relocate=False)
    try:
        src = make_engine(pg.start())
        result = subprocess.run(
            [pg.tool("pg_restore"), "--no-owner", "--single-transaction",
             f"--dbname={pg.client_env()['PGDATABASE']}", str(dump)],
            env=pg.client_env(), capture_output=True, text=True,
            creationflags=NO_WINDOW)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-600:]
            raise LegacyError(
                f"The .dump backup could not be read: {detail}. Check that "
                "the file was written by PFI 0.3 'Back up now'.")
        run_migrations(src)
        counts = copy_database(src, dest_path)
        src.dispose()
        return counts
    finally:
        pg.stop()
        shutil.rmtree(tmp, ignore_errors=True)
