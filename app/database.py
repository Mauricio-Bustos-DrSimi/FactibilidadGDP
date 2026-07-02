"""Database engine / session setup."""
from __future__ import annotations

import os
import json
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Project root = parent of the ``app`` package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Allow override (handy for tests) but default to the local file.
DB_PATH = os.environ.get("SITE_SWIPER_DB", str(DATA_DIR / "site_swiper.db"))


def _postgres_database_url() -> str:
    user = quote_plus(os.getenv("POSTGRES_USER", ""))
    password = quote_plus(os.getenv("POSTGRES_PASSWORD", ""))
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


def _database_url() -> str:
    explicit = os.getenv("SITE_SWIPER_DATABASE_URL") or os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    if os.getenv("SITE_SWIPER_DB"):
        return f"sqlite:///{DB_PATH}"
    use_postgres = os.getenv("SITE_SWIPER_USE_POSTGRES", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_postgres:
        return _postgres_database_url()
    return f"sqlite:///{DB_PATH}"


DATABASE_URL = _database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
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
    _ensure_runtime_columns()


def _ensure_runtime_columns() -> None:
    """Add lightweight columns needed by newer app versions.

    SQLAlchemy create_all creates missing tables but does not alter existing
    tables, so local/Postgres upgrades need a small compatibility pass.
    """
    columns = {
        "workflow_group": "VARCHAR",
        "last_action": "VARCHAR",
        "last_action_at": "TIMESTAMP",
        "last_actor_role": "VARCHAR",
        "last_reject_note": "TEXT",
        "suggested_at": "TIMESTAMP",
        "approved_at": "TIMESTAMP",
        "rejected_at": "TIMESTAMP",
        "project_at": "TIMESTAMP",
        "skipped_at": "TIMESTAMP",
        "returned_at": "TIMESTAMP",
        "reopened_at": "TIMESTAMP",
        "rejected_from_approved_at": "TIMESTAMP",
        "rejected_from_project_at": "TIMESTAMP",
    }
    inspector = inspect(engine)
    if not inspector.has_table("location_candidate"):
        return
    existing = {col["name"] for col in inspector.get_columns("location_candidate")}
    with engine.begin() as conn:
        for name, sql_type in columns.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE location_candidate ADD COLUMN "{name}" {sql_type}'))
        indexes = [
            ("idx_location_candidate_workflow_group", "location_candidate", "workflow_group"),
            ("idx_location_candidate_current_stage", "location_candidate", "current_stage"),
            ("idx_location_candidate_status", "location_candidate", "status"),
            ("idx_location_candidate_last_action_at", "location_candidate", "last_action_at"),
            ("idx_review_candidate_id", "review", "candidate_id"),
            ("idx_review_created_at", "review", "created_at"),
            ("idx_review_candidate_action_stage", "review", "candidate_id, action, stage"),
        ]
        for index_name, table_name, expression in indexes:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({expression})'
            ))
    if inspector.has_table("candidate_project_variables"):
        variable_columns = {
            "comuna": "VARCHAR",
            "provincia": "VARCHAR",
            "region": "VARCHAR",
        }
        existing_variables = {
            col["name"] for col in inspect(engine).get_columns("candidate_project_variables")
        }
        with engine.begin() as conn:
            for name, sql_type in variable_columns.items():
                if name not in existing_variables:
                    conn.execute(text(f'ALTER TABLE candidate_project_variables ADD COLUMN "{name}" {sql_type}'))
