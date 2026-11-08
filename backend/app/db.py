"""Database engine, session factory and declarative base.

The engine is created at startup (``init_engine``) because in embedded
mode the connection URL is only known once PostgreSQL has started.
"""
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine: Engine | None = None


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


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
    _engine = create_engine(url, pool_pre_ping=True)
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
