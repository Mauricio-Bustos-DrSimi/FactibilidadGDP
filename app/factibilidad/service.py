"""Use cases and transaction boundaries for Factibilidad."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.factibility_timing import completion_timestamp
from app.factibilidad.definitions import FACTIBILITY_TASK_INDEX
from app.factibilidad.progress import build_progress
from app.factibilidad.repository import FactibilityRepository


@dataclass(frozen=True)
class FactibilityAdapters:
    candidate_out: Callable[[Session, models.LocationCandidate], schemas.CandidateOut]
    projection_id: Callable[[models.LocationCandidate], str]
    read_sales_sheet: Callable[[models.LocationCandidate], dict]
    write_sales_sheet: Callable[
        [models.LocationCandidate, schemas.CandidateProjectVariablesIn], dict
    ]
    files_state: Callable[[], tuple[int, int]]


class FactibilityService:
    """Deep application interface for every non-filesystem Factibilidad action."""

    def __init__(
        self,
        repository: FactibilityRepository,
        adapters: FactibilityAdapters,
    ) -> None:
        self._repository = repository
        self._adapters = adapters

    def list_locations(self, db: Session) -> list[dict]:
        candidates = self._repository.project_candidates(db)
        candidate_ids = [candidate.id for candidate in candidates]
        progress = self._repository.progress_for_candidates(db, candidate_ids)
        decisions = self._repository.decisions_for_candidates(db, candidate_ids)
        approvals = self._repository.approvals_for_candidates(db, candidate_ids)
        return [
            self._location_payload(
                db,
                candidate,
                progress.get(candidate.id, []),
                decisions.get(candidate.id),
                approvals.get(candidate.id, []),
            )
            for candidate in candidates
        ]

    def location(self, db: Session, candidate_id: int) -> dict:
        candidate = self._project_candidate(db, candidate_id)
        return self._location_payload(db, candidate)

    def update_task(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        task_key: str,
        payload: schemas.FactibilityTaskUpdate,
    ) -> dict:
        candidate = self._project_candidate(db, candidate_id)
        projection_id = self._adapters.projection_id(candidate)
        definition = FACTIBILITY_TASK_INDEX.get(task_key)
        if not definition:
            raise HTTPException(404, "La tarea de Factibilidad no existe.")
        row = self._repository.task(db, candidate_id, task_key)
        if row is None:
            row = models.FactibilityTaskProgress(
                candidate_id=candidate_id,
                projection_id=projection_id,
                group_key=definition[1],
                task_key=task_key,
            )
            db.add(row)
        else:
            row.projection_id = projection_id
        now = datetime.now(timezone.utc)
        row.completed_at = completion_timestamp(
            row.status,
            payload.status,
            row.completed_at,
            now,
        )
        row.status = payload.status
        row.comment = (payload.comment or "").strip() or None
        row.updated_by_id = user.id
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return {
            "candidate_id": candidate_id,
            "group_key": row.group_key,
            "task_key": row.task_key,
            "status": row.status,
            "comment": row.comment,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
        }

    def update_decision(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        payload: schemas.FactibilityDecisionUpdate,
    ) -> dict:
        candidate = self._project_candidate(db, candidate_id)
        projection_id = self._adapters.projection_id(candidate)
        row = self._repository.decision_for_candidate(db, candidate_id)
        if row is None:
            row = models.FactibilityLocationDecision(
                candidate_id=candidate_id,
                projection_id=projection_id,
            )
            db.add(row)
        else:
            row.projection_id = projection_id
        row.decision = payload.decision
        row.updated_by_id = user.id
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return {
            "candidate_id": candidate_id,
            "decision": row.decision,
            "updated_at": row.updated_at,
        }

    def approve_area(
        self,
        db: Session,
        user: models.User,
        candidate_id: int,
        area: schemas.FactibilityApprovalArea,
    ) -> dict:
        candidate = self._project_candidate(db, candidate_id)
        projection_id = self._adapters.projection_id(candidate)
        row = self._repository.approval(db, candidate_id, area)
        if row is None:
            row = models.FactibilityApproval(
                candidate_id=candidate_id,
                projection_id=projection_id,
                area=area,
                approved_by_id=user.id,
                approved_at=datetime.now(timezone.utc),
            )
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:
                db.rollback()
                row = self._repository.approval(db, candidate_id, area)
                if row is None:
                    raise
        return {
            "candidate_id": candidate_id,
            "area": row.area,
            "approved_at": row.approved_at,
            "approved_by_id": row.approved_by_id,
        }

    def sync_version(self, db: Session) -> dict[str, str]:
        state = (self._repository.sync_database_state(db), self._adapters.files_state())
        raw = json.dumps(state, default=str, ensure_ascii=True)
        return {"version": hashlib.sha256(raw.encode("utf-8")).hexdigest()}

    def sales_sheet(self, db: Session, candidate_id: int) -> dict:
        return self._adapters.read_sales_sheet(
            self._project_candidate(db, candidate_id)
        )

    def update_sales_sheet(
        self,
        db: Session,
        candidate_id: int,
        payload: schemas.CandidateProjectVariablesIn,
    ) -> dict:
        return self._adapters.write_sales_sheet(
            self._project_candidate(db, candidate_id), payload
        )

    def _location_payload(
        self,
        db: Session,
        candidate: models.LocationCandidate,
        progress_rows: list[models.FactibilityTaskProgress] | None = None,
        decision: models.FactibilityLocationDecision | None = None,
        approvals: list[models.FactibilityApproval] | None = None,
    ) -> dict:
        rows = (
            progress_rows
            if progress_rows is not None
            else self._repository.progress_for_candidate(db, candidate.id)
        )
        decision = (
            decision
            if decision is not None
            else self._repository.decision_for_candidate(db, candidate.id)
        )
        approvals = (
            approvals
            if approvals is not None
            else self._repository.approvals_for_candidate(db, candidate.id)
        )
        groups, completion = build_progress(rows)
        return {
            "candidate": self._adapters.candidate_out(db, candidate),
            "sales_sheet": self._adapters.read_sales_sheet(candidate),
            "decision": ({
                "decision": decision.decision,
                "updated_at": decision.updated_at,
                "updated_by_id": decision.updated_by_id,
            } if decision else None),
            "approvals": {
                row.area: {
                    "area": row.area,
                    "approved_at": row.approved_at,
                    "approved_by_id": row.approved_by_id,
                }
                for row in approvals
            },
            "completion": completion,
            "task_groups": groups,
        }

    def _project_candidate(
        self, db: Session, candidate_id: int
    ) -> models.LocationCandidate:
        candidate = self._repository.project_candidate(db, candidate_id)
        if candidate is None:
            raise HTTPException(404, "El local no está disponible en Proyectos.")
        return candidate


__all__ = ["FactibilityAdapters", "FactibilityService"]
