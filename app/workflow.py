"""Multi-layer review workflow engine.

A candidate flows through three sequential review layers:

    coordinator -> manager -> director -> (approved_final)

Each layer can approve, reject, star (strong-accept that advances) or skip
(defer, no decision). A reviewer one layer up can send a candidate back one
step; a rejected candidate can be reopened and resumes at the stage where it
was rejected. Every action is recorded in the append-only ``Review`` log.

This module holds the pure state-transition logic. It does not enforce
authentication — it only checks that the acting user's *role* is allowed to
act on the candidate's *current stage* (sysadmin may act anywhere).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models

# Ordered review layers. Index defines "one step up / down".
STAGES: tuple[str, ...] = ("coordinator", "manager", "director")
DONE = "done"

# Candidate.status values.
PENDING = "pending"
RETURNED = "returned"          # sent back to a lower layer, awaiting re-review
REJECTED = "rejected"
APPROVED_FINAL = "approved_final"
ACTIVE_STATUSES = frozenset({PENDING, RETURNED})

# Review.action values that constitute a gating decision.
DECIDING_ACTIONS = frozenset({"accept", "reject", "star"})

# Map a user role to the stage it owns. sysadmin owns no fixed stage.
ROLE_STAGE = {
    "coordinator": "coordinator",
    "manager": "manager",
    "director": "director",
}


class WorkflowError(Exception):
    """Raised when an action is illegal for the candidate's current state."""


# --------------------------------------------------------------------------- #
# Stage helpers
# --------------------------------------------------------------------------- #
def role_stage(role: str) -> Optional[str]:
    return ROLE_STAGE.get(role)


def next_stage(stage: str) -> Optional[str]:
    """The layer after ``stage``, or None if ``stage`` is the last one."""
    i = STAGES.index(stage)
    return STAGES[i + 1] if i + 1 < len(STAGES) else None


def prev_stage(stage: str) -> Optional[str]:
    """The layer before ``stage``, or None if ``stage`` is the first one."""
    i = STAGES.index(stage)
    return STAGES[i - 1] if i > 0 else None


def can_act(user: models.User, candidate: models.LocationCandidate) -> bool:
    """Whether ``user`` may act on ``candidate`` at its current stage."""
    if user.role == "sysadmin":
        return True
    return (
        candidate.current_stage in STAGES
        and role_stage(user.role) == candidate.current_stage
    )


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def submit_review(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    action: str,
    note: Optional[str] = None,
) -> models.Review:
    """Record an accept / reject / star / skip at the candidate's current stage.

    - accept / star : advance to the next layer (or approved_final at director);
                      star additionally flags the candidate as priority.
    - reject        : mark rejected (current_stage unchanged so reopen resumes here).
    - skip          : log only; no state change (candidate stays in this queue).
    """
    if action not in ("accept", "reject", "star", "skip"):
        raise WorkflowError(f"Unknown review action: {action!r}")
    if candidate.status not in ACTIVE_STATUSES:
        raise WorkflowError(
            f"Candidate is {candidate.status!r}; cannot review until reopened/active."
        )
    if not can_act(user, candidate):
        raise WorkflowError(
            f"User role {user.role!r} cannot act on stage {candidate.current_stage!r}."
        )

    stage = candidate.current_stage
    review = _log(db, candidate, stage, user, action, note)

    if action == "skip":
        pass  # deferred — no state change
    elif action in ("accept", "star"):
        if action == "star":
            candidate.priority = True
        nxt = next_stage(stage)
        if nxt is None:
            candidate.current_stage = DONE
            candidate.status = APPROVED_FINAL
        else:
            candidate.current_stage = nxt
            candidate.status = PENDING
    elif action == "reject":
        candidate.status = REJECTED  # current_stage stays where it was rejected

    db.flush()
    return review


def send_back(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    note: Optional[str] = None,
) -> models.Review:
    """Bounce the candidate one layer down for re-review (manager/director only)."""
    if candidate.status not in ACTIVE_STATUSES:
        raise WorkflowError(f"Candidate is {candidate.status!r}; cannot send back.")
    if not can_act(user, candidate):
        raise WorkflowError(
            f"User role {user.role!r} cannot act on stage {candidate.current_stage!r}."
        )
    prev = prev_stage(candidate.current_stage)
    if prev is None:
        raise WorkflowError("Coordinator is the first layer; cannot send back further.")

    review = _log(db, candidate, candidate.current_stage, user, "send_back", note)
    candidate.current_stage = prev
    candidate.status = RETURNED
    db.flush()
    return review


def reopen(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    note: Optional[str] = None,
) -> models.Review:
    """Reopen a rejected candidate; it resumes at the stage where it was rejected.

    Allowed for the reviewer who owns that stage, or any sysadmin.
    """
    if candidate.status != REJECTED:
        raise WorkflowError("Only rejected candidates can be reopened.")
    if user.role != "sysadmin" and role_stage(user.role) != candidate.current_stage:
        raise WorkflowError(
            f"User role {user.role!r} cannot reopen at stage {candidate.current_stage!r}."
        )

    review = _log(db, candidate, candidate.current_stage, user, "reopen", note)
    candidate.status = RETURNED  # resumes in the same stage's queue
    db.flush()
    return review


# --------------------------------------------------------------------------- #
# Queues
# --------------------------------------------------------------------------- #
def queue_query(stage: str, project_id: Optional[str] = None):
    """SQLAlchemy select for a stage's inbox, skip-aware ordering.

    Order: candidates never acted on at this stage first (NULL timestamp),
    then by the most-recent action at this stage ascending — so a just-skipped
    candidate drops to the back while longest-waiting ones surface first.
    """
    last_action = (
        select(
            models.Review.candidate_id.label("cid"),
            func.max(models.Review.created_at).label("ts"),
        )
        .where(models.Review.stage == stage)
        .group_by(models.Review.candidate_id)
        .subquery()
    )

    q = (
        select(models.LocationCandidate)
        .outerjoin(last_action, last_action.c.cid == models.LocationCandidate.id)
        .where(models.LocationCandidate.current_stage == stage)
        .where(models.LocationCandidate.status.in_(ACTIVE_STATUSES))
        .order_by(
            last_action.c.ts.asc().nullsfirst(),
            models.LocationCandidate.id.asc(),
        )
    )
    if project_id is not None:
        q = q.where(models.LocationCandidate.project_id == project_id)
    return q


def next_for_role(
    db: Session, role: str, project_id: Optional[str] = None
) -> Optional[models.LocationCandidate]:
    """The next candidate a given role should review, or None if the queue is empty."""
    stage = role_stage(role)
    if stage is None:
        return None  # sysadmin has no review queue of its own
    return db.scalars(queue_query(stage, project_id).limit(1)).first()


def current_decision(
    db: Session, candidate_id: int, stage: str
) -> Optional[models.Review]:
    """The latest gating decision (accept/reject/star) recorded at ``stage``."""
    return db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .where(models.Review.stage == stage)
        .where(models.Review.action.in_(DECIDING_ACTIONS))
        .order_by(models.Review.created_at.desc(), models.Review.id.desc())
        .limit(1)
    ).first()
