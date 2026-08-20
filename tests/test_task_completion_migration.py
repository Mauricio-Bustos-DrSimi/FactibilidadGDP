from __future__ import annotations

import os
import re
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_completed_tasks_are_backfilled_with_their_last_known_update():
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not configured")
    name = f"factibilidad_test_{uuid.uuid4().hex}"
    assert re.fullmatch(r"factibilidad_test_[0-9a-f]{32}", name)
    parsed = make_url(admin_url)
    target_url = parsed.set(database=name)
    admin = create_engine(parsed, isolation_level="AUTOCOMMIT")
    target = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
        config = Config("alembic.ini")
        config.attributes["database_url"] = target_url.render_as_string(hide_password=False)
        command.upgrade(config, "20260820_06")
        target = create_engine(target_url)
        with target.begin() as connection:
            connection.execute(text("""
                INSERT INTO factibilidad.tarea_local
                  (id_candidato, clave_grupo, clave_tarea, estado, actualizado_en)
                VALUES
                  (1, 'grupo', 'terminada', 'realizado', '2026-08-18 10:00:00+00'),
                  (1, 'grupo', 'pendiente', 'en_proceso', '2026-08-19 10:00:00+00')
            """))
        target.dispose()
        target = None
        command.upgrade(config, "head")
        target = create_engine(target_url)
        with target.connect() as connection:
            rows = connection.execute(text("""
                SELECT clave_tarea, completado_en
                FROM factibilidad.tarea_local ORDER BY clave_tarea
            """)).all()
            indexed = connection.scalar(text("""
                SELECT EXISTS (
                  SELECT 1 FROM pg_indexes
                  WHERE schemaname='factibilidad' AND tablename='tarea_local'
                    AND indexname='ix_tarea_local_completado'
                )
            """))
        assert rows[0][0] == "pendiente" and rows[0][1] is None
        assert rows[1][0] == "terminada"
        assert rows[1][1].isoformat() == "2026-08-18T10:00:00+00:00"
        assert indexed is True
    finally:
        if target is not None:
            target.dispose()
        with admin.connect() as connection:
            connection.execute(text("""
                SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                WHERE datname=:name AND pid <> pg_backend_pid()
            """), {"name": name})
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()
