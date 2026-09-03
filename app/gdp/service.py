"""Application service for the replicated Gestor de Proyecciones domain.

The service owns GDP query and command orchestration.  Compatibility callbacks
keep legacy projections, visibility and response assembly stable while those
pieces are migrated incrementally from the original composition root.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, workflow


@dataclass(frozen=True)
class GDPAdapters:
    candidate_out: Callable[[Session, models.LocationCandidate], schemas.CandidateOut]
    visible_candidates: Callable[
        [Session, models.User, Optional[str], Optional[str]],
        list[models.LocationCandidate],
    ]
    queue_visible_candidates: Callable[
        [Session, models.User, Optional[str], Optional[str]],
        list[models.LocationCandidate],
    ]
    require_candidate_visible: Callable[
        [Session, models.LocationCandidate, models.User, Optional[str]], None
    ]
    candidate_by_projection_id: Callable[
        [Session, str], Optional[models.LocationCandidate]
    ]
    candidate_audit_payload: Callable[[Session, models.LocationCandidate], dict]
    max_projection_id: Callable[[Session], int]
    stats_payload: Callable[[Session, Optional[str]], dict]
    review_out: Callable[[models.Review], schemas.ReviewOut]
    versioned_image_url: Callable[[Optional[str]], Optional[str]]
    require_viewer_read_only: Callable[[models.User], None]
    require_current_approval_division: Callable[
        [Session, models.LocationCandidate, str, Optional[str]], None
    ]
    ensure_project_activation_variables: Callable[[Session, models.LocationCandidate], None]
    ensure_review_session_started: Callable[[Request], None]
    approval_notification_outbox_id: Callable[
        [Session, models.LocationCandidate, models.Review, str, str, Optional[str]],
        Optional[int],
    ]
    deliver_approval_notification: Callable[[int], None]
    action_out: Callable[..., schemas.CandidateActionOut]


class GDPService:
    """Deep interface used by GDP HTTP adapters."""

    def __init__(self, adapters: GDPAdapters) -> None:
        self._adapters = adapters

    def create_project(self, db: Session, payload: schemas.ProjectCreate) -> models.Project:
        project = models.Project(
            name=payload.name,
            project_url=payload.project_url,
            notes=payload.notes,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    def list_projects(self, db: Session) -> list[models.Project]:
        return list(
            db.scalars(select(models.Project).order_by(models.Project.created_at.desc())).all()
        )

    def get_project(self, db: Session, project_id: str) -> models.Project:
        project = db.get(models.Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        return project

    def queue(
        self,
        db: Session,
        user: models.User,
        project_id: Optional[str],
        sort_by: str,
        sort_dir: str,
        division: Optional[str],
    ) -> schemas.QueueOut:
        stage = workflow.role_stage(user.role)
        if stage is None:
            return schemas.QueueOut(candidate=None, remaining=0, stage=None)
        visible = self._adapters.queue_visible_candidates(db, user, project_id, division)
        candidates = workflow.candidates_for_role(
            db, user.role, project_id, sort_by, sort_dir, candidates=visible
        )
        candidate = candidates[0] if candidates else None
        return schemas.QueueOut(
            candidate=self._adapters.candidate_out(db, candidate) if candidate else None,
            remaining=len(candidates),
            stage=stage,
        )

    def list_candidates(
        self,
        db: Session,
        user: models.User,
        project_id: Optional[str],
        division: Optional[str],
    ) -> list[schemas.CandidateOut]:
        return [
            self._adapters.candidate_out(db, candidate)
            for candidate in self._adapters.visible_candidates(db, user, project_id, division)
        ]

    def funnel_baseline(self, db: Session) -> dict[str, int]:
        return {"max_projection_id": self._adapters.max_projection_id(db)}

    def candidate_by_projection(
        self,
        db: Session,
        user: models.User,
        projection_id: str,
        division: Optional[str],
    ) -> schemas.CandidateOut:
        candidate = self._adapters.candidate_by_projection_id(db, projection_id)
        if not candidate:
            raise HTTPException(404, "Projection ID not found.")
        self._adapters.require_candidate_visible(db, candidate, user, division)
        return self._adapters.candidate_out(db, candidate)

    def candidate_audit_by_projection(
        self,
        db: Session,
        user: models.User,
        projection_id: str,
        division: Optional[str],
    ) -> dict:
        candidate = self._adapters.candidate_by_projection_id(db, projection_id)
        if not candidate:
            raise HTTPException(404, "Projection ID not found.")
        self._adapters.require_candidate_visible(db, candidate, user, division)
        return self._adapters.candidate_audit_payload(db, candidate)

    def candidate(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        division: Optional[str],
    ) -> schemas.CandidateOut:
        candidate = self._candidate(db, candidate_id)
        self._adapters.require_candidate_visible(db, candidate, user, division)
        return self._adapters.candidate_out(db, candidate)

    def resolve_candidate(self, db: Session, candidate_id: int) -> models.LocationCandidate:
        """Resolve a GDP candidate for cross-cutting adapters such as documents."""
        return self._candidate(db, candidate_id)

    def reviews(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        division: Optional[str],
    ) -> list[schemas.ReviewOut]:
        candidate = self._candidate(db, candidate_id)
        self._adapters.require_candidate_visible(db, candidate, user, division)
        reviews = db.scalars(
            select(models.Review)
            .where(models.Review.candidate_id == candidate_id)
            .order_by(models.Review.created_at, models.Review.id)
        ).all()
        return [self._adapters.review_out(review) for review in reviews]

    def comment(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        payload: schemas.NoteIn,
        division: Optional[str],
    ) -> schemas.ReviewOut:
        self._adapters.require_viewer_read_only(user)
        candidate = self._candidate(db, candidate_id)
        self._adapters.require_candidate_visible(db, candidate, user, division)
        note = (payload.note or "").strip()
        if not note:
            raise HTTPException(400, "A comment is required.")
        review = models.Review(
            candidate_id=candidate.id,
            stage=workflow.role_stage(user.role) or candidate.current_stage or workflow.COMITE,
            reviewer_id=user.id,
            action="comment",
            note=note,
            created_at=datetime.now(timezone.utc),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return self._adapters.review_out(review)

    def update_status(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        payload: schemas.CandidateStatusUpdate,
        request: Request,
        background_tasks: BackgroundTasks,
        sort_by: str,
        sort_dir: str,
        division: Optional[str],
    ) -> schemas.CandidateActionOut:
        self._adapters.require_viewer_read_only(user)
        candidate = self._candidate(db, candidate_id)
        self._adapters.require_candidate_visible(db, candidate, user, division)
        if payload.group == "pending":
            current_group = workflow.candidate_group(db, candidate)
            is_approver_return = (
                user.role in workflow.APPROVER_ROLES
                and current_group in {"proposed", "rejected"}
            )
            if user.role != workflow.SYSADMIN and not is_approver_return:
                raise HTTPException(
                    403,
                    "Only Sysadmin, Arriendos y Patentes, or Gerente from Propuestos or Rechazados can return candidates to Pendientes.",
                )
            if is_approver_return and not (payload.note or "").strip():
                raise HTTPException(
                    400,
                    "Arriendos y Patentes or Gerente must provide a comment when returning a candidate to Pendientes.",
                )
            stage = (
                user.role
                if is_approver_return
                else candidate.current_stage
                if candidate.current_stage in workflow.STAGES
                else workflow.COMITE
            )
            action = "send_back" if is_approver_return else "reopen"
            review = models.Review(
                candidate_id=candidate.id,
                stage=stage,
                reviewer_id=user.id,
                action=action,
                note=(payload.note or "").strip() or None,
                created_at=datetime.now(timezone.utc),
            )
            db.add(review)
            candidate.current_stage = stage
            candidate.status = workflow.RETURNED
            candidate.workflow_group = workflow.PENDING
            candidate.last_action = action
            candidate.last_action_at = review.created_at
            candidate.last_actor_role = user.role
            if is_approver_return:
                candidate.returned_at = candidate.last_action_at
            else:
                candidate.reopened_at = candidate.last_action_at
            db.commit()
        else:
            previous_group = workflow.candidate_group(db, candidate)
            action = {
                "proposed": "accept",
                "approved": "project",
                "rejected": "reject",
                "study": "study",
                "opening": "opening",
                "skip": "skip",
            }[payload.group]
            self._adapters.require_current_approval_division(
                db, candidate, action, payload.note
            )
            if action == "opening":
                self._adapters.ensure_project_activation_variables(db, candidate)
            if user.role in workflow.COMITE_LIKE_ROLES and action in {"project", "reject"}:
                self._adapters.ensure_review_session_started(request)
            review = self._workflow_review(db, candidate, user, action, payload.note)
            notification_event_id = self._adapters.approval_notification_outbox_id(
                db, candidate, review, previous_group, action, payload.note
            )
            db.commit()
            if notification_event_id is not None:
                background_tasks.add_task(
                    self._adapters.deliver_approval_notification,
                    notification_event_id,
                )
        db.refresh(candidate)
        return self._adapters.action_out(
            db,
            candidate,
            user,
            sort_by=sort_by,
            sort_dir=sort_dir,
            commercial_division=division,
        )

    def submit_review(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        payload: schemas.ReviewCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        sort_by: str,
        sort_dir: str,
        division: Optional[str],
    ) -> schemas.CandidateActionOut:
        self._adapters.require_viewer_read_only(user)
        candidate = self._candidate(db, candidate_id)
        self._adapters.require_candidate_visible(db, candidate, user, division)
        self._adapters.require_current_approval_division(
            db, candidate, payload.action, payload.note
        )
        previous_group = workflow.candidate_group(db, candidate)
        if (
            user.role in workflow.COMITE_LIKE_ROLES
            and payload.action in {"accept", "project", "reject"}
        ):
            self._adapters.ensure_review_session_started(request)
        review = self._workflow_review(
            db, candidate, user, payload.action, payload.note
        )
        notification_event_id = self._adapters.approval_notification_outbox_id(
            db, candidate, review, previous_group, payload.action, payload.note
        )
        db.commit()
        if notification_event_id is not None:
            background_tasks.add_task(
                self._adapters.deliver_approval_notification,
                notification_event_id,
            )
        db.refresh(candidate)
        return self._adapters.action_out(
            db,
            candidate,
            user,
            sort_by=sort_by,
            sort_dir=sort_dir,
            commercial_division=division,
        )

    def send_back(
        self, db: Session, user: models.User, candidate_id: int, payload: schemas.NoteIn
    ) -> schemas.CandidateOut:
        self._adapters.require_viewer_read_only(user)
        candidate = self._candidate(db, candidate_id)
        try:
            workflow.send_back(db, candidate, user, payload.note)
        except workflow.WorkflowError as exc:
            raise HTTPException(409, str(exc)) from exc
        db.commit()
        db.refresh(candidate)
        return self._adapters.candidate_out(db, candidate)

    def reopen(
        self, db: Session, user: models.User, candidate_id: int, payload: schemas.NoteIn
    ) -> schemas.CandidateOut:
        self._adapters.require_viewer_read_only(user)
        candidate = self._candidate(db, candidate_id)
        try:
            workflow.reopen(db, candidate, user, payload.note)
        except workflow.WorkflowError as exc:
            raise HTTPException(409, str(exc)) from exc
        db.commit()
        db.refresh(candidate)
        return self._adapters.candidate_out(db, candidate)

    def stats(self, db: Session, project_id: Optional[str]) -> dict:
        return self._adapters.stats_payload(db, project_id)

    def business(self, db: Session) -> list[schemas.BusinessOut]:
        result: list[schemas.BusinessOut] = []
        for row in db.scalars(select(models.BusinessLocation)).all():
            attributes = dict(row.attributes or {})
            if "image_url" in attributes:
                attributes["image_url"] = self._adapters.versioned_image_url(
                    attributes["image_url"]
                )
            result.append(
                schemas.BusinessOut(
                    id=row.id,
                    name=row.name,
                    lat=row.lat,
                    lng=row.lng,
                    category=row.category,
                    attributes=attributes,
                )
            )
        return result

    @staticmethod
    def _workflow_review(
        db: Session,
        candidate: models.LocationCandidate,
        user: models.User,
        action: str,
        note: Optional[str],
    ) -> models.Review:
        try:
            return workflow.submit_review(db, candidate, user, action, note)
        except workflow.WorkflowError as exc:
            raise HTTPException(409, str(exc)) from exc

    @staticmethod
    def _candidate(db: Session, candidate_id: int) -> models.LocationCandidate:
        candidate = db.get(models.LocationCandidate, candidate_id)
        if not candidate:
            raise HTTPException(404, "Candidate not found")
        return candidate
