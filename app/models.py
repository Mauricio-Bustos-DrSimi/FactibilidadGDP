"""SQLAlchemy ORM models."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A person who logs in. Role determines which review layer they own."""

    __tablename__ = "usuario"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column("correo", String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column("nombre", String, nullable=False)
    password_hash: Mapped[str] = mapped_column("hash_contrasena", String, nullable=False)
    # jefatura | jefecomercial | coordinador | arriendo | comite | gerente | gerentegeneral | sysadmin
    role: Mapped[str] = mapped_column("rol", String, nullable=False)
    commercial_division: Mapped[str | None] = mapped_column("division_comercial", String, nullable=True)
    job_title: Mapped[str | None] = mapped_column("cargo", String, nullable=True)
    supervisor_emails: Mapped[str | None] = mapped_column("correos_supervisores", Text, nullable=True)
    org_x: Mapped[float | None] = mapped_column("organigrama_x", Float, nullable=True)
    org_y: Mapped[float | None] = mapped_column("organigrama_y", Float, nullable=True)
    active: Mapped[bool] = mapped_column("activo", Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=_now)

    reviews: Mapped[list["Review"]] = relationship(back_populates="reviewer")


class Project(Base):
    """The unit of work — primary scoping key everywhere."""

    __tablename__ = "proyecto"

    project_id: Mapped[str] = mapped_column("id_proyecto", String, primary_key=True, default=_uuid)
    # A separate project URL, distinct from per-location map URLs.
    project_url: Mapped[str | None] = mapped_column("url_proyecto", String, nullable=True)
    name: Mapped[str] = mapped_column("nombre", String, nullable=False)
    source_file: Mapped[str | None] = mapped_column("archivo_origen", String, nullable=True)
    notes: Mapped[str | None] = mapped_column("notas", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=_now)

    candidates: Mapped[list["LocationCandidate"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class LocationCandidate(Base):
    """One row per candidate from the tabular source."""

    __tablename__ = "candidato_ubicacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        "id_proyecto", ForeignKey("proyecto.id_proyecto"), nullable=False, index=True
    )
    # Raw value from the "maps" column: a Google Maps URL or "lat,lng".
    map_ref: Mapped[str | None] = mapped_column("referencia_mapa", Text, nullable=True)
    lat: Mapped[float | None] = mapped_column("latitud", Float, nullable=True)
    lng: Mapped[float | None] = mapped_column("longitud", Float, nullable=True)
    # Remaining tabular columns -> legend content.
    display_data: Mapped[dict] = mapped_column("datos_visualizacion", JSON, default=dict)

    # ----- Multi-layer review workflow state -----
    # Which layer's queue the candidate currently sits in:
    #   jefatura | comite | gerente | done
    current_stage: Mapped[str] = mapped_column(
        "etapa_actual", String, default="jefatura", nullable=False, index=True
    )
    # pendiente | devuelto | rechazado | sugerido | aprobado | locales_proyecto
    status: Mapped[str] = mapped_column("estado", String, default="pendiente", nullable=False, index=True)
    # Set true once any layer stars it (strong accept / shortlist priority).
    priority: Mapped[bool] = mapped_column("prioridad", Boolean, default=False, nullable=False)
    workflow_group: Mapped[str | None] = mapped_column("grupo_flujo", String, default="pendiente", nullable=True, index=True)
    last_action: Mapped[str | None] = mapped_column("ultima_accion", String, nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column("ultima_accion_en", DateTime, nullable=True)
    last_actor_role: Mapped[str | None] = mapped_column("rol_ultimo_actor", String, nullable=True)
    last_reject_note: Mapped[str | None] = mapped_column("comentario_ultimo_rechazo", Text, nullable=True)
    suggested_at: Mapped[datetime | None] = mapped_column("sugerido_en", DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column("aprobado_en", DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column("rechazado_en", DateTime, nullable=True)
    project_at: Mapped[datetime | None] = mapped_column("proyecto_en", DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column("omitido_en", DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column("devuelto_en", DateTime, nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column("reabierto_en", DateTime, nullable=True)
    rejected_from_approved_at: Mapped[datetime | None] = mapped_column("rechazado_desde_aprobado_en", DateTime, nullable=True)
    rejected_from_project_at: Mapped[datetime | None] = mapped_column("rechazado_desde_proyecto_en", DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="candidates")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="Review.created_at",
    )
    project_variables: Mapped["CandidateProjectVariables | None"] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CandidateProjectVariables(Base):
    """Editable project variables completed by Jefatura for project locations."""

    __tablename__ = "variables_proyecto_candidato"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        "id_candidato",
        ForeignKey("candidato_ubicacion.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    cve_unidad: Mapped[str | None] = mapped_column("cve_unidad", String, nullable=True)
    unidad: Mapped[str | None] = mapped_column("unidad", String, nullable=True)
    comuna: Mapped[str | None] = mapped_column("comuna", String, nullable=True)
    provincia: Mapped[str | None] = mapped_column("provincia", String, nullable=True)
    region: Mapped[str | None] = mapped_column("region", String, nullable=True)
    mt2: Mapped[float | None] = mapped_column("mt2", Float, nullable=True)
    valor_arriendo: Mapped[str | None] = mapped_column("valor_arriendo", String, nullable=True)
    gastos_comunes: Mapped[str | None] = mapped_column("gastos_comunes", String, nullable=True)
    clausula_salida: Mapped[str | None] = mapped_column("clausula_salida", Text, nullable=True)
    meses_gracia: Mapped[str | None] = mapped_column("meses_gracia", String, nullable=True)
    plazo_arriendo: Mapped[str | None] = mapped_column("plazo_arriendo", String, nullable=True)
    garantia: Mapped[str | None] = mapped_column("garantia", String, nullable=True)
    tipo_proyecto: Mapped[str | None] = mapped_column("tipo_proyecto", String, nullable=True)
    fecha_apertura_aproximada: Mapped[date | None] = mapped_column(
        "fecha_apertura_aproximada", Date, nullable=True
    )
    contacto_nombre: Mapped[str | None] = mapped_column("contacto_nombre", String, nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column("contacto_telefono", String, nullable=True)
    contacto_email: Mapped[str | None] = mapped_column("contacto_email", String, nullable=True)
    fecha_entrega_local: Mapped[date | None] = mapped_column("fecha_entrega_local", Date, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        "actualizado_por_id", ForeignKey("usuario.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        "actualizado_en", DateTime, default=_now, onupdate=_now, nullable=False
    )

    candidate: Mapped["LocationCandidate"] = relationship(back_populates="project_variables")
    updated_by: Mapped["User | None"] = relationship()


class Review(Base):
    """Append-only audit log of every workflow action on a candidate.

    Never updated or deleted — each approve/reject/star/skip/send_back/reopen
    adds one row. The "current decision at stage N" is the latest row for
    that (candidate, stage) whose action is accept/reject/star.
    """

    __tablename__ = "revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        "id_candidato", ForeignKey("candidato_ubicacion.id"), nullable=False, index=True
    )
    # The layer at which the action happened: jefatura | comite | gerente
    stage: Mapped[str] = mapped_column("etapa", String, nullable=False, index=True)
    reviewer_id: Mapped[str] = mapped_column(
        "id_revisor", ForeignKey("usuario.id"), nullable=False, index=True
    )
    # accept | reject | star | skip | send_back | reopen
    action: Mapped[str] = mapped_column("accion", String, nullable=False)
    note: Mapped[str | None] = mapped_column("comentario", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=_now, index=True)

    candidate: Mapped["LocationCandidate"] = relationship(back_populates="reviews")
    reviewer: Mapped["User"] = relationship(back_populates="reviews")


class BusinessLocation(Base):
    """Global enrichment layer — shared across all projects, no project FK."""

    __tablename__ = "punto_interes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column("nombre", String, nullable=True)
    lat: Mapped[float] = mapped_column("latitud", Float, nullable=False)
    lng: Mapped[float] = mapped_column("longitud", Float, nullable=False)
    category: Mapped[str | None] = mapped_column("categoria", String, nullable=True)
    attributes: Mapped[dict] = mapped_column("atributos", JSON, default=dict)
