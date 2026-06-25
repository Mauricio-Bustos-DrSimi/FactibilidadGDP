"""Database engine / session setup.

The SQLite file lives at ./data/site_swiper.db relative to the project root and is
created automatically on first run (along with the ./data directory).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Project root = parent of the ``app`` package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Allow override (handy for tests) but default to the local file.
DB_PATH = os.environ.get("SITE_SWIPER_DB", str(DATA_DIR / "site_swiper.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread=False because FastAPI may touch the session from threadpool workers.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Import models first so they register on ``Base.metadata``."""
    from app import models  # noqa: F401  (registers models)

    Base.metadata.create_all(bind=engine)
