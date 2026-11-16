"""Minimal, ordered schema migrations tracked in ``schema_version``.

Each migration is applied once, in order, inside a transaction. Append new
migrations to ``MIGRATIONS``; never edit one that has shipped. A brand-new
database is created from the current models in one step and every
migration is recorded as applied. Migrations 1-3 come from the PostgreSQL
era (0.1-0.3) and only ran when 0.4 moved a 0.3 database to SQLite.
"""
import logging
from collections.abc import Callable

from sqlalchemy import Connection, Engine, inspect, select, text

from . import models
from .db import Base

log = logging.getLogger(__name__)


def _initial_schema(conn: Connection) -> None:
    Base.metadata.create_all(conn)


def _import_presets(conn: Connection) -> None:
    models.ImportPreset.__table__.create(conn, checkfirst=True)


def _v03_automation_investments(conn: Connection) -> None:
    for stmt in (
        "ALTER TABLE settings ALTER COLUMN value TYPE TEXT",
        "ALTER TABLE recurring_items ADD COLUMN IF NOT EXISTS auto_post "
        "BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE recurring_items ADD COLUMN IF NOT EXISTS remind_days "
        "INTEGER NOT NULL DEFAULT 3",
        "ALTER TABLE recurring_items ADD COLUMN IF NOT EXISTS last_posted "
        "DATE",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS recurring_id "
        "INTEGER REFERENCES recurring_items(id) ON DELETE SET NULL",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_source "
        "VARCHAR(10)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS price_source "
        "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS price_symbol "
        "VARCHAR(64)",
    ):
        conn.execute(text(stmt))


def _v04_splits_tags_attachments(conn: Connection) -> None:
    for model in (models.TransactionSplit, models.Tag,
                  models.TransactionTag, models.Attachment):
        model.__table__.create(conn, checkfirst=True)


def _v05_reconcile_debts(conn: Connection) -> None:
    for model in (models.Reconciliation, models.DebtTerms):
        model.__table__.create(conn, checkfirst=True)
    columns = {c["name"] for c in inspect(conn).get_columns("transactions")}
    if "cleared" not in columns:
        conn.execute(text("ALTER TABLE transactions ADD COLUMN cleared "
                          "BOOLEAN NOT NULL DEFAULT 0"))
    if "reconciliation_id" not in columns:
        conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN reconciliation_id INTEGER "
            "REFERENCES reconciliations(id) ON DELETE SET NULL"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_transactions_reconciliation_id "
            "ON transactions (reconciliation_id)"))


_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"
_NEW_UID = "lower(hex(randomblob(16)))"


def _add_column(conn: Connection, table: str, ddl: str) -> None:
    name = ddl.split()[0]
    if name not in {c["name"] for c in inspect(conn).get_columns(table)}:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _v06_envelopes_sync(conn: Connection) -> None:
    for model in (models.BudgetAssignment, models.BudgetTarget,
                  models.PeriodBudget, models.PeriodBudgetCategory,
                  models.Iou, models.IouPayment, models.SyncTombstone):
        model.__table__.create(conn, checkfirst=True)
    _add_column(conn, "categories", "icon VARCHAR(40)")
    _add_column(conn, "transactions",
                "reviewed BOOLEAN NOT NULL DEFAULT 1")
    for table in models.SYNCED_TABLES:
        _add_column(conn, table, "uid VARCHAR(32)")
        _add_column(conn, table, "updated_at DATETIME")
        conn.execute(text(
            f"UPDATE {table} SET uid = coalesce(uid, {_NEW_UID}), "
            f"updated_at = coalesce(updated_at, {_NOW})"))


def _v07_sync_state(conn: Connection) -> None:
    for model in (models.SyncState, models.SyncSeen, models.SyncAlias,
                  models.SyncPending):
        model.__table__.create(conn, checkfirst=True)


def ensure_sync_triggers(conn: Connection) -> None:
    """Create the uid index and the sync triggers of every synced table.

    The triggers give rows written outside the ORM (migrations, restores,
    bulk statements) a ``uid`` and an ``updated_at``, refresh
    ``updated_at`` on every change and record deletions in
    ``sync_tombstones``. Safe to run on every start.

    Parameters
    ----------
    conn : Connection
        The open connection to the application database.
    """
    for t in models.SYNCED_TABLES:
        conn.execute(text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{t}_uid ON {t} (uid)"))
        conn.execute(text(
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_ins AFTER INSERT ON {t} "
            f"WHEN NEW.uid IS NULL OR NEW.updated_at IS NULL BEGIN "
            f"UPDATE {t} SET uid = coalesce(NEW.uid, {_NEW_UID}), "
            f"updated_at = coalesce(NEW.updated_at, {_NOW}) "
            f"WHERE rowid = NEW.rowid; END"))
        conn.execute(text(
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_upd AFTER UPDATE ON {t} "
            f"WHEN NEW.updated_at IS OLD.updated_at BEGIN "
            f"UPDATE {t} SET updated_at = {_NOW} WHERE rowid = NEW.rowid; "
            f"END"))
        conn.execute(text(
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_del AFTER DELETE ON {t} "
            f"WHEN OLD.uid IS NOT NULL BEGIN "
            f"INSERT INTO sync_tombstones (table_name, uid, deleted_at) "
            f"VALUES ('{t}', OLD.uid, {_NOW}); END"))


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema", _initial_schema),
    (2, "import presets", _import_presets),
    (3, "automation and investment pricing", _v03_automation_investments),
    (4, "splits, tags and attachments", _v04_splits_tags_attachments),
    (5, "reconciliation and debt terms", _v05_reconcile_debts),
    (6, "envelope budgets, IOUs, review queue and sync ids",
     _v06_envelopes_sync),
    (7, "sync with the phone app", _v07_sync_state),
]


def run_migrations(engine: Engine) -> int:
    """Apply pending migrations and return the resulting schema version.

    Parameters
    ----------
    engine : Engine
        The engine connected to the application database.

    Returns
    -------
    int
        The schema version after all migrations have been applied.
    """
    with engine.begin() as conn:
        fresh = not inspect(conn).get_table_names()
        if fresh:
            Base.metadata.create_all(conn)
            conn.execute(models.SchemaVersion.__table__.insert(), [
                {"version": v, "name": n} for v, n, _ in MIGRATIONS])
            log.info("Created a new database (schema v%s)",
                     MIGRATIONS[-1][0])
        models.SchemaVersion.__table__.create(conn, checkfirst=True)
        done = set(conn.scalars(select(models.SchemaVersion.version)))
    for version, name, func in MIGRATIONS:
        if version in done:
            continue
        log.info("Applying migration %s: %s", version, name)
        with engine.begin() as conn:
            func(conn)
            conn.execute(models.SchemaVersion.__table__.insert().values(
                version=version, name=name))
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            ensure_sync_triggers(conn)
    current = max(v for v, _, _ in MIGRATIONS)
    tables = set(inspect(engine).get_table_names())
    missing = set(Base.metadata.tables) - tables
    if missing:
        raise RuntimeError(
            f"Database schema is incomplete; missing tables: "
            f"{sorted(missing)}. A migration may have been skipped. Back up "
            "the data directory and add a migration that creates them.")
    return current
