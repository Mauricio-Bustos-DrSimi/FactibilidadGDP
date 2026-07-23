"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal[
    "jefatura",
    "jefecomercial",
    "coordinador",
    "arriendo",
    "comite",
    "gerente",
    "gerentegeneral",
    "sysadmin",
]
UserDivision = Literal["SUCURSAL", "FRANQUICIA", "APERTURA"]


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
    commercial_division: Optional[UserDivision] = None
    job_title: Optional[str] = None
    supervisor_emails: Optional[str] = None
    org_x: Optional[float] = None
    org_y: Optional[float] = None
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
    requested_by: Optional[str] = None
    # Workflow state
    current_stage: str
    status: str
    workflow_group: Optional[str] = None
    priority: bool
    last_decision: Optional[str] = None
    last_reject_note: Optional[str] = None
    workflow_dates: dict[str, Optional[str]] = {}
    project_variables: Optional[dict[str, Any]] = None
    approved_division: Optional[str] = None
    # Free-text conditions the committee set at approval that must be met before
    # the location can be moved to Proyecto. Only populated for approved/opening.
    approval_conditions: Optional[str] = None


class CandidateStatusUpdate(BaseModel):
    group: Literal["pending", "proposed", "approved", "rejected", "study", "opening", "skip"]
    note: Optional[str] = None


class CandidateProjectVariablesIn(BaseModel):
    cve_unidad: Optional[str] = None
    unidad: Optional[str] = None
    comuna: Optional[str] = None
    provincia: Optional[str] = None
    region: Optional[str] = None
    mt2: Optional[float] = None
    valor_arriendo: Optional[str] = None
    gastos_comunes: Optional[str] = None
    clausula_salida: Optional[str] = None
    meses_gracia: Optional[str] = None
    plazo_arriendo: Optional[str] = None
    garantia: Optional[str] = None
    tipo_proyecto: Optional[
        Literal[
            "PROYECTO VERDE (HABITABLE)",
            "PROYECTO AZUL (EN CONSTRUCCION)",
            "PROYECTO BLANCO (SOLO TERRENO)",
        ]
    ] = None
    fecha_apertura_aproximada: Optional[date] = None
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None
    contacto_email: Optional[str] = None
    flujo_franquicia: Optional[Literal["SUBARRIENDO", "FRANQUICIADO DIRECTO"]] = None
    franquiciado_nombre: Optional[str] = None
    franquiciado_telefono: Optional[str] = None
    franquiciado_email: Optional[str] = None
    fecha_entrega_local: Optional[date] = None


class CandidateProjectVariablesOut(CandidateProjectVariablesIn):
    candidate_id: int
    updated_at: Optional[datetime] = None
    updated_by_id: Optional[str] = None


class CandidateProjectEmailSelection(BaseModel):
    plan_id: str
    recipients: list[str]
    cc: list[str] = Field(default_factory=list)


class CandidateProjectVariablesEmailIn(BaseModel):
    messages: list[CandidateProjectEmailSelection]
    variables: CandidateProjectVariablesIn


class CandidateProjectEmailPlanOut(BaseModel):
    plan_id: str
    area: str
    from_email: str
    recipients: list[str]
    cc: list[str]
    subject: str
    html_body: str
    reduced: bool


class CandidateProjectVariablesEmailPreviewIn(BaseModel):
    variables: CandidateProjectVariablesIn


class CandidateProjectSentEmailOut(BaseModel):
    plan_id: str
    area: str
    from_email: str
    recipients: list[str]
    cc: list[str]
    subject: str


class CandidateProjectVariablesEmailOut(BaseModel):
    sent: bool
    messages: list[CandidateProjectSentEmailOut]


# --------------------------------------------------------------------------- #
# Review workflow
# --------------------------------------------------------------------------- #
ReviewAction = Literal["accept", "reject", "study", "skip", "opening", "like", "dislike"]


class ReviewCreate(BaseModel):
    action: ReviewAction
    note: Optional[str] = None


class NoteIn(BaseModel):
    """Body for send-back / reopen (note optional)."""

    note: Optional[str] = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    stage: str
    action: str
    note: Optional[str] = None
    created_at: datetime
    reviewer_id: str
    reviewer_name: Optional[str] = None
    reviewer_role: Optional[str] = None


class QueueOut(BaseModel):
    """The next candidate for the current user's role, plus queue size."""

    candidate: Optional[CandidateOut] = None
    remaining: int
    stage: Optional[str] = None


class CandidateActionOut(BaseModel):
    candidate: CandidateOut
    next_candidate: Optional[CandidateOut] = None
    remaining: int = 0
    stats: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# User management (sysadmin)
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: Role
    commercial_division: Optional[UserDivision] = None
    job_title: Optional[str] = None
    supervisor_emails: Optional[str] = None
    org_x: Optional[float] = None
    org_y: Optional[float] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[Role] = None
    commercial_division: Optional[UserDivision] = None
    job_title: Optional[str] = None
    supervisor_emails: Optional[str] = None
    org_x: Optional[float] = None
    org_y: Optional[float] = None
    active: Optional[bool] = None


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


class PostgresImportRequest(BaseModel):
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    import_candidates: bool = True
    import_business: bool = True
    replace_candidates: bool = False
    replace_business: bool = True


class PostgresImportResult(BaseModel):
    project_id: Optional[str] = None
    project_created: bool
    candidate_rows_read: int
    candidates_created: int
    parsed_candidate_coordinates: int
    failed_candidate_coordinates: int
    business_rows_read: int
    business_locations_created: int
    failed_business_coordinates: int
    replaced_candidates: bool
    replaced_business: bool
