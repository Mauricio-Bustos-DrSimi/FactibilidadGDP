from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app.replication.events import IncomingEvent, apply_event, process_pending, receive_event
from app.replication.models import (
    ActividadCandidato,
    Candidato,
    EventoEntrada,
    TransicionEstado,
    VariableProyectoVersion,
)


def candidate_event(order: int = 1):
    return IncomingEvent(
        origin_id=f"test:candidate:{order}", table="candidato_ubicacion",
        operation="INSERT", key="847", order=order,
        occurred_at=datetime.now(timezone.utc),
        payload={"id": 847, "estado": "pendiente", "datos_visualizacion": {"ID": 847}},
        candidate_legacy_id="847",
    )


def test_duplicate_delivery_has_exactly_once_effect(db):
    first, created = receive_event(db, candidate_event())
    db.commit()
    duplicate, created_again = receive_event(db, candidate_event())
    assert created is True and created_again is False and first.id == duplicate.id
    assert apply_event(db, first.id) is True
    assert apply_event(db, first.id) is False
    assert db.scalar(select(func.count(Candidato.id))) == 1
    assert db.scalar(select(func.count(ActividadCandidato.id))) == 1


def test_out_of_order_receipt_is_applied_in_source_order(db):
    base, _ = receive_event(db, candidate_event(1))
    db.commit()
    apply_event(db, base.id)
    later = datetime.now(timezone.utc) + timedelta(seconds=2)
    events = [
        IncomingEvent("test:review:3", "revision", "INSERT", "3", 3, later,
                      {"id": 3, "id_candidato": 847, "accion": "project"}, candidate_legacy_id="847"),
        IncomingEvent("test:review:2", "revision", "INSERT", "2", 2, later - timedelta(seconds=1),
                      {"id": 2, "id_candidato": 847, "accion": "accept"}, candidate_legacy_id="847"),
    ]
    for incoming in events:
        receive_event(db, incoming)
    db.commit()
    result = process_pending(db)
    transitions = list(db.scalars(select(TransicionEstado).order_by(TransicionEstado.orden_origen)))
    assert result["aplicados"] == 2
    assert [row.orden_origen for row in transitions] == [2, 3]


def test_failure_rolls_back_effect_and_is_retryable(db):
    incoming = IncomingEvent(
        "test:missing", "revision", "INSERT", "99", 99, datetime.now(timezone.utc),
        {"id": 99, "id_candidato": 99999, "accion": "reject"}, candidate_legacy_id="99999",
    )
    event, _ = receive_event(db, incoming)
    db.commit()
    try:
        apply_event(db, event.id)
    except LookupError:
        pass
    stored = db.get(EventoEntrada, event.id)
    assert stored.estado == "REINTENTO"
    assert db.scalar(select(func.count(TransicionEstado.id))) == 0


def test_variables_are_versioned(db):
    base, _ = receive_event(db, candidate_event())
    db.commit()
    apply_event(db, base.id)
    for version, value in ((2, "A"), (3, "B")):
        event, _ = receive_event(db, IncomingEvent(
            f"test:variables:{version}", "variables_proyecto_candidato", "UPSERT", "1",
            version, datetime.now(timezone.utc),
            {"id": 1, "id_candidato": 847, "unidad": value}, candidate_legacy_id="847",
        ))
        db.commit()
        apply_event(db, event.id)
    rows = list(db.scalars(select(VariableProyectoVersion).order_by(VariableProyectoVersion.version)))
    assert [row.version for row in rows] == [1, 2]
    assert [row.vigente for row in rows] == [False, True]


def test_required_views_exist(db):
    names = set(db.scalars(text("""
        SELECT table_name FROM information_schema.views
        WHERE table_schema='gestor' AND table_name LIKE 'vw_%'
    """)))
    assert {"vw_pendientes", "vw_observacion", "vw_rechazados", "vw_en_estudio",
            "vw_propuestos", "vw_aprobados", "vw_proyectos", "vw_metricas_flujo"} <= names


def test_compatibility_views_expose_legacy_candidate_id(db):
    event, _ = receive_event(db, candidate_event())
    db.commit()
    apply_event(db, event.id)
    assert db.scalar(text("SELECT id FROM gestor.candidato_ubicacion")) == 847


def test_legacy_point_without_coordinates_is_preserved(db):
    event, _ = receive_event(db, IncomingEvent(
        "test:point:1", "punto_interes", "SNAPSHOT", "9818511", 1,
        datetime.now(timezone.utc),
        {"id": 9818511, "nombre": "ECO EGAÑA", "latitud": None, "longitud": None},
    ))
    db.commit()
    assert apply_event(db, event.id) is True
    row = db.execute(text(
        "SELECT latitud, longitud FROM gestor.punto_interes WHERE legacy_punto_id='9818511'"
    )).one()
    assert row.latitud is None and row.longitud is None
