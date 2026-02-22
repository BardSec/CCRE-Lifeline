from __future__ import annotations

from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _make_engine(database_url: str):
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


# Populated by the app factory after config is loaded.
SessionLocal: sessionmaker | None = None


def init_db(database_url: str) -> None:
    global SessionLocal
    engine = _make_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Return the request-scoped DB session (creates one if needed)."""
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


def close_db(error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
