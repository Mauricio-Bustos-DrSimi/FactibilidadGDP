"""Idempotent inbox and exactly-once event effects on the target database."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.replication import models
from app.replication.identity import projection_id_from_display_data
from app.replication.state_mapping import translate_state


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def json_value(value: Any) -> Any:
    """Return a deterministic JSON-safe value for database payload columns."""
    return json.loads(canonical_json(value))


@dataclass(frozen=True)
class IncomingEvent:
    origin_id: str
    table: str
    operation: str
    key: str
    order: int
    occurred_at: datetime
    payload: dict[str, Any]
    source_lsn: str | None = None
    candidate_legacy_id: str | None = None


def receive_event(db: Session, incoming: IncomingEvent) -> tuple[models.EventoEntrada, bool]:
    """Insert once. A duplicate origin id returns the previously stored event."""
    normalized_payload = json_value(incoming.payload)
    normalized_hash = payload_hash(normalized_payload)
    existing = db.scalar(
        select(models.EventoEntrada).where(
            models.EventoEntrada.evento_origen_id == incoming.origin_id
        )
    )
    if existing:
        if existing.payload_hash != normalized_hash:
            raise ValueError("Duplicate origin id has a different payload hash")
        return existing, False
    row = models.EventoEntrada(
        id=uuid.uuid4(),
        evento_origen_id=incoming.origin_id,
        source_lsn=incoming.source_lsn,
        tabla_origen=incoming.table,
        operacion=incoming.operation,
        clave_origen=incoming.key,
        candidato_legacy_id=incoming.candidate_legacy_id,
        orden_origen=incoming.order,
        ocurrido_en=incoming.occurred_at,
        payload=normalized_payload,
        payload_hash=normalized_hash,
    )
    try:
        # A savepoint prevents a concurrent duplicate from rolling back other
        # inbox inserts already staged by the same snapshot batch.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(models.EventoEntrada).where(
                models.EventoEntrada.evento_origen_id == incoming.origin_id
            )
        )
        if existing is None:
            raise
        return existing, False
    return row, True


def _state(db: Session, code: str) -> models.EstadoCatalogo:
    row = db.scalar(select(models.EstadoCatalogo).where(models.EstadoCatalogo.codigo == code))
    if row is None:
        raise RuntimeError(f"Missing state catalog entry: {code}")
    return row


def _candidate(db: Session, legacy_id: str, lock: bool = True) -> models.Candidato | None:
    query = select(models.Candidato).where(models.Candidato.legacy_candidato_id == legacy_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


ACTION_STATE = {
    "accept": "PROPUESTO",
    "study": "EN_ESTUDIO",
    "reject": "RECHAZADO",
    "project": "APROBADO",
    "opening": "PROYECTO",
    "send_back": "PENDIENTE",
    "reopen": "PENDIENTE",
}


def _datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _apply_candidate(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_id = str(data.get("id") or event.clave_origen)
    display_data = data.get("datos_visualizacion") or data.get("display_data") or {}
    projection_id = projection_id_from_display_data(display_data)
    mapped = translate_state(data.get("estado") or data.get("status"))
    source_version = int(data.get("_source_version", event.orden_origen))
    state = _state(db, mapped.codigo)
    candidate = _candidate(db, legacy_id)
    legacy_project_id = str(data.get("id_proyecto") or data.get("project_id") or "")
    project = db.scalar(select(models.ProyectoImportacion).where(
        models.ProyectoImportacion.legacy_proyecto_id == legacy_project_id
    )) if legacy_project_id else None
    if candidate is None:
        if projection_id is None:
            raise ValueError(f"Candidate {legacy_id} is missing ID Proyección")
        candidate = models.Candidato(
            legacy_candidato_id=legacy_id,
            id_proyeccion=projection_id,
            proyecto_id=project.id if project else None,
            estado_actual_id=state.id,
            estado_origen=str(data.get("estado") or data.get("status") or ""),
            certeza_mapeo=mapped.certeza,
            version_origen=source_version,
            referencia_mapa=data.get("referencia_mapa") or data.get("map_ref"),
            latitud=data.get("latitud") or data.get("lat"),
            longitud=data.get("longitud") or data.get("lng"),
            datos=display_data,
            payload_origen=data,
            hash_origen=event.payload_hash,
            actualizado_origen_en=event.ocurrido_en,
        )
        db.add(candidate)
        db.flush()
    elif event.operacion == "SNAPSHOT_FINAL" or source_version > candidate.version_origen:
        candidate.estado_actual_id = state.id
        if project:
            candidate.proyecto_id = project.id
        candidate.estado_origen = str(data.get("estado") or data.get("status") or "")
        candidate.certeza_mapeo = mapped.certeza
        candidate.version_origen = max(candidate.version_origen, source_version)
        candidate.referencia_mapa = data.get("referencia_mapa", candidate.referencia_mapa)
        candidate.latitud = data.get("latitud", data.get("lat", candidate.latitud))
        candidate.longitud = data.get("longitud", data.get("lng", candidate.longitud))
        candidate.datos = data.get("datos_visualizacion", data.get("display_data", candidate.datos))
        candidate.id_proyeccion = projection_id or candidate.id_proyeccion
        candidate.payload_origen = data
        candidate.hash_origen = event.payload_hash
        candidate.actualizado_origen_en = event.ocurrido_en
        candidate.sincronizado_en = datetime.now(timezone.utc)
    event.id_proyeccion = candidate.id_proyeccion
    db.add(models.ActividadCandidato(
        candidato_id=candidate.id,
        id_proyeccion=candidate.id_proyeccion,
        evento_origen_id=event.id,
        tipo="CANDIDATO_SINCRONIZADO",
        detalle={"operacion": event.operacion, "estado_origen": candidate.estado_origen},
        ocurrido_en=event.ocurrido_en,
    ))
def _apply_review(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_candidate_id = str(
        data.get("id_candidato") or data.get("candidate_id") or event.candidato_legacy_id or ""
    )
    candidate = _candidate(db, legacy_candidate_id)
    if candidate is None:
        raise LookupError(f"Candidate {legacy_candidate_id} has not been replicated")
    event.id_proyeccion = candidate.id_proyeccion
    action = str(data.get("accion") or data.get("action") or "comment").strip().lower()
    destination_code = ACTION_STATE.get(action)
    if destination_code:
        destination = _state(db, destination_code)
        previous_id = candidate.estado_actual_id
        db.add(models.TransicionEstado(
            candidato_id=candidate.id,
            id_proyeccion=candidate.id_proyeccion,
            legacy_revision_id=str(data.get("id") or event.clave_origen),
            evento_origen_id=event.id,
            estado_anterior_id=previous_id,
            estado_nuevo_id=destination.id,
            estado_origen=str(data.get("estado_origen") or destination_code),
            accion_origen=action,
            comentario=data.get("comentario") or data.get("note"),
            actor_legacy_id=str(data.get("id_revisor") or data.get("reviewer_id") or "") or None,
            orden_origen=event.orden_origen,
            ocurrido_en=event.ocurrido_en,
        ))
        candidate.estado_actual_id = destination.id
        candidate.estado_origen = str(data.get("estado_origen") or destination_code)
    db.add(models.ActividadCandidato(
        candidato_id=candidate.id,
        id_proyeccion=candidate.id_proyeccion,
        evento_origen_id=event.id,
        tipo="CAMBIO_ESTADO" if destination_code else "COMENTARIO",
        detalle={"accion": action, "comentario": data.get("comentario") or data.get("note")},
        ocurrido_en=event.ocurrido_en,
    ))
    if action == "project" or "email" in action or "correo" in action:
        db.add(models.NotificacionEnvio(
            evento_origen_id=event.id,
            candidato_id=candidate.id,
            id_proyeccion=candidate.id_proyeccion,
            tipo="APROBACION" if action == "project" else "CORREO_VARIABLES",
            destinatarios={},
            estado="REPLICADA_SIN_REENVIO",
            suprimido_por_shadow=True,
        ))


def _apply_variables(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_candidate_id = str(data.get("id_candidato") or data.get("candidate_id") or "")
    candidate = _candidate(db, legacy_candidate_id)
    if candidate is None:
        raise LookupError(f"Candidate {legacy_candidate_id} has not been replicated")
    event.id_proyeccion = candidate.id_proyeccion
    current_version = db.scalar(
        select(func.max(models.VariableProyectoVersion.version)).where(
            models.VariableProyectoVersion.candidato_id == candidate.id
        )
    ) or 0
    db.query(models.VariableProyectoVersion).filter(
        models.VariableProyectoVersion.candidato_id == candidate.id,
        models.VariableProyectoVersion.vigente.is_(True),
    ).update({"vigente": False})
    db.add(models.VariableProyectoVersion(
        candidato_id=candidate.id,
        id_proyeccion=candidate.id_proyeccion,
        evento_origen_id=event.id,
        legacy_variable_id=str(data.get("id") or event.clave_origen),
        version=current_version + 1,
        valores=data,
        hash_origen=event.payload_hash,
        vigente=True,
        ocurrido_en=event.ocurrido_en,
    ))


def _apply_project(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_id = str(data.get("id_proyecto") or data.get("project_id") or event.clave_origen)
    row = db.scalar(select(models.ProyectoImportacion).where(
        models.ProyectoImportacion.legacy_proyecto_id == legacy_id
    ))
    values = {
        "nombre": str(data.get("nombre") or data.get("name") or legacy_id),
        "archivo_origen": data.get("archivo_origen") or data.get("source_file"),
        "creado_origen_en": _datetime_value(data.get("creado_en") or data.get("created_at")),
        "payload_origen": data,
        "hash_origen": event.payload_hash,
    }
    if row is None:
        db.add(models.ProyectoImportacion(id=legacy_id, legacy_proyecto_id=legacy_id, **values))
    else:
        for key, value in values.items():
            setattr(row, key, value)


def _apply_user(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_id = str(data.get("id") or event.clave_origen)
    role_code = str(data.get("rol") or data.get("role") or "desconocido")
    role = db.scalar(select(models.Rol).where(models.Rol.codigo == role_code))
    if role is None:
        next_id = (db.scalar(select(func.max(models.Rol.id))) or 0) + 1
        role = models.Rol(id=next_id, codigo=role_code, nombre=role_code, activo=True)
        db.add(role)
        db.flush()
    row = db.scalar(select(models.Usuario).where(models.Usuario.legacy_usuario_id == legacy_id))
    values = {
        "rol_id": role.id,
        "rol": role_code,
        "correo": str(data.get("correo") or data.get("email") or ""),
        "nombre": str(data.get("nombre") or data.get("name") or legacy_id),
        "hash_contrasena": str(data.get("hash_contrasena") or data.get("password_hash") or ""),
        "division_comercial": data.get("division_comercial") or data.get("commercial_division"),
        "cargo": data.get("cargo") or data.get("job_title"),
        "correos_supervisores": data.get("correos_supervisores") or data.get("supervisor_emails"),
        "organigrama_x": data.get("organigrama_x") or data.get("org_x"),
        "organigrama_y": data.get("organigrama_y") or data.get("org_y"),
        "activo": bool(data.get("activo", data.get("active", True))),
        "eliminado_en": _datetime_value(data.get("eliminado_en") or data.get("deleted_at")),
        "payload_origen": data,
        "hash_origen": event.payload_hash,
        "sincronizado_en": datetime.now(timezone.utc),
    }
    if row is None:
        db.add(models.Usuario(id=legacy_id, legacy_usuario_id=legacy_id, **values))
    else:
        for key, value in values.items():
            setattr(row, key, value)


def _apply_point(db: Session, event: models.EventoEntrada) -> None:
    data = event.payload
    legacy_id = str(data.get("id") or event.clave_origen)
    row = db.scalar(select(models.PuntoInteres).where(
        models.PuntoInteres.legacy_punto_id == legacy_id
    ))
    values = {
        "nombre": data.get("nombre") or data.get("name"),
        "latitud": data.get("latitud") or data.get("lat"),
        "longitud": data.get("longitud") or data.get("lng"),
        "categoria": data.get("categoria") or data.get("category"),
        "atributos": data.get("atributos") or data.get("attributes") or {},
        "hash_origen": event.payload_hash,
    }
    if row is None:
        db.add(models.PuntoInteres(legacy_punto_id=legacy_id, **values))
    else:
        for key, value in values.items():
            setattr(row, key, value)


def _dispatch(db: Session, event: models.EventoEntrada) -> None:
    table = event.tabla_origen.rsplit(".", 1)[-1].lower()
    if table in {"candidato_ubicacion", "location_candidate"}:
        _apply_candidate(db, event)
    elif table in {"proyecto", "project"}:
        _apply_project(db, event)
    elif table in {"usuario", "user"}:
        _apply_user(db, event)
    elif table in {"revision", "review"}:
        _apply_review(db, event)
    elif table in {"variables_proyecto_candidato", "candidate_project_variables"}:
        _apply_variables(db, event)
    elif table in {"punto_interes", "business_location"}:
        _apply_point(db, event)
    else:
        # Unsupported tables remain auditable without mutating shared data.
        event.estado = "IGNORADO"


def apply_event(db: Session, event_id: uuid.UUID, consumer: str = "replica") -> bool:
    """Apply one inbox event atomically; repeated calls have no effect."""
    event = db.scalar(
        select(models.EventoEntrada).where(models.EventoEntrada.id == event_id).with_for_update()
    )
    if event is None:
        raise LookupError(f"Event {event_id} does not exist")
    if event.estado in {"APLICADO", "IGNORADO"}:
        return False
    try:
        _dispatch(db, event)
        if event.estado != "IGNORADO":
            event.estado = "APLICADO"
        event.aplicado_en = datetime.now(timezone.utc)
        event.intentos += 1
        checkpoint = db.get(models.CheckpointCDC, consumer)
        if checkpoint is None:
            checkpoint = models.CheckpointCDC(consumidor=consumer)
            db.add(checkpoint)
        checkpoint.source_lsn = event.source_lsn or checkpoint.source_lsn
        checkpoint.ultima_fecha = event.ocurrido_en
        checkpoint.ultimo_id = str(event.orden_origen)
        checkpoint.ultimo_hash = event.payload_hash
        checkpoint.actualizado_en = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        failed_event = db.get(models.EventoEntrada, event_id)
        if failed_event is not None:
            failed_event.intentos += 1
            failed_event.estado = "FALLIDO" if failed_event.intentos >= 5 else "REINTENTO"
            failed_event.siguiente_intento_en = datetime.now(timezone.utc) + timedelta(
                seconds=min(300, 2 ** failed_event.intentos)
            )
            dead = db.scalar(select(models.EventoFallido).where(
                models.EventoFallido.evento_entrada_id == event_id
            ))
            if dead is None:
                dead = models.EventoFallido(
                    evento_entrada_id=event_id,
                    error_tipo=type(exc).__name__,
                    error_detalle=str(exc)[:4000],
                    intentos=failed_event.intentos,
                )
                db.add(dead)
            else:
                dead.error_tipo = type(exc).__name__
                dead.error_detalle = str(exc)[:4000]
                dead.intentos = failed_event.intentos
                dead.ultimo_fallo_en = datetime.now(timezone.utc)
            db.commit()
        raise


def process_pending(db: Session, limit: int = 100) -> dict[str, int]:
    ids = list(db.scalars(
        select(models.EventoEntrada.id)
        .where(models.EventoEntrada.estado.in_(["PENDIENTE", "REINTENTO"]))
        .where(
            (models.EventoEntrada.siguiente_intento_en.is_(None))
            | (models.EventoEntrada.siguiente_intento_en <= datetime.now(timezone.utc))
        )
        .order_by(models.EventoEntrada.orden_origen, models.EventoEntrada.recibido_en)
        .limit(limit)
    ))
    result = {"aplicados": 0, "fallidos": 0}
    for event_id in ids:
        try:
            result["aplicados"] += int(apply_event(db, event_id))
        except Exception:
            result["fallidos"] += 1
    return result


def replay_failed(db: Session, event_id: uuid.UUID | None = None) -> int:
    query = select(models.EventoEntrada).where(models.EventoEntrada.estado == "FALLIDO")
    if event_id is not None:
        query = query.where(models.EventoEntrada.id == event_id)
    rows = list(db.scalars(query.with_for_update()))
    for event in rows:
        event.estado = "PENDIENTE"
        event.siguiente_intento_en = None
        dead = db.scalar(select(models.EventoFallido).where(
            models.EventoFallido.evento_entrada_id == event.id
        ))
        if dead:
            dead.resuelto_en = datetime.now(timezone.utc)
    db.commit()
    return len(rows)
