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


def _normalize_database_url(url: str) -> str:
    """Normalize provider URLs for SQLAlchemy without logging credentials."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _database_url() -> str:
    explicit = os.getenv("DATABASE_URL") or os.getenv("SITE_SWIPER_DATABASE_URL")
    if explicit:
        return _normalize_database_url(explicit)
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
IS_POSTGRES = DATABASE_URL.startswith(("postgresql", "postgres"))


def _engine_connect_args() -> dict:
    if IS_SQLITE:
        return {"check_same_thread": False}
    if IS_POSTGRES:
        timeout = os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")
        try:
            connect_timeout = max(1, int(timeout))
        except ValueError:
            connect_timeout = 10
        return {"connect_timeout": connect_timeout}
    return {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_engine_connect_args(),
    pool_pre_ping=True,
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
        "grupo_flujo": "VARCHAR",
        "ultima_accion": "VARCHAR",
        "ultima_accion_en": "TIMESTAMP",
        "rol_ultimo_actor": "VARCHAR",
        "comentario_ultimo_rechazo": "TEXT",
        "sugerido_en": "TIMESTAMP",
        "aprobado_en": "TIMESTAMP",
        "rechazado_en": "TIMESTAMP",
        "proyecto_en": "TIMESTAMP",
        "omitido_en": "TIMESTAMP",
        "devuelto_en": "TIMESTAMP",
        "reabierto_en": "TIMESTAMP",
        "rechazado_desde_aprobado_en": "TIMESTAMP",
        "rechazado_desde_proyecto_en": "TIMESTAMP",
    }
    inspector = inspect(engine)
    if not inspector.has_table("candidato_ubicacion"):
        return
    existing = {col["name"] for col in inspector.get_columns("candidato_ubicacion")}
    with engine.begin() as conn:
        for name, sql_type in columns.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE candidato_ubicacion ADD COLUMN "{name}" {sql_type}'))
        indexes = [
            ("idx_candidato_ubicacion_grupo_flujo", "candidato_ubicacion", "grupo_flujo"),
            ("idx_candidato_ubicacion_etapa_actual", "candidato_ubicacion", "etapa_actual"),
            ("idx_candidato_ubicacion_estado", "candidato_ubicacion", "estado"),
            ("idx_candidato_ubicacion_ultima_accion_en", "candidato_ubicacion", "ultima_accion_en"),
            ("idx_revision_id_candidato", "revision", "id_candidato"),
            ("idx_revision_creado_en", "revision", "creado_en"),
            ("idx_revision_candidato_accion_etapa", "revision", "id_candidato, accion, etapa"),
        ]
        for index_name, table_name, expression in indexes:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({expression})'
            ))
    if inspector.has_table("variables_proyecto_candidato"):
        variable_columns = {
            "comuna": "VARCHAR",
            "provincia": "VARCHAR",
            "region": "VARCHAR",
        }
        existing_variables = {
            col["name"] for col in inspect(engine).get_columns("variables_proyecto_candidato")
        }
        with engine.begin() as conn:
            for name, sql_type in variable_columns.items():
                if name not in existing_variables:
                    conn.execute(text(f'ALTER TABLE variables_proyecto_candidato ADD COLUMN "{name}" {sql_type}'))
    if inspector.has_table("usuario"):
        existing_users = {col["name"] for col in inspect(engine).get_columns("usuario")}
        user_columns = {
            "division_comercial": "VARCHAR",
            "cargo": "VARCHAR",
            "correos_supervisores": "TEXT",
            "organigrama_x": "FLOAT",
            "organigrama_y": "FLOAT",
            "eliminado_en": "TIMESTAMP",
        }
        with engine.begin() as conn:
            for name, sql_type in user_columns.items():
                if name not in existing_users:
                    conn.execute(text(f'ALTER TABLE "usuario" ADD COLUMN "{name}" {sql_type}'))
