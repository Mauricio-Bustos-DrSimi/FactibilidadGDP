from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cli_environment(database_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(PROJECT_ROOT),
        "DATABASE_URL": database_url,
        "LEGACY_DATABASE_URL": database_url,
        "SOURCE_DATABASE_URL": database_url,
        "CDC_DATABASE_URL": "",
        "ALEMBIC_MANAGED_SCHEMA": "true",
        "TARGET_SEARCH_PATH": "pruebas_gestor,factibilidad,gestor,integracion,public",
        "SHADOW_MODE": "true",
        "GESTOR_TEST_MODE": "true",
        "LEGACY_SYNC_ENABLED": "true",
        "REPLICATION_MODE": "polling",
        "EMAIL_DELIVERY_ENABLED": "false",
    })
    return environment


def _run_cli(database_url: str, cwd: Path, *arguments: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "app.replication.cli", *arguments],
        cwd=cwd,
        env=_cli_environment(database_url),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cli_dry_run_apply_and_replay_do_not_mutate_temporary_postgres(
    temporary_postgres_url,
    tmp_path,
):
    applied = _run_cli(temporary_postgres_url, tmp_path, "apply", "--dry-run")
    replayed = _run_cli(temporary_postgres_url, tmp_path, "replay", "--dry-run")

    assert applied == {"dry_run": True, "message": "No events were applied"}
    assert replayed == {
        "dry_run": True,
        "message": "No failed events were replayed",
    }


def test_cli_reconcile_dry_run_reads_source_and_writes_no_report(
    db,
    temporary_postgres_url,
    tmp_path,
):
    db.execute(text("""
        CREATE TABLE public.candidato_ubicacion (
            id bigint PRIMARY KEY,
            estado text,
            datos_visualizacion jsonb
        )
    """))
    db.execute(text("""
        CREATE TABLE public.revision (
            id bigint PRIMARY KEY,
            id_candidato bigint,
            accion text,
            comentario text,
            creado_en timestamptz
        )
    """))
    db.execute(text("""
        CREATE TABLE public.usuario (
            id text PRIMARY KEY
        )
    """))
    db.execute(text("""
        CREATE TABLE public.variables_proyecto_candidato (
            id bigint PRIMARY KEY,
            id_candidato bigint
        )
    """))
    db.execute(text("""
        INSERT INTO public.candidato_ubicacion
          (id, estado, datos_visualizacion)
        VALUES (990401, 'pendiente', '{"ID": 990401}'::jsonb)
    """))
    db.commit()

    report = _run_cli(
        temporary_postgres_url,
        tmp_path,
        "reconcile",
        "--dry-run",
    )

    assert report["dry_run"] is True
    assert report["source"]["candidates"] == 1
    assert report["target"]["candidates"] == 0
    assert report["difference_count"] == 1
    assert report["differences"] == [{
        "entity": "candidate",
        "legacy_id": "990401",
        "field": "presence",
        "source": "present",
        "target": "missing",
    }]
    assert list(tmp_path.rglob("reconciliation-*.json")) == []
    assert list(tmp_path.rglob("reconciliation-*.csv")) == []
    assert db.scalar(text("SELECT count(*) FROM integracion.reconciliacion")) == 0
