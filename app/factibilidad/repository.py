"""Persistence boundary for data owned by Factibilidad.

Reads of LocationCandidate are limited to the replicated Gestor read model;
writes target only the existing Factibilidad models.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, workflow


class FactibilityRepository:
    def project_candidate(
        self, db: Session, candidate_id: int
    ) -> models.LocationCandidate | None:
        candidate = db.get(models.LocationCandidate, candidate_id)
        if not candidate or workflow.candidate_group(db, candidate) != "opening":
            return None
        return candidate

    def project_candidates(self, db: Session) -> list[models.LocationCandidate]:
        return [
            candidate
            for candidate in db.scalars(
                select(models.LocationCandidate).order_by(
                    models.LocationCandidate.id.desc()
                )
            ).all()
            if workflow.candidate_group(db, candidate) == "opening"
        ]

    def progress_for_candidates(
        self, db: Session, candidate_ids: list[int]
    ) -> dict[int, list[models.FactibilityTaskProgress]]:
        result: dict[int, list[models.FactibilityTaskProgress]] = {}
        if not candidate_ids:
            return result
        for row in db.scalars(
            select(models.FactibilityTaskProgress).where(
                models.FactibilityTaskProgress.candidate_id.in_(candidate_ids)
            )
        ).all():
            result.setdefault(row.candidate_id, []).append(row)
        return result

    def decisions_for_candidates(
        self, db: Session, candidate_ids: list[int]
    ) -> dict[int, models.FactibilityLocationDecision]:
        if not candidate_ids:
            return {}
        return {
            row.candidate_id: row
            for row in db.scalars(
                select(models.FactibilityLocationDecision).where(
                    models.FactibilityLocationDecision.candidate_id.in_(candidate_ids)
                )
            ).all()
        }

    def approvals_for_candidates(
        self, db: Session, candidate_ids: list[int]
    ) -> dict[int, list[models.FactibilityApproval]]:
        result: dict[int, list[models.FactibilityApproval]] = {}
        if not candidate_ids:
            return result
        for row in db.scalars(
            select(models.FactibilityApproval).where(
                models.FactibilityApproval.candidate_id.in_(candidate_ids)
            )
        ).all():
            result.setdefault(row.candidate_id, []).append(row)
        return result

    def progress_for_candidate(
        self, db: Session, candidate_id: int
    ) -> list[models.FactibilityTaskProgress]:
        return list(
            db.scalars(
                select(models.FactibilityTaskProgress).where(
                    models.FactibilityTaskProgress.candidate_id == candidate_id
                )
            ).all()
        )

    def decision_for_candidate(
        self, db: Session, candidate_id: int
    ) -> models.FactibilityLocationDecision | None:
        return db.scalar(
            select(models.FactibilityLocationDecision).where(
                models.FactibilityLocationDecision.candidate_id == candidate_id
            )
        )

    def approvals_for_candidate(
        self, db: Session, candidate_id: int
    ) -> list[models.FactibilityApproval]:
        return list(
            db.scalars(
                select(models.FactibilityApproval).where(
                    models.FactibilityApproval.candidate_id == candidate_id
                )
            ).all()
        )

    def task(
        self, db: Session, candidate_id: int, task_key: str
    ) -> models.FactibilityTaskProgress | None:
        return db.scalar(
            select(models.FactibilityTaskProgress).where(
                models.FactibilityTaskProgress.candidate_id == candidate_id,
                models.FactibilityTaskProgress.task_key == task_key,
            )
        )

    def approval(
        self, db: Session, candidate_id: int, area: str
    ) -> models.FactibilityApproval | None:
        return db.scalar(
            select(models.FactibilityApproval).where(
                models.FactibilityApproval.candidate_id == candidate_id,
                models.FactibilityApproval.area == area,
            )
        )

    def sync_database_state(self, db: Session) -> tuple:
        return (
            db.execute(
                select(
                    func.count(models.FactibilityTaskProgress.id),
                    func.max(models.FactibilityTaskProgress.updated_at),
                )
            ).one(),
            db.execute(
                select(
                    func.count(models.FactibilityLocationDecision.id),
                    func.max(models.FactibilityLocationDecision.updated_at),
                )
            ).one(),
            db.execute(
                select(
                    func.count(models.FactibilityApproval.id),
                    func.max(models.FactibilityApproval.approved_at),
                )
            ).one(),
            db.execute(
                select(
                    func.count(models.LocationCandidate.id),
                    func.max(models.LocationCandidate.id),
                    func.max(models.LocationCandidate.last_action_at),
                    func.max(models.LocationCandidate.project_at),
                )
            ).one(),
            db.execute(
                select(
                    func.count(models.CandidateProjectVariables.id),
                    func.max(models.CandidateProjectVariables.updated_at),
                )
            ).one(),
        )


__all__ = ["FactibilityRepository"]
