"""HTTP adapters for GDP and Factibilidad document operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.documents.service import DocumentService
from app.documents.types import DocumentDownload


@dataclass(frozen=True)
class DocumentRouterAdapters:
    candidate: Callable[[Session, int], models.LocationCandidate]
    factibility_candidate: Callable[[Session, int], models.LocationCandidate]
    require_viewer_read_only: Callable[[models.User], None]
    require_candidate_visible: Callable[
        [Session, models.LocationCandidate, models.User, str | None], None
    ]
    candidate_group: Callable[[Session, models.LocationCandidate], str]
    factibility_pdf: Callable[
        [Session, models.LocationCandidate], tuple[bytes, str]
    ]


def create_document_router(
    service: DocumentService,
    adapters: DocumentRouterAdapters,
) -> APIRouter:
    router = APIRouter(tags=["Documents"])

    def visible_candidate(
        db: Session,
        candidate_id: int,
        user: models.User,
        division: str | None,
    ) -> models.LocationCandidate:
        adapters.require_viewer_read_only(user)
        candidate = adapters.candidate(db, candidate_id)
        adapters.require_candidate_visible(db, candidate, user, division)
        return candidate

    @router.get(
        "/candidates/{candidate_id}/attachments",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def list_candidate_attachments(
        candidate_id: int,
        division: str | None = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        candidate = visible_candidate(db, candidate_id, user, division)
        return service.list_candidate_documents(candidate)

    @router.post(
        "/candidates/{candidate_id}/attachments",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    async def upload_candidate_attachments(
        candidate_id: int,
        files: list[UploadFile] = File(...),
        division: str | None = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        candidate = visible_candidate(db, candidate_id, user, division)
        return await service.upload_candidate_documents(
            db,
            user,
            candidate,
            files,
            adapters.candidate_group(db, candidate),
        )

    @router.get("/candidates/{candidate_id}/attachments/{filename}")
    def get_candidate_attachment(
        candidate_id: int,
        filename: str,
        division: str | None = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        candidate = visible_candidate(db, candidate_id, user, division)
        return _file_response(service.open_candidate_document(candidate, filename))

    @router.delete(
        "/candidates/{candidate_id}/attachments/{filename}",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def delete_candidate_attachment(
        candidate_id: int,
        filename: str,
        division: str | None = None,
        db: Session = Depends(get_db),
        user: models.User = Depends(auth.get_current_user),
    ):
        candidate = visible_candidate(db, candidate_id, user, division)
        return service.delete_candidate_document(db, user, candidate, filename)

    @router.get("/factibilidad/locations/{candidate_id}/sales-sheet.pdf")
    def download_factibility_sales_sheet(
        candidate_id: int,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        pdf, filename = adapters.factibility_pdf(db, candidate)
        return StreamingResponse(
            iter([pdf]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    @router.get(
        "/factibilidad/locations/{candidate_id}/sales-sheet/images",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def list_factibility_sales_sheet_images(
        candidate_id: int,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return service.list_sheet_images(candidate)

    @router.post(
        "/factibilidad/locations/{candidate_id}/sales-sheet/images",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    async def upload_factibility_sales_sheet_images(
        candidate_id: int,
        files: list[UploadFile] = File(...),
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return await service.upload_sheet_images(candidate, files)

    @router.get(
        "/factibilidad/locations/{candidate_id}/sales-sheet/images/{filename}"
    )
    def get_factibility_sales_sheet_image(
        candidate_id: int,
        filename: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return _file_response(service.open_sheet_image(candidate, filename))

    @router.delete(
        "/factibilidad/locations/{candidate_id}/sales-sheet/images/{filename}",
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def delete_factibility_sales_sheet_image(
        candidate_id: int,
        filename: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return service.delete_sheet_image(candidate, filename)

    @router.get("/factibilidad/locations/{candidate_id}/attachments")
    def list_factibility_location_library(
        candidate_id: int,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return service.factibility_library(candidate)

    group_route = (
        "/factibilidad/locations/{candidate_id}/groups/{group_key}/attachments"
    )

    @router.get(
        group_route,
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def list_factibility_attachments(
        candidate_id: int,
        group_key: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return service.list_factibility_documents(candidate, group_key)

    @router.post(
        group_route,
        response_model=list[schemas.CandidateAttachmentOut],
    )
    async def upload_factibility_attachments(
        candidate_id: int,
        group_key: str,
        files: list[UploadFile] = File(...),
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return await service.upload_factibility_documents(
            candidate, group_key, files
        )

    file_route = f"{group_route}/{{filename}}"

    @router.get(file_route)
    def get_factibility_attachment(
        candidate_id: int,
        group_key: str,
        filename: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        download = service.open_factibility_document(
            candidate, group_key, filename
        )
        return _file_response(download)

    @router.delete(
        file_route,
        response_model=list[schemas.CandidateAttachmentOut],
    )
    def delete_factibility_attachment(
        candidate_id: int,
        group_key: str,
        filename: str,
        db: Session = Depends(get_db),
        _: models.User = Depends(auth.require_factibility_access),
    ):
        candidate = adapters.factibility_candidate(db, candidate_id)
        return service.delete_factibility_document(
            candidate, group_key, filename
        )

    return router


def _file_response(download: DocumentDownload) -> FileResponse:
    headers = {}
    if download.disposition:
        headers["Content-Disposition"] = download.disposition
    if download.media_type == "image/svg+xml":
        headers["X-Content-Type-Options"] = "nosniff"
    return FileResponse(
        download.path,
        media_type=download.media_type,
        headers=headers,
    )


__all__ = ["DocumentRouterAdapters", "create_document_router"]
