"""SQLAlchemy ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    decisions: Mapped[list["Decision"]] = relationship(
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

    project: Mapped["Project"] = relationship(back_populates="candidates")
    decision: Mapped["Decision | None"] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", uselist=False
    )


class Decision(Base):
    """The swipe result — idempotent per (project_id, candidate_id)."""

    __tablename__ = "decision"
    __table_args__ = (
        UniqueConstraint("project_id", "candidate_id", name="uq_decision_project_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.project_id"), nullable=False, index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("location_candidate.id"), nullable=False, index=True
    )
    # accept | reject | star  (star = shortlisted / priority, a strong accept)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="decisions")
    candidate: Mapped["LocationCandidate"] = relationship(back_populates="decision")


class BusinessLocation(Base):
    """Global enrichment layer — shared across all projects, no project FK."""

    __tablename__ = "business_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
