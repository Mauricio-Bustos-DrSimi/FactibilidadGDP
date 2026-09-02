"""Stable HTTP adapter for the Gestor de Proyecciones module."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.gdp.service import GDPService


def create_gdp_router(service: GDPService) -> APIRouter:
    router = APIRouter(tags=["GDP"])

    @router.post("/projects", response_model=schemas.ProjectOut)
    def create_project(
        payload: schemas.ProjectCreate,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_role("sysadmin")),
    ):
        return service.create_project(db, payload)

    @router.get("/projects", response_model=list[schemas.ProjectOut])
    def list_projects(
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.get_current_user),
    ):
        return service.list_projects(db)

    @router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
    def get_project(
        project_id: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.get_current_user),
    ):
        return service.get_project(db, project_id)

    @router.get("/queue", response_model=schemas.QueueOut)
    def get_queue(
        project_id: Optional[str] = None,
        sort_by: str = "score",
        sort_dir: str = "desc",
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.queue(db, user, project_id, sort_by, sort_dir, division)

    @router.get("/candidates", response_model=list[schemas.CandidateOut])
    def list_candidates(
        project_id: Optional[str] = None,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.list_candidates(db, user, project_id, division)

    @router.get("/funnel/baseline")
    def funnel_baseline(
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.get_current_user),
    ):
        return service.funnel_baseline(db)

    @router.get("/candidates/by-projection/{projection_id}", response_model=schemas.CandidateOut)
    def get_candidate_by_projection(
        projection_id: str,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.candidate_by_projection(db, user, projection_id, division)

    @router.get("/candidates/by-projection/{projection_id}/audit")
    def candidate_audit_by_projection(
        projection_id: str,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.candidate_audit_by_projection(db, user, projection_id, division)

    @router.get("/candidates/{candidate_id}", response_model=schemas.CandidateOut)
    def get_candidate(
        candidate_id: int,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.candidate(db, user, candidate_id, division)

    @router.get("/candidates/{candidate_id}/reviews", response_model=list[schemas.ReviewOut])
    def candidate_reviews(
        candidate_id: int,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.reviews(db, user, candidate_id, division)

    @router.post("/candidates/{candidate_id}/comment", response_model=schemas.ReviewOut)
    def comment_candidate(
        candidate_id: int,
        payload: schemas.NoteIn,
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.comment(db, user, candidate_id, payload, division)

    @router.post("/candidates/{candidate_id}/status", response_model=schemas.CandidateActionOut)
    def update_candidate_status(
        candidate_id: int,
        payload: schemas.CandidateStatusUpdate,
        request: Request,
        background_tasks: BackgroundTasks,
        sort_by: str = "score",
        sort_dir: str = "desc",
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.update_status(
            db, user, candidate_id, payload, request, background_tasks,
            sort_by, sort_dir, division,
        )

    @router.post("/candidates/{candidate_id}/review", response_model=schemas.CandidateActionOut)
    def review_candidate(
        candidate_id: int,
        payload: schemas.ReviewCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        sort_by: str = "score",
        sort_dir: str = "desc",
        division: Optional[str] = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.submit_review(
            db, user, candidate_id, payload, request, background_tasks,
            sort_by, sort_dir, division,
        )

    @router.post("/candidates/{candidate_id}/send-back", response_model=schemas.CandidateOut)
    def send_back_candidate(
        candidate_id: int,
        payload: schemas.NoteIn,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.send_back(db, user, candidate_id, payload)

    @router.post("/candidates/{candidate_id}/reopen", response_model=schemas.CandidateOut)
    def reopen_candidate(
        candidate_id: int,
        payload: schemas.NoteIn,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        return service.reopen(db, user, candidate_id, payload)

    @router.get("/stats")
    def stats(
        project_id: Optional[str] = None,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_role("sysadmin")),
    ):
        return service.stats(db, project_id)

    @router.get("/business", response_model=list[schemas.BusinessOut])
    def list_business(
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.get_current_user),
    ):
        return service.business(db)

    return router


__all__ = ["create_gdp_router"]
