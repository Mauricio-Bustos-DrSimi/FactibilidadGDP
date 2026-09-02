from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.approval_outbox import (
    deliver_approval_notification,
    enqueue_approval_notification,
)
from app.replication.models import EventoSalida


@pytest.fixture
def outbox_db():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"integracion": None}},
    )
    EventoSalida.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_approval_notification_is_enqueued_once_and_delivered_after_commit(outbox_db):
    db = outbox_db
    event_key = "review:123"
    event_id = enqueue_approval_notification(
        db,
        event_key=event_key,
        candidate_id=847,
        projection_id="847",
        division="SUCURSAL",
    )
    duplicate_id = enqueue_approval_notification(
        db,
        event_key=event_key,
        candidate_id=847,
        projection_id="847",
        division="SUCURSAL",
    )

    assert event_id == duplicate_id
    assert db.scalar(select(func.count(EventoSalida.id))) == 1

    sent: list[tuple[int, str, str]] = []
    db.commit()

    assert deliver_approval_notification(
        db,
        event_id,
        lambda candidate_id, division, message_id: sent.append(
            (candidate_id, division, message_id)
        ),
    ) is True
    assert sent == [(847, "SUCURSAL", str(event_id))]
    assert db.get(EventoSalida, event_id).publicado_en is not None

    assert deliver_approval_notification(
        db,
        event_id,
        lambda candidate_id, division, message_id: sent.append(
            (candidate_id, division, message_id)
        ),
    ) is False
    assert sent == [(847, "SUCURSAL", str(event_id))]


def test_failed_delivery_remains_pending_for_retry(outbox_db):
    db = outbox_db
    event_id = enqueue_approval_notification(
        db,
        event_key=f"review:{uuid.uuid4()}",
        candidate_id=848,
        projection_id="848",
        division="FRANQUICIA",
    )
    db.commit()

    with pytest.raises(OSError, match="SMTP unavailable"):
        deliver_approval_notification(
            db,
            event_id,
            lambda _candidate_id, _division, _message_id: (_ for _ in ()).throw(
                OSError("SMTP unavailable")
            ),
        )

    stored = db.get(EventoSalida, event_id)
    assert stored.publicado_en is None
    assert stored.estado == "PENDIENTE"
    assert stored.intentos == 1
    assert stored.ultimo_error == "SMTP unavailable"


def test_outbox_event_rolls_back_with_its_business_transaction(outbox_db):
    enqueue_approval_notification(
        outbox_db,
        event_key="review:rolled-back",
        candidate_id=849,
        projection_id="849",
        division="SUCURSAL",
    )

    outbox_db.rollback()

    assert outbox_db.scalar(select(func.count(EventoSalida.id))) == 0


def test_postgres_migration_accepts_one_productive_outbox_event(db):
    event_id = enqueue_approval_notification(
        db,
        event_key="review:postgres-migration",
        candidate_id=850,
        projection_id="850",
        division="SUCURSAL",
    )
    db.commit()

    stored = db.get(EventoSalida, event_id)
    assert stored.modo == "PRODUCTIVO"
    assert stored.estado == "PENDIENTE"
    assert stored.intentos == 0
