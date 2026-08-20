from __future__ import annotations

import os
import re
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def temporary_postgres_url():
    """Create a disposable PostgreSQL database; never reuse an application DB."""
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not configured")
    name = f"factibilidad_test_{uuid.uuid4().hex}"
    assert re.fullmatch(r"factibilidad_test_[0-9a-f]{32}", name)
    parsed = make_url(admin_url)
    target_url = parsed.set(database=name)
    admin = create_engine(parsed, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    try:
        config = Config("alembic.ini")
        config.attributes["database_url"] = target_url.render_as_string(hide_password=False)
        command.upgrade(config, "head")
        yield target_url.render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text("""
                SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                WHERE datname=:name AND pid <> pg_backend_pid()
            """), {"name": name})
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@pytest.fixture
def db(temporary_postgres_url):
    engine = create_engine(temporary_postgres_url)
    with engine.begin() as connection:
        connection.execute(text("""
            TRUNCATE TABLE
              pruebas_gestor.revision_local,
              pruebas_gestor.variable_override,
              pruebas_gestor.candidato_override,
              factibilidad.entrega, factibilidad.tarea_local,
              factibilidad.decision_local, factibilidad.visto_bueno_local,
              gestor.transicion_estado, gestor.actividad_candidato,
              gestor.variable_proyecto_version, gestor.documento_candidato,
              gestor.notificacion_envio, gestor.candidato, gestor.usuario,
              gestor.proyecto_importacion, gestor.punto_interes,
              integracion.evento_fallido, integracion.evento_salida,
              integracion.checkpoint_cdc, integracion.reconciliacion,
              integracion.migracion_control, integracion.evento_entrada
            RESTART IDENTITY CASCADE
        """))
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    engine.dispose()
