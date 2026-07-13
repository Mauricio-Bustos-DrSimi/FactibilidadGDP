"""Role-based review workflow for candidate locations.

Groups shown in the UI:
    pending -> suggested -> approved -> project
    pending -> highlighted -> suggested -> approved -> project

Roles:
    jefatura: like/dislike pending candidates as metrics, or highlight them.
    comite: approve/reject pending, suggested, approved, or rejected candidates.
    gerente: see all candidates and approve/reject pending, suggested, or approved candidates.
    sysadmin: unrestricted oversight.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

JEFATURA = "jefatura"
JEFE_COMERCIAL = "jefecomercial"
COORDINADOR = "coordinador"
ARRIENDO = "arriendo"
COMITE = "comite"
GERENTE = "gerente"
SYSADMIN = "sysadmin"

STAGES: tuple[str, ...] = (JEFATURA, JEFE_COMERCIAL, COORDINADOR, ARRIENDO, COMITE, GERENTE)
JEFATURA_LIKE_ROLES = frozenset({JEFATURA, JEFE_COMERCIAL, COORDINADOR})
COMITE_LIKE_ROLES = frozenset({COMITE, ARRIENDO, GERENTE})
DONE = "done"
APPROVED_STAGE = "Aprobado"
PROJECT_STAGE = "Proyecto"

PENDING = "pendiente"
RETURNED = "devuelto"
REJECTED = "rechazado"
SUGGESTED = "sugerido"
APPROVED_FINAL = "aprobado"
PROJECT = "locales_proyecto"
OPENING = "por_abrir"
ACTIVE_STATUSES = frozenset({PENDING, RETURNED})

GROUP_TO_DB = {
    "pending": PENDING,
    "suggested": SUGGESTED,
    "approved": APPROVED_FINAL,
    "rejected": REJECTED,
    "project": PROJECT,
    "opening": OPENING,
}

DB_TO_GROUP = {
    PENDING: "pending",
    RETURNED: "pending",
    SUGGESTED: "suggested",
    APPROVED_FINAL: "approved",
    REJECTED: "rejected",
    PROJECT: "approved",
    OPENING: "opening",
    # Legacy values kept for rows created before the Spanish-state change.
    "pending": "pending",
    "returned": "pending",
    "suggested": "suggested",
    "approved": "approved",
    "approved_final": "approved",
    "rejected": "rejected",
    "project": "approved",
    "opening": "opening",
}


def candidate_group_for_db_value(value: str | None) -> str:
    return DB_TO_GROUP.get(value or "", "pending")

DECIDING_ACTIONS = frozenset({"accept", "reject", "star", "project", "like", "dislike", "opening"})
QUEUE_SORT_FIELDS = frozenset({"id", "score"})

ROLE_STAGE = {
    JEFATURA: JEFATURA,
    JEFE_COMERCIAL: JEFE_COMERCIAL,
    COORDINADOR: COORDINADOR,
    ARRIENDO: ARRIENDO,
    COMITE: COMITE,
    GERENTE: GERENTE,
}


class WorkflowError(Exception):
    """Raised when an action is illegal for the current user/candidate state."""


def role_stage(role: str) -> Optional[str]:
    return ROLE_STAGE.get(role)


def next_stage(stage: str) -> Optional[str]:
    try:
        i = STAGES.index(stage)
    except ValueError:
        return None
    return STAGES[i + 1] if i + 1 < len(STAGES) else None


def prev_stage(stage: str) -> Optional[str]:
    try:
        i = STAGES.index(stage)
    except ValueError:
        return None
    return STAGES[i - 1] if i > 0 else None


def _log(
    db: Session,
    candidate: models.LocationCandidate,
    stage: str,
    user: models.User,
    action: str,
    note: Optional[str],
) -> models.Review:
    created_at = datetime.now(timezone.utc)
    review = models.Review(
        candidate_id=candidate.id,
        stage=stage,
        reviewer_id=user.id,
        action=action,
        note=note,
        created_at=created_at,
    )
    db.add(review)
    return review


def _workflow_group_for_status(candidate: models.LocationCandidate) -> str:
    return GROUP_TO_DB.get(DB_TO_GROUP.get(candidate.status or "", "pending"), PENDING)


def _sync_candidate_workflow_columns(
    candidate: models.LocationCandidate,
    review: models.Review,
    user: models.User,
    previous_group: str,
) -> None:
    candidate.workflow_group = _workflow_group_for_status(candidate)
    candidate.last_action = review.action
    candidate.last_action_at = review.created_at
    candidate.last_actor_role = user.role
    if review.action == "reject":
        candidate.last_reject_note = review.note
        candidate.rejected_at = review.created_at
        if previous_group == "approved":
            candidate.rejected_from_approved_at = review.created_at
        elif previous_group == "project":
            candidate.rejected_from_project_at = review.created_at
    elif review.action == "like":
        candidate.suggested_at = review.created_at
    elif review.action == "dislike":
        pass
    elif review.action == "star" and user.role in JEFATURA_LIKE_ROLES | {ARRIENDO}:
        candidate.suggested_at = review.created_at
    elif review.action in {"accept", "star"}:
        candidate.approved_at = review.created_at
    elif review.action == "project":
        candidate.project_at = review.created_at
    elif review.action == "opening":
        candidate.project_at = review.created_at
    elif review.action == "skip":
        candidate.skipped_at = review.created_at
    elif review.action == "send_back":
        candidate.returned_at = review.created_at
    elif review.action == "reopen":
        candidate.reopened_at = review.created_at


def last_decision(db: Session, candidate_id: int) -> Optional[models.Review]:
    return db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .where(models.Review.action.in_(DECIDING_ACTIONS))
        .order_by(models.Review.created_at.desc(), models.Review.id.desc())
        .limit(1)
    ).first()


def last_action(db: Session, candidate_id: int) -> Optional[models.Review]:
    return db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .order_by(models.Review.created_at.desc(), models.Review.id.desc())
        .limit(1)
    ).first()


def last_reject(db: Session, candidate_id: int) -> Optional[models.Review]:
    return db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .where(models.Review.action == "reject")
        .order_by(models.Review.created_at.desc(), models.Review.id.desc())
        .limit(1)
    ).first()


def candidate_group(db: Session, candidate: models.LocationCandidate) -> str:
    group = DB_TO_GROUP.get(candidate.workflow_group or "")
    if group:
        return group
    status_group = DB_TO_GROUP.get(candidate.status or "")
    if status_group:
        return status_group
    dec = last_decision(db, candidate.id)
    if dec and dec.action == "reject":
        return "rejected"
    if dec and dec.action == "like":
        return "suggested"
    if dec and dec.action in {"accept", "star"}:
        return "approved"
    return "pending"


def can_act(db: Session, user: models.User, candidate: models.LocationCandidate, action: str) -> bool:
    if user.role == SYSADMIN:
        return True
    group = candidate_group(db, candidate)
    if user.role in JEFATURA_LIKE_ROLES:
        return (
            (group == "pending" and action in {"accept", "like", "dislike", "star", "skip"})
            or (group == "approved" and action == "opening")
        )
    if user.role == ARRIENDO:
        return (
            (group == "pending" and action in {"accept", "reject", "like", "dislike", "star", "skip"})
            or (group == "suggested" and action in {"accept", "reject", "skip"})
            or (group == "approved" and action == "reject")
        )
    if user.role in {COMITE, GERENTE}:
        return (
            (group in {"pending", "suggested"} and action in {"accept", "reject"})
            or (group == "approved" and action == "reject")
        )
    return False


def submit_review(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    action: str,
    note: Optional[str] = None,
) -> models.Review:
    if action not in {"accept", "reject", "star", "skip", "project", "like", "dislike", "opening"}:
        raise WorkflowError(f"Unknown review action: {action!r}")

    if action in {"reject", "dislike"} and not (note or "").strip():
        raise WorkflowError("Rejecting a candidate requires a comment.")

    effective_action = action
    if user.role in JEFATURA_LIKE_ROLES and action == "accept":
        effective_action = "like"
    elif user.role in JEFATURA_LIKE_ROLES and action == "reject":
        effective_action = "dislike"
    current_group = candidate_group(db, candidate)
    if current_group == "opening":
        raise WorkflowError("Proyecto is a final state and cannot be changed.")
    if effective_action == "opening":
        variables = candidate.project_variables or db.scalar(
            select(models.CandidateProjectVariables).where(
                models.CandidateProjectVariables.candidate_id == candidate.id
            )
        )
        missing = [
            label
            for attr, label in (
                ("cve_unidad", "CveUnidad"),
                ("unidad", "Unidad"),
                ("region", "Region"),
                ("comuna", "Comuna"),
            )
            if not (getattr(variables, attr, None) if variables else None)
        ]
        if missing:
            raise WorkflowError("Complete Variables before moving to Proyecto: " + ", ".join(missing))
    if not can_act(db, user, candidate, effective_action):
        raise WorkflowError(
            f"User role {user.role!r} cannot {action!r} this candidate."
        )

    stage = role_stage(user.role) or candidate.current_stage or COMITE
    review = _log(db, candidate, stage, user, effective_action, note)

    if effective_action == "skip":
        pass
    elif effective_action == "like":
        pass
    elif effective_action == "dislike":
        pass
    elif effective_action == "star" and user.role in JEFATURA_LIKE_ROLES | {ARRIENDO}:
        candidate.priority = True
        candidate.current_stage = COMITE
        candidate.status = SUGGESTED
    elif effective_action in {"accept", "star"}:
        if effective_action == "star":
            candidate.priority = True
        candidate.current_stage = APPROVED_STAGE
        candidate.status = APPROVED_FINAL
    elif effective_action == "reject":
        candidate.current_stage = stage
        candidate.status = REJECTED
    elif effective_action == "project":
        candidate.current_stage = DONE
        candidate.status = PROJECT
    elif effective_action == "opening":
        candidate.current_stage = PROJECT_STAGE
        candidate.status = OPENING

    _sync_candidate_workflow_columns(candidate, review, user, current_group)
    db.flush()
    return review


def send_back(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    note: Optional[str] = None,
) -> models.Review:
    if user.role != SYSADMIN:
        raise WorkflowError("Only sysadmin can send candidates back manually.")
    previous_group = candidate_group(db, candidate)
    review = _log(db, candidate, candidate.current_stage, user, "send_back", note)
    candidate.current_stage = COMITE
    candidate.status = RETURNED
    _sync_candidate_workflow_columns(candidate, review, user, previous_group)
    db.flush()
    return review


def reopen(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    note: Optional[str] = None,
) -> models.Review:
    if user.role != SYSADMIN:
        raise WorkflowError("Only sysadmin can reopen candidates manually.")
    previous_group = candidate_group(db, candidate)
    review = _log(db, candidate, candidate.current_stage, user, "reopen", note)
    candidate.current_stage = COMITE
    candidate.status = RETURNED
    _sync_candidate_workflow_columns(candidate, review, user, previous_group)
    db.flush()
    return review


def _numeric_score(candidate: models.LocationCandidate) -> Optional[float]:
    display_data = candidate.display_data or {}
    value = (
        display_data.get("ScoreTotal")
        or display_data.get("SCORETOTAL")
        or display_data.get("score_total")
    )
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+(?:[\.,]\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def candidates_for_role(
    db: Session,
    role: str,
    project_id: Optional[str] = None,
    sort_by: str = "score",
    sort_dir: str = "desc",
    candidates: Optional[list[models.LocationCandidate]] = None,
) -> list[models.LocationCandidate]:
    if candidates is None:
        q = select(models.LocationCandidate).order_by(models.LocationCandidate.id.asc())
        if project_id is not None:
            q = q.where(models.LocationCandidate.project_id == project_id)
        candidates = db.scalars(q).all()

    if role in JEFATURA_LIKE_ROLES:
        allowed = {"pending"}
    elif role in COMITE_LIKE_ROLES:
        allowed = {"pending", "suggested", "approved"}
    else:
        return []

    group_priority = {
        JEFATURA: {"pending": 0},
        JEFE_COMERCIAL: {"pending": 0},
        COORDINADOR: {"pending": 0},
        ARRIENDO: {"suggested": 0, "pending": 1, "approved": 2, "rejected": 3},
        COMITE: {"suggested": 0, "pending": 1, "approved": 2, "rejected": 3},
        GERENTE: {"suggested": 0, "pending": 1, "approved": 2, "rejected": 3},
    }[role]

    filtered = [c for c in candidates if candidate_group(db, c) in allowed]

    sort_by = sort_by if sort_by in QUEUE_SORT_FIELDS else "score"
    sort_dir = sort_dir if sort_dir in {"asc", "desc"} else "desc"
    descending = sort_dir == "desc"

    def queue_key(candidate: models.LocationCandidate):
        group = candidate_group(db, candidate)
        last_action_name = candidate.last_action
        last_ts = candidate.last_action_at
        score = _numeric_score(candidate)
        if sort_by == "score":
            sort_value = score if score is not None else (float("-inf") if descending else float("inf"))
        else:
            sort_value = candidate.id
        if descending:
            sort_value = -sort_value
        return (
            group_priority.get(group, 99),
            1 if last_action_name == "skip" else 0,
            sort_value,
            last_ts or datetime.min,
            candidate.id,
        )

    return sorted(filtered, key=queue_key)


def queue_query(stage: str, project_id: Optional[str] = None):
    """Legacy helper kept for exports/tests that still expect a selectable query."""
    q = select(models.LocationCandidate).order_by(models.LocationCandidate.id.asc())
    if project_id is not None:
        q = q.where(models.LocationCandidate.project_id == project_id)
    return q


def next_for_role(
    db: Session,
    role: str,
    project_id: Optional[str] = None,
    sort_by: str = "score",
    sort_dir: str = "desc",
) -> Optional[models.LocationCandidate]:
    items = candidates_for_role(db, role, project_id, sort_by, sort_dir)
    return items[0] if items else None


def current_decision(
    db: Session, candidate_id: int, stage: str
) -> Optional[models.Review]:
    return db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .where(models.Review.stage == stage)
        .where(models.Review.action.in_(DECIDING_ACTIONS))
        .order_by(models.Review.created_at.desc(), models.Review.id.desc())
        .limit(1)
    ).first()
