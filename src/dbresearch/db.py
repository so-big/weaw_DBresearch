"""Database engine and per-request sessions.

The engine is created lazily so tests (and the worker) can point it at another database
with `configure_engine(url)` before first use.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from dbresearch.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def configure_engine(url: str | None = None) -> Engine:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url or get_settings().database_url, pool_pre_ping=True)
    _factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine if _engine is not None else configure_engine()


def new_session() -> Session:
    get_engine()
    assert _factory is not None
    return _factory()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request; services commit explicitly."""
    session = new_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
