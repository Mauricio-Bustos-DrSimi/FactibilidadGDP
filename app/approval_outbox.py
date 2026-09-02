"""Transactional outbox for projection approval notifications."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.replication.models import EventoSalida


APPROVAL_NOTIFICATION_TYPE = "APROBACION_PROYECCION"
_OUTBOX_NAMESPACE = uuid.UUID("29765aad-5c22-4d7a-976d-4dc3d96b6cd3")


def enqueue_approval_notification(
    db: Session,
    *,
    event_key: str,
    candidate_id: int,
    projection_id: str,
    division: str,
) -> uuid.UUID:
    """Add one approval notification to the caller's current transaction."""
    event_id = uuid.uuid5(_OUTBOX_NAMESPACE, event_key)
    if db.get(EventoSalida, event_id) is not None:
        return event_id
    db.add(EventoSalida(
        id=event_id,
        modo="PRODUCTIVO",
        tipo=APPROVAL_NOTIFICATION_TYPE,
        clave_agregado=str(candidate_id),
        id_proyeccion=str(projection_id),
        payload={"candidate_id": candidate_id, "division": division},
        estado="PENDIENTE",
        intentos=0,
    ))
    db.flush()
    return event_id


def deliver_approval_notification(
    db: Session,
    event_id: uuid.UUID,
    sender: Callable[[int, str, str], None],
) -> bool:
    """Deliver one committed event at least once, with a stable message ID."""
    event = db.scalar(
        select(EventoSalida).where(EventoSalida.id == event_id).with_for_update()
    )
    if event is None:
        raise LookupError(f"Approval outbox event {event_id} does not exist")
    if event.publicado_en is not None:
        return False

    payload = event.payload or {}
    try:
        sender(int(payload["candidate_id"]), str(payload["division"]), str(event.id))
    except Exception as exc:
        event.intentos += 1
        event.estado = "PENDIENTE"
        event.ultimo_error = str(exc)[:4000]
        db.commit()
        raise

    event.intentos += 1
    event.estado = "ENVIADO"
    event.ultimo_error = None
    event.publicado_en = datetime.now(timezone.utc)
    db.commit()
    return True


def pending_approval_notification_ids(db: Session) -> list[uuid.UUID]:
    """Return pending approval events in creation order for safe replay."""
    return list(db.scalars(
        select(EventoSalida.id)
        .where(EventoSalida.modo == "PRODUCTIVO")
        .where(EventoSalida.tipo == APPROVAL_NOTIFICATION_TYPE)
        .where(EventoSalida.publicado_en.is_(None))
        .order_by(EventoSalida.creado_en, EventoSalida.id)
    ))
