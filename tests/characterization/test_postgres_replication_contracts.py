from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select, text

from app.replication.events import (
    IncomingEvent,
    apply_event,
    process_pending,
    receive_event,
    replay_failed,
)
from app.replication.models import Candidato, EventoEntrada, EventoFallido, Reconciliacion
from app.replication.reconcile import reconcile
from app.replication.snapshot import poll_once, snapshot


def _replace_legacy_source_tables(db) -> None:
    db.execute(text("""
        DROP TABLE IF EXISTS public.revision,
          public.variables_proyecto_candidato,
          public.candidato_ubicacion,
          public.proyecto,
          public.usuario,
          public.punto_interes CASCADE
    """))
    db.execute(text("""
        CREATE TABLE public.usuario (
            id bigint PRIMARY KEY,
            creado_en timestamptz,
            eliminado_en timestamptz
        );
        CREATE TABLE public.proyecto (
            id_proyecto text PRIMARY KEY,
            creado_en timestamptz
        );
        CREATE TABLE public.candidato_ubicacion (
            id bigint PRIMARY KEY,
            id_proyecto text,
            estado text,
            grupo_flujo text,
            ultima_accion_en timestamptz,
            datos_visualizacion jsonb
        );
        CREATE TABLE public.revision (
            id bigint PRIMARY KEY,
            id_candidato bigint,
            accion text,
            comentario text,
            creado_en timestamptz
        );
        CREATE TABLE public.variables_proyecto_candidato (
            id bigint PRIMARY KEY,
            id_candidato bigint,
            actualizado_en timestamptz
        );
        CREATE TABLE public.punto_interes (
            id bigint PRIMARY KEY
        )
    """))
    db.commit()


def test_snapshot_resume_polling_and_reconciliation_contract(
    db,
    temporary_postgres_url,
    tmp_path,
):
    _replace_legacy_source_tables(db)
    db.execute(text("""
        INSERT INTO public.candidato_ubicacion
          (id, estado, grupo_flujo, ultima_accion_en, datos_visualizacion)
        VALUES (
          990601,
          'pendiente',
          'pendiente',
          '2026-08-20T12:00:00+00:00',
          '{"ID": 990601, "Unidad": "SNAPSHOT"}'::jsonb
        )
    """))
    db.commit()
    legacy = create_engine(temporary_postgres_url)
    try:
        first = snapshot(legacy, db, dry_run=False, batch_size=1)
        first_applied = process_pending(db, limit=100)
        inbox_after_first = db.scalar(select(func.count(EventoEntrada.id)))

        repeated = snapshot(legacy, db, dry_run=False, batch_size=1)
        inbox_after_repeated = db.scalar(select(func.count(EventoEntrada.id)))

        db.execute(text("""
            INSERT INTO public.candidato_ubicacion
              (id, estado, grupo_flujo, ultima_accion_en, datos_visualizacion)
            VALUES (
              990602,
              'observacion',
              'observacion',
              NULL,
              '{"ID": 990602, "Unidad": "POLLING NULL"}'::jsonb
            )
        """))
        db.commit()
        polled = poll_once(legacy, db, dry_run=False, limit=100)
        polling_applied = process_pending(db, limit=100)

        report = reconcile(
            legacy,
            db,
            dry_run=False,
            output_dir=tmp_path / "reconciliation",
        )
    finally:
        legacy.dispose()

    assert first["tables"]["candidato_ubicacion"]["read"] == 1
    assert first_applied["aplicados"] == 2
    assert db.scalar(select(func.count(Candidato.id))) == 2
    assert repeated["tables"]["candidato_ubicacion"]["queued"] == 0
    assert inbox_after_repeated == inbox_after_first
    assert polled["consistency"] == "eventual"
    assert polled["tables"]["candidato_ubicacion"] == 0
    assert polled["tables"]["candidato_ubicacion_hash_scan"] == 2
    assert polled["tables"]["candidato_ubicacion_hash_queued"] >= 1
    assert polling_applied["aplicados"] >= 1
    assert report["difference_count"] == 0
    assert report["source"]["candidates"] == 2
    assert report["target"]["candidates"] == 2
    assert (tmp_path / "reconciliation" / f"reconciliation-{report['id']}.json").is_file()
    assert (tmp_path / "reconciliation" / f"reconciliation-{report['id']}.csv").is_file()
    assert db.scalar(select(func.count(Reconciliacion.id))) == 1


def test_dead_letter_replay_contract(db):
    event, _ = receive_event(db, IncomingEvent(
        origin_id="characterization:missing-candidate",
        table="revision",
        operation="INSERT",
        key="990699",
        order=990699,
        occurred_at=datetime.now(timezone.utc),
        payload={
            "id": 990699,
            "id_candidato": 990699,
            "accion": "reject",
        },
        candidate_legacy_id="990699",
    ))
    db.commit()

    for _ in range(5):
        with pytest.raises(LookupError):
            apply_event(db, event.id)

    failed = db.get(EventoEntrada, event.id)
    dead_letter = db.scalar(select(EventoFallido).where(
        EventoFallido.evento_entrada_id == event.id
    ))
    assert failed.estado == "FALLIDO"
    assert dead_letter.resuelto_en is None

    assert replay_failed(db, event.id) == 1
    db.refresh(failed)
    db.refresh(dead_letter)
    assert failed.estado == "PENDIENTE"
    assert failed.siguiente_intento_en is None
    assert dead_letter.resuelto_en is not None
