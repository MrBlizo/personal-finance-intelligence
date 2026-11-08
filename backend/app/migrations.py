"""Minimal, ordered schema migrations tracked in ``schema_version``.

Each migration is applied once, in order, inside a transaction. Append new
migrations to ``MIGRATIONS``; never edit one that has shipped.
"""
import logging
from collections.abc import Callable

from sqlalchemy import Connection, Engine, inspect, select

from . import models
from .db import Base

log = logging.getLogger(__name__)


def _initial_schema(conn: Connection) -> None:
    Base.metadata.create_all(conn)


def _import_presets(conn: Connection) -> None:
    models.ImportPreset.__table__.create(conn, checkfirst=True)


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema", _initial_schema),
    (2, "import presets", _import_presets),
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
    current = max(v for v, _, _ in MIGRATIONS)
    tables = set(inspect(engine).get_table_names())
    missing = set(Base.metadata.tables) - tables
    if missing:
        raise RuntimeError(
            f"Database schema is incomplete; missing tables: "
            f"{sorted(missing)}. A migration may have been skipped. Back up "
            "the data directory and add a migration that creates them.")
    return current
