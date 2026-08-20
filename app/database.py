"""Database engine / session setup."""
from __future__ import annotations

import os
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, select, text
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
    alembic_managed = os.getenv("ALEMBIC_MANAGED_SCHEMA", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if alembic_managed:
        explicit_target = os.getenv("DATABASE_URL")
        if not explicit_target:
            raise RuntimeError("DATABASE_URL is required for the Alembic-managed target")
        return _normalize_database_url(explicit_target)
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
        args = {"connect_timeout": connect_timeout}
        if os.getenv("ALEMBIC_MANAGED_SCHEMA", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }:
            search_path = os.getenv(
                "TARGET_SEARCH_PATH",
                "pruebas_gestor,factibilidad,gestor,integracion,public",
            )
            args["options"] = f"-csearch_path={search_path}"
        return args
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
    if os.getenv("ALEMBIC_MANAGED_SCHEMA", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        # Production schema changes are exclusively Alembic-owned. This check
        # fails closed instead of silently creating or altering objects.
        with engine.connect() as conn:
            revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
            if not revision:
                raise RuntimeError("Alembic schema is not initialized")
        return
    from app import models  # noqa: F401  (registers models)

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns()
    _run_data_migrations()


def _projection_id_number(display_data: dict) -> int | None:
    for key, value in (display_data or {}).items():
        normalized = unicodedata.normalize("NFKD", str(key))
        normalized = re.sub(r"[^a-z0-9]", "", normalized.encode("ascii", "ignore").decode("ascii").lower())
        if normalized not in {"id", "idproyeccion"} or value is None:
            continue
        match = re.fullmatch(r"\s*(\d+)(?:\.0+)?\s*", str(value))
        if match:
            return int(match.group(1))
    return None


def migrate_rejected_candidates_to_observation(db, min_projection_id: int = 690) -> int:
    """Move the requested legacy rejection range into Observación."""
    from app import models

    migrated = 0
    candidates = db.scalars(select(models.LocationCandidate)).all()
    for candidate in candidates:
        current_group = candidate.workflow_group or candidate.status
        if current_group not in {"rechazado", "rejected"}:
            continue
        projection_id = _projection_id_number(candidate.display_data or {})
        if projection_id is None or projection_id < min_projection_id:
            continue
        candidate.status = "observacion"
        candidate.workflow_group = "observacion"
        migrated += 1
    if migrated:
        db.commit()
    return migrated


def _run_data_migrations() -> None:
    migration_key = "rejected_projection_690_to_observation_v1"
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS migracion_app "
            "(clave VARCHAR(160) PRIMARY KEY, aplicado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        applied = conn.execute(
            text("SELECT clave FROM migracion_app WHERE clave = :key"),
            {"key": migration_key},
        ).first()
    if applied:
        return

    db = SessionLocal()
    try:
        migrate_rejected_candidates_to_observation(db)
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO migracion_app (clave) VALUES (:key)"),
                {"key": migration_key},
            )
    finally:
        db.close()


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
            "flujo_franquicia": "VARCHAR",
            "franquiciado_nombre": "VARCHAR",
            "franquiciado_telefono": "VARCHAR",
            "franquiciado_email": "VARCHAR",
            "tiendas_anclas": "TEXT",
            "proyeccion_supervisor": "VARCHAR",
            "proyeccion_jefe_comercial": "VARCHAR",
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
