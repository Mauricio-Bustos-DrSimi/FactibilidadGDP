"""Stable HTTP adapter for Factibilidad use cases."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.factibilidad.service import FactibilityService


def create_factibility_router(service: FactibilityService) -> APIRouter:
    router = APIRouter(prefix="/factibilidad", tags=["Factibilidad"])

    @router.get("/locations")
    def list_locations(
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        return service.list_locations(db)

    @router.put("/locations/{candidate_id}/tasks/{task_key}")
    def update_task(
        candidate_id: int,
        task_key: str,
        payload: schemas.FactibilityTaskUpdate,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.require_factibility_access),
    ):
        return service.update_task(db, user, candidate_id, task_key, payload)

    @router.put("/locations/{candidate_id}/decision")
    def update_decision(
        candidate_id: int,
        payload: schemas.FactibilityDecisionUpdate,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.require_factibility_access),
    ):
        return service.update_decision(db, user, candidate_id, payload)

    @router.put("/locations/{candidate_id}/approvals/{area}")
    def approve_area(
        candidate_id: int,
        area: schemas.FactibilityApprovalArea,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.require_factibility_access),
    ):
        return service.approve_area(db, user, candidate_id, area)

    @router.get("/sync-version")
    def sync_version(
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        return service.sync_version(db)

    @router.get("/locations/{candidate_id}/sales-sheet")
    def get_sales_sheet(
        candidate_id: int,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        return service.sales_sheet(db, candidate_id)

    @router.put("/locations/{candidate_id}/sales-sheet")
    def update_sales_sheet(
        candidate_id: int,
        payload: schemas.CandidateProjectVariablesIn,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        return service.update_sales_sheet(db, candidate_id, payload)

    return router


__all__ = ["create_factibility_router"]
