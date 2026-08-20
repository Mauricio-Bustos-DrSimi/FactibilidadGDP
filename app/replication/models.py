"""Normalized PostgreSQL model owned by FactibilidadGDP.

The legacy Gestor read model is kept in ``gestor``. Integration bookkeeping is
kept in ``integracion`` and local business writes in ``factibilidad``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class ReplicationBase(DeclarativeBase):
    pass


class EstadoCatalogo(ReplicationBase):
    __tablename__ = "estado_catalogo"
    __table_args__ = {"schema": "gestor"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    estados_origen: Mapped[list] = mapped_column(JSON_VALUE, nullable=False, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Rol(ReplicationBase):
    __tablename__ = "rol"
    __table_args__ = {"schema": "gestor"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Usuario(ReplicationBase):
    __tablename__ = "usuario"
    __table_args__ = (
        UniqueConstraint("legacy_usuario_id", name="uq_gestor_usuario_legacy"),
        {"schema": "gestor"},
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    legacy_usuario_id: Mapped[str] = mapped_column(String(120), nullable=False)
    rol_id: Mapped[int | None] = mapped_column(ForeignKey("gestor.rol.id"))
    rol: Mapped[str] = mapped_column(String(50), nullable=False)
    correo: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    hash_contrasena: Mapped[str] = mapped_column(Text, nullable=False)
    division_comercial: Mapped[str | None] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(200))
    correos_supervisores: Mapped[str | None] = mapped_column(Text)
    organigrama_x: Mapped[float | None] = mapped_column(Numeric)
    organigrama_y: Mapped[float | None] = mapped_column(Numeric)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload_origen: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    hash_origen: Mapped[str] = mapped_column(String(64), nullable=False)
    sincronizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProyectoImportacion(ReplicationBase):
    __tablename__ = "proyecto_importacion"
    __table_args__ = {"schema": "gestor"}

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    legacy_proyecto_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    archivo_origen: Mapped[str | None] = mapped_column(Text)
    creado_origen_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_origen: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    hash_origen: Mapped[str] = mapped_column(String(64), nullable=False)


class Candidato(ReplicationBase):
    __tablename__ = "candidato"
    __table_args__ = (
        UniqueConstraint("legacy_candidato_id", name="uq_gestor_candidato_legacy"),
        CheckConstraint(
            "certeza_mapeo IN ('EXACTA','INFERIDA','DESCONOCIDA')",
            name="ck_candidato_certeza",
        ),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    legacy_candidato_id: Mapped[str] = mapped_column(String(120), nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    proyecto_id: Mapped[str | None] = mapped_column(
        ForeignKey("gestor.proyecto_importacion.id")
    )
    estado_actual_id: Mapped[int] = mapped_column(
        ForeignKey("gestor.estado_catalogo.id"), nullable=False, index=True
    )
    estado_origen: Mapped[str] = mapped_column(String(80), nullable=False)
    certeza_mapeo: Mapped[str] = mapped_column(String(16), nullable=False)
    version_origen: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    referencia_mapa: Mapped[str | None] = mapped_column(Text)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7))
    datos: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    payload_origen: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    hash_origen: Mapped[str] = mapped_column(String(64), nullable=False)
    actualizado_origen_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sincronizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransicionEstado(ReplicationBase):
    __tablename__ = "transicion_estado"
    __table_args__ = (
        UniqueConstraint("legacy_revision_id", name="uq_transicion_legacy_revision"),
        UniqueConstraint("evento_origen_id", name="uq_transicion_evento_origen"),
        Index("ix_transicion_candidato_orden", "candidato_id", "orden_origen"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_id: Mapped[int] = mapped_column(ForeignKey("gestor.candidato.id"), nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    legacy_revision_id: Mapped[str | None] = mapped_column(String(120))
    evento_origen_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integracion.evento_entrada.id"), nullable=False
    )
    estado_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("gestor.estado_catalogo.id"))
    estado_nuevo_id: Mapped[int] = mapped_column(ForeignKey("gestor.estado_catalogo.id"), nullable=False)
    estado_origen: Mapped[str] = mapped_column(String(80), nullable=False)
    accion_origen: Mapped[str] = mapped_column(String(80), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    actor_legacy_id: Mapped[str | None] = mapped_column(String(120))
    orden_origen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActividadCandidato(ReplicationBase):
    __tablename__ = "actividad_candidato"
    __table_args__ = (
        UniqueConstraint("evento_origen_id", "tipo", name="uq_actividad_evento_tipo"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_id: Mapped[int] = mapped_column(ForeignKey("gestor.candidato.id"), nullable=False, index=True)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    evento_origen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integracion.evento_entrada.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    detalle: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VariableProyectoVersion(ReplicationBase):
    __tablename__ = "variable_proyecto_version"
    __table_args__ = (
        UniqueConstraint("candidato_id", "version", name="uq_variable_candidato_version"),
        UniqueConstraint("evento_origen_id", name="uq_variable_evento"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_id: Mapped[int] = mapped_column(ForeignKey("gestor.candidato.id"), nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    evento_origen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integracion.evento_entrada.id"), nullable=False)
    legacy_variable_id: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    valores: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    hash_origen: Mapped[str] = mapped_column(String(64), nullable=False)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentoCandidato(ReplicationBase):
    __tablename__ = "documento_candidato"
    __table_args__ = (
        UniqueConstraint("candidato_id", "ruta_origen", name="uq_documento_candidato_ruta"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_id: Mapped[int] = mapped_column(ForeignKey("gestor.candidato.id"), nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    ruta_origen: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    tamano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modificado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    presente: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    inventariado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificacionEnvio(ReplicationBase):
    __tablename__ = "notificacion_envio"
    __table_args__ = (
        UniqueConstraint("evento_origen_id", "tipo", name="uq_notificacion_evento_tipo"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evento_origen_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("integracion.evento_entrada.id"))
    candidato_id: Mapped[int | None] = mapped_column(ForeignKey("gestor.candidato.id"))
    id_proyeccion: Mapped[str | None] = mapped_column(String(120), index=True)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    destinatarios: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    estado: Mapped[str] = mapped_column(String(32), nullable=False)
    suprimido_por_shadow: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PuntoInteres(ReplicationBase):
    __tablename__ = "punto_interes"
    __table_args__ = (
        UniqueConstraint("legacy_punto_id", name="uq_punto_legacy"),
        {"schema": "gestor"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    legacy_punto_id: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(500))
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(200))
    atributos: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    hash_origen: Mapped[str] = mapped_column(String(64), nullable=False)


class EventoEntrada(ReplicationBase):
    __tablename__ = "evento_entrada"
    __table_args__ = (
        UniqueConstraint("evento_origen_id", name="uq_evento_entrada_origen"),
        Index("ix_evento_entrada_estado_orden", "estado", "orden_origen"),
        {"schema": "integracion"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evento_origen_id: Mapped[str] = mapped_column(String(250), nullable=False)
    source_lsn: Mapped[str | None] = mapped_column(String(40))
    tabla_origen: Mapped[str] = mapped_column(String(160), nullable=False)
    operacion: Mapped[str] = mapped_column(String(16), nullable=False)
    clave_origen: Mapped[str] = mapped_column(String(250), nullable=False)
    candidato_legacy_id: Mapped[str | None] = mapped_column(String(120), index=True)
    id_proyeccion: Mapped[str | None] = mapped_column(String(120), index=True)
    orden_origen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), default="PENDIENTE", nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    siguiente_intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aplicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventoSalida(ReplicationBase):
    __tablename__ = "evento_salida"
    __table_args__ = (
        CheckConstraint("modo IN ('PRUEBA','SUPRIMIDO')", name="ck_evento_salida_modo"),
        {"schema": "integracion"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modo: Mapped[str] = mapped_column(String(16), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    clave_agregado: Mapped[str | None] = mapped_column(String(250), index=True)
    id_proyeccion: Mapped[str | None] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckpointCDC(ReplicationBase):
    __tablename__ = "checkpoint_cdc"
    __table_args__ = {"schema": "integracion"}

    consumidor: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_lsn: Mapped[str | None] = mapped_column(String(40))
    ultima_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_id: Mapped[str | None] = mapped_column(String(160))
    ultimo_hash: Mapped[str | None] = mapped_column(String(64))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventoFallido(ReplicationBase):
    __tablename__ = "evento_fallido"
    __table_args__ = (
        UniqueConstraint("evento_entrada_id", name="uq_evento_fallido_entrada"),
        {"schema": "integracion"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evento_entrada_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integracion.evento_entrada.id"), nullable=False)
    id_proyeccion: Mapped[str | None] = mapped_column(String(120), index=True)
    error_tipo: Mapped[str] = mapped_column(String(200), nullable=False)
    error_detalle: Mapped[str] = mapped_column(Text, nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False)
    primer_fallo_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ultimo_fallo_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reconciliacion(ReplicationBase):
    __tablename__ = "reconciliacion"
    __table_args__ = {"schema": "integracion"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    iniciado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(24), nullable=False)
    totales_origen: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    totales_destino: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    diferencias: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    diferencias_cantidad: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reporte_json: Mapped[str | None] = mapped_column(Text)
    reporte_csv: Mapped[str | None] = mapped_column(Text)


class MigracionControl(ReplicationBase):
    __tablename__ = "migracion_control"
    __table_args__ = {"schema": "integracion"}

    clave: Mapped[str] = mapped_column(String(180), primary_key=True)
    fase: Mapped[str] = mapped_column(String(80), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False)
    checkpoint: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    iniciado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Entrega(ReplicationBase):
    __tablename__ = "entrega"
    __table_args__ = {"schema": "factibilidad"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_legacy_id: Mapped[int] = mapped_column("id_candidato", BigInteger, nullable=False, index=True)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    area_destino: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(String(32), nullable=False)
    antecedentes: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    entregado_por: Mapped[str | None] = mapped_column(String(120))
    entregado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TareaLocal(ReplicationBase):
    __tablename__ = "tarea_local"
    __table_args__ = (
        UniqueConstraint("id_candidato", "clave_tarea", name="uq_factibilidad_tarea"),
        {"schema": "factibilidad"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_legacy_id: Mapped[int] = mapped_column("id_candidato", BigInteger, nullable=False, index=True)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clave_grupo: Mapped[str] = mapped_column(String(100), nullable=False)
    clave_tarea: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(String(32), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    actualizado_por: Mapped[str | None] = mapped_column("actualizado_por_id", String(120))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DecisionLocal(ReplicationBase):
    __tablename__ = "decision_local"
    __table_args__ = (
        UniqueConstraint("id_candidato", name="uq_factibilidad_decision"),
        {"schema": "factibilidad"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_legacy_id: Mapped[int] = mapped_column("id_candidato", BigInteger, nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actualizado_por: Mapped[str | None] = mapped_column("actualizado_por_id", String(120))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VistoBuenoLocal(ReplicationBase):
    __tablename__ = "visto_bueno_local"
    __table_args__ = (
        UniqueConstraint("id_candidato", "area", name="uq_factibilidad_vb"),
        {"schema": "factibilidad"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidato_legacy_id: Mapped[int] = mapped_column("id_candidato", BigInteger, nullable=False)
    id_proyeccion: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(32), nullable=False)
    aprobado_por: Mapped[str | None] = mapped_column("aprobado_por_id", String(120))
    aprobado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
