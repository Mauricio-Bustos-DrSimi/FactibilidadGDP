"""Role-based review workflow for candidate locations.

Groups shown in the UI:
    pending -> suggested -> approved -> project
    pending -> rejected -> approved

Roles:
    jefatura: like/dislike pending candidates.
    comite: approve/reject suggested, approved, or rejected candidates.
    gerente: promote approved candidates to project locations.
    sysadmin: unrestricted oversight.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

JEFATURA = "jefatura"
COMITE = "comite"
GERENTE = "gerente"
SYSADMIN = "sysadmin"

STAGES: tuple[str, ...] = (JEFATURA, COMITE, GERENTE)
DONE = "done"

PENDING = "pending"
RETURNED = "returned"
REJECTED = "rejected"
SUGGESTED = "suggested"
APPROVED_FINAL = "approved_final"
PROJECT = "locales_proyecto"
ACTIVE_STATUSES = frozenset({PENDING, RETURNED})

DECIDING_ACTIONS = frozenset({"accept", "reject", "star", "project", "like"})

ROLE_STAGE = {
    JEFATURA: JEFATURA,
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
    review = models.Review(
        candidate_id=candidate.id,
        stage=stage,
        reviewer_id=user.id,
        action=action,
        note=note,
    )
    db.add(review)
    return review


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
    if candidate.status == PROJECT:
        return "project"
    dec = last_decision(db, candidate.id)
    if candidate.status == REJECTED or (dec and dec.action == "reject"):
        return "rejected"
    if candidate.status == SUGGESTED or (dec and dec.action == "like"):
        return "suggested"
    if candidate.status == APPROVED_FINAL or (dec and dec.action in {"accept", "star"}):
        return "approved"
    return "pending"


def can_act(db: Session, user: models.User, candidate: models.LocationCandidate, action: str) -> bool:
    if user.role == SYSADMIN:
        return True
    group = candidate_group(db, candidate)
    if user.role == JEFATURA:
        return (
            (group == "pending" and action in {"accept", "like", "reject", "skip"})
            or (group == "suggested" and action == "reject")
            or (group == "rejected" and action in {"accept", "like"})
        )
    if user.role == COMITE:
        return group in {"suggested", "approved", "rejected"} and action in {"accept", "reject", "skip"}
    if user.role == GERENTE:
        return (
            (group == "approved" and action in {"accept", "project", "reject", "skip"})
            or (group == "project" and action == "reject")
        )
    return False


def submit_review(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    action: str,
    note: Optional[str] = None,
) -> models.Review:
    if action not in {"accept", "reject", "star", "skip", "project", "like"}:
        raise WorkflowError(f"Unknown review action: {action!r}")

    if action == "reject" and not (note or "").strip():
        raise WorkflowError("Rejecting a candidate requires a comment.")

    effective_action = "project" if user.role == GERENTE and action == "accept" else action
    if user.role == JEFATURA and action == "accept":
        effective_action = "like"
    current_group = candidate_group(db, candidate)
    if user.role == JEFATURA and current_group == "rejected" and effective_action == "like" and not (note or "").strip():
        raise WorkflowError("Suggesting a rejected candidate requires a comment.")
    if not can_act(db, user, candidate, effective_action):
        raise WorkflowError(
            f"User role {user.role!r} cannot {action!r} this candidate."
        )

    stage = role_stage(user.role) or candidate.current_stage or COMITE
    review = _log(db, candidate, stage, user, effective_action, note)

    if effective_action == "skip":
        pass
    elif effective_action == "like":
        candidate.current_stage = COMITE
        candidate.status = SUGGESTED
    elif effective_action in {"accept", "star"}:
        if effective_action == "star":
            candidate.priority = True
        candidate.current_stage = COMITE
        candidate.status = APPROVED_FINAL
    elif effective_action == "reject":
        candidate.current_stage = stage
        candidate.status = REJECTED
    elif effective_action == "project":
        candidate.current_stage = DONE
        candidate.status = PROJECT

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
    review = _log(db, candidate, candidate.current_stage, user, "send_back", note)
    candidate.current_stage = COMITE
    candidate.status = RETURNED
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
    review = _log(db, candidate, candidate.current_stage, user, "reopen", note)
    candidate.current_stage = COMITE
    candidate.status = RETURNED
    db.flush()
    return review


def candidates_for_role(
    db: Session,
    role: str,
    project_id: Optional[str] = None,
) -> list[models.LocationCandidate]:
    q = select(models.LocationCandidate).order_by(models.LocationCandidate.id.asc())
    if project_id is not None:
        q = q.where(models.LocationCandidate.project_id == project_id)
    candidates = db.scalars(q).all()

    if role == JEFATURA:
        allowed = {"pending", "suggested", "rejected"}
    elif role == COMITE:
        allowed = {"suggested", "approved", "rejected"}
    elif role == GERENTE:
        allowed = {"approved", "project"}
    else:
        return []

    group_priority = {
        JEFATURA: {"pending": 0, "suggested": 1, "rejected": 2},
        COMITE: {"suggested": 0, "approved": 1, "rejected": 2},
        GERENTE: {"approved": 0, "project": 1},
    }[role]

    filtered = [c for c in candidates if candidate_group(db, c) in allowed]

    def queue_key(candidate: models.LocationCandidate):
        group = candidate_group(db, candidate)
        last = last_action(db, candidate.id)
        last_ts = last.created_at if last else None
        return (
            group_priority.get(group, 99),
            1 if last and last.action == "skip" else 0,
            last_ts or datetime.min.replace(tzinfo=timezone.utc),
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
    db: Session, role: str, project_id: Optional[str] = None
) -> Optional[models.LocationCandidate]:
    items = candidates_for_role(db, role, project_id)
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
