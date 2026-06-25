"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["accept", "reject", "star"]
Role = Literal["coordinator", "manager", "director", "sysadmin"]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: Role
    active: bool


class ProjectCreate(BaseModel):
    name: str
    project_url: Optional[str] = None
    notes: Optional[str] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    project_url: Optional[str] = None
    name: str
    source_file: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class IngestConfig(BaseModel):
    """Optional config declaring which column holds the map reference."""

    map_column: Optional[str] = Field(
        default=None,
        description="Name of the column holding the Google Maps URL or 'lat,lng'.",
    )


class IngestResult(BaseModel):
    project_id: str
    rows_read: int
    candidates_created: int
    map_column: str
    parsed_coordinates: int
    failed_coordinates: int


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    map_ref: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    display_data: dict[str, Any] = {}


class NextCandidateOut(BaseModel):
    candidate: Optional[CandidateOut] = None
    remaining: int
    decided: int
    total: int


class DecisionCreate(BaseModel):
    candidate_id: int
    verdict: Verdict
    note: Optional[str] = None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    candidate_id: int
    verdict: str
    note: Optional[str] = None
    decided_at: datetime


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    lat: float
    lng: float
    category: Optional[str] = None
    attributes: dict[str, Any] = {}


class BusinessIngestResult(BaseModel):
    rows_read: int
    locations_created: int
    failed_coordinates: int
