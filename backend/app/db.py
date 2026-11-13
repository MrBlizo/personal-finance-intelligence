"""Database engine, session factory and declarative base.

The application database is a single SQLite file (``<data_dir>/pfi.sqlite``
by default). The engine is created at startup (``init_engine``).
"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine: Engine | None = None


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def sqlite_url(path: Path) -> str:
    """Return the SQLAlchemy URL of the SQLite file ``path``.

    Parameters
    ----------
    path : Path
        The database file.
    """
    return f"sqlite:///{Path(path).resolve().as_posix()}"


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("PRAGMA synchronous = NORMAL")
    cur.execute("PRAGMA busy_timeout = 30000")
    cur.close()


def make_engine(url: str) -> Engine:
    """Create an engine; SQLite gets foreign keys, WAL and a lock timeout.

    Parameters
    ----------
    url : str
        The SQLAlchemy database URL.
    """
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={
            "check_same_thread": False, "timeout": 30})
        event.listen(engine, "connect", _sqlite_pragmas)
        return engine
    return create_engine(url, pool_pre_ping=True)


def init_engine(url: str) -> Engine:
    """Create the global engine and bind the session factory to it.

    Parameters
    ----------
    url : str
        The SQLAlchemy database URL.

    Returns
    -------
    Engine
        The newly created engine.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(url)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    """Return the global engine, raising if startup has not run."""
    if _engine is None:
        raise RuntimeError(
            "Database engine is not initialised: the application startup "
            "did not run. Start the API through app.main:app or call "
            "init_engine() first.")
    return _engine


def get_db() -> Iterator[Session]:
    """Yield a database session and close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
