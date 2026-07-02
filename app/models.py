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

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # jefatura | comite | gerente | sysadmin
    role: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    reviews: Mapped[list["Review"]] = relationship(back_populates="reviewer")


class Project(Base):
    """The unit of work — primary scoping key everywhere."""

    __tablename__ = "project"

    project_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # A separate project URL, distinct from per-location map URLs.
    project_url: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    candidates: Mapped[list["LocationCandidate"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class LocationCandidate(Base):
    """One row per candidate from the tabular source."""

    __tablename__ = "location_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.project_id"), nullable=False, index=True
    )
    # Raw value from the "maps" column: a Google Maps URL or "lat,lng".
    map_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Remaining tabular columns -> legend content.
    display_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # ----- Multi-layer review workflow state -----
    # Which layer's queue the candidate currently sits in:
    #   jefatura | comite | gerente | done
    current_stage: Mapped[str] = mapped_column(
        String, default="jefatura", nullable=False, index=True
    )
    # pending | returned | rejected | suggested | approved_final | locales_proyecto
    status: Mapped[str] = mapped_column(
        String, default="pending", nullable=False, index=True
    )
    # Set true once any layer stars it (strong accept / shortlist priority).
    priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    workflow_group: Mapped[str | None] = mapped_column(String, default="pending", nullable=True, index=True)
    last_action: Mapped[str | None] = mapped_column(String, nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    last_reject_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_from_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_from_project_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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

    __tablename__ = "candidate_project_variables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("location_candidate.id"), unique=True, nullable=False, index=True
    )
    cve_unidad: Mapped[str | None] = mapped_column(String, nullable=True)
    unidad: Mapped[str | None] = mapped_column(String, nullable=True)
    mt2: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_arriendo: Mapped[str | None] = mapped_column(String, nullable=True)
    gastos_comunes: Mapped[str | None] = mapped_column(String, nullable=True)
    clausula_salida: Mapped[str | None] = mapped_column(Text, nullable=True)
    meses_gracia: Mapped[str | None] = mapped_column(String, nullable=True)
    plazo_arriendo: Mapped[str | None] = mapped_column(String, nullable=True)
    garantia: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_proyecto: Mapped[str | None] = mapped_column(String, nullable=True)
    fecha_apertura_aproximada: Mapped[date | None] = mapped_column(Date, nullable=True)
    contacto_nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column(String, nullable=True)
    contacto_email: Mapped[str | None] = mapped_column(String, nullable=True)
    fecha_entrega_local: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )

    candidate: Mapped["LocationCandidate"] = relationship(back_populates="project_variables")
    updated_by: Mapped["User | None"] = relationship()


class Review(Base):
    """Append-only audit log of every workflow action on a candidate.

    Never updated or deleted — each approve/reject/star/skip/send_back/reopen
    adds one row. The "current decision at stage N" is the latest row for
    that (candidate, stage) whose action is accept/reject/star.
    """

    __tablename__ = "review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("location_candidate.id"), nullable=False, index=True
    )
    # The layer at which the action happened: jefatura | comite | gerente
    stage: Mapped[str] = mapped_column(String, nullable=False, index=True)
    reviewer_id: Mapped[str] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # accept | reject | star | skip | send_back | reopen
    action: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    candidate: Mapped["LocationCandidate"] = relationship(back_populates="reviews")
    reviewer: Mapped["User"] = relationship(back_populates="reviews")


class BusinessLocation(Base):
    """Global enrichment layer — shared across all projects, no project FK."""

    __tablename__ = "business_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
