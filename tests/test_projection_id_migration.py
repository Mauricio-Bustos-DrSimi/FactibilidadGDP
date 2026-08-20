from __future__ import annotations

import json
import os
import re
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_projection_id_is_backfilled_from_historical_json():
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
        command.upgrade(config, "20260820_05")
        target = create_engine(target_url)
        with target.begin() as connection:
            for candidate_id in (847, 848):
                display = {"ID Proyección": 872, "Unidad": f"LOCAL {candidate_id}"}
                connection.execute(text("""
                    INSERT INTO gestor.candidato
                      (legacy_candidato_id,estado_actual_id,estado_origen,
                       certeza_mapeo,version_origen,datos,payload_origen,hash_origen)
                    VALUES (:legacy_id,1,'pendiente','EXACTA',1,
                            CAST(:display AS jsonb),'{}'::jsonb,:hash)
                """), {
                    "legacy_id": str(candidate_id),
                    "display": json.dumps(display, ensure_ascii=False),
                    "hash": f"hash-{candidate_id}",
                })
        target.dispose()
        target = None
        command.upgrade(config, "head")
        target = create_engine(target_url)
        with target.connect() as connection:
            values = list(connection.scalars(text("""
                SELECT id_proyeccion FROM gestor.candidato
                ORDER BY legacy_candidato_id
            """)))
            nullable = connection.scalar(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema='gestor' AND table_name='candidato'
                  AND column_name='id_proyeccion'
            """))
            indexed = connection.scalar(text("""
                SELECT EXISTS (
                  SELECT 1 FROM pg_indexes
                  WHERE schemaname='gestor' AND tablename='candidato'
                    AND indexname='ix_gestor_candidato_id_proyeccion'
                )
            """))
        assert values == ["872", "872"]
        assert nullable == "NO"
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
