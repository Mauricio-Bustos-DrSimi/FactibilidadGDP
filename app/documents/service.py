"""Document use cases shared by GDP and Factibilidad."""
from __future__ import annotations

import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas, workflow
from app.documents.policy import ATTACHMENT_TYPES, IMAGE_TYPES, SHEET_IMAGE_TYPES, DocumentPolicy
from app.documents.repository import DocumentStorage
from app.documents.types import DocumentDownload, PreparedDocument, StoredDocument

logger = logging.getLogger("factibilidad.documents")


@dataclass(frozen=True)
class DocumentAdapters:
    projection_id: Callable[[models.LocationCandidate], str]
    factibility_groups: tuple[tuple[str, str, str, tuple], ...]


class DocumentService:
    def __init__(
        self,
        storage: DocumentStorage,
        policy: DocumentPolicy,
        adapters: DocumentAdapters,
    ) -> None:
        self.storage = storage
        self.policy = policy
        self.adapters = adapters
        self._groups = {key: (area, title) for area, key, title, _ in adapters.factibility_groups}

    async def prepare_uploads(self, files: list[UploadFile]) -> list[PreparedDocument]:
        self.policy.validate_count(len(files))
        prepared: list[PreparedDocument] = []
        for upload in files:
            try:
                content = await upload.read(self.policy.max_bytes + 1)
            finally:
                await upload.close()
            prepared.append(self.policy.prepare(upload.filename or "", content))
        return prepared

    def list_candidate_documents(
        self, candidate: models.LocationCandidate
    ) -> list[schemas.CandidateAttachmentOut]:
        documents = self.storage.list(self._candidate_dir(candidate))
        return [self._candidate_out(candidate.id, item) for item in documents]

    async def upload_candidate_documents(
        self,
        db: Session,
        user: models.User,
        candidate: models.LocationCandidate,
        files: list[UploadFile],
        candidate_group: str,
    ) -> list[schemas.CandidateAttachmentOut]:
        if candidate_group != "proposed":
            raise HTTPException(
                409,
                "Files can only be attached while the candidate is in Propuestos.",
            )
        prepared = await self.prepare_uploads(files)
        relative = self._candidate_dir(candidate)
        stored = self.storage.store_many(relative, prepared)
        db.add(
            models.Review(
                candidate_id=candidate.id,
                stage=(
                    workflow.role_stage(user.role)
                    or candidate.current_stage
                    or workflow.COMITE
                ),
                reviewer_id=user.id,
                action="attachment_upload",
                note=", ".join(item.name for item in stored),
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            for item in stored:
                with suppress(HTTPException):
                    self.storage.delete(relative, item.name)
            raise
        return self.list_candidate_documents(candidate)

    def open_candidate_document(
        self, candidate: models.LocationCandidate, filename: str
    ) -> DocumentDownload:
        path = self.storage.resolve_existing(
            self._candidate_dir(candidate),
            filename,
            allowed=set(ATTACHMENT_TYPES),
        )
        return self._download(path)

    def delete_candidate_document(
        self,
        db: Session,
        user: models.User,
        candidate: models.LocationCandidate,
        filename: str,
    ) -> list[schemas.CandidateAttachmentOut]:
        relative = self._candidate_dir(candidate)
        original = self.storage.read_existing(
            relative, filename, allowed=set(ATTACHMENT_TYPES)
        )
        self.storage.delete(relative, filename, allowed=set(ATTACHMENT_TYPES))
        db.add(
            models.Review(
                candidate_id=candidate.id,
                stage=(
                    workflow.role_stage(user.role)
                    or candidate.current_stage
                    or workflow.COMITE
                ),
                reviewer_id=user.id,
                action="attachment_delete",
                note=filename,
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            self.storage.store_many(
                relative, [self.policy.prepare(filename, original)]
            )
            raise
        return self.list_candidate_documents(candidate)

    def list_factibility_documents(
        self, candidate: models.LocationCandidate, group_key: str
    ) -> list[schemas.CandidateAttachmentOut]:
        self._require_group(group_key)
        documents = self.storage.list(
            self._factibility_group_dir(candidate, group_key)
        )
        return [
            self._factibility_out(candidate.id, group_key, item)
            for item in documents
        ]

    async def upload_factibility_documents(
        self,
        candidate: models.LocationCandidate,
        group_key: str,
        files: list[UploadFile],
    ) -> list[schemas.CandidateAttachmentOut]:
        self._require_group(group_key)
        prepared = await self.prepare_uploads(files)
        self.storage.store_many(
            self._factibility_group_dir(candidate, group_key), prepared
        )
        return self.list_factibility_documents(candidate, group_key)

    def open_factibility_document(
        self,
        candidate: models.LocationCandidate,
        group_key: str,
        filename: str,
    ) -> DocumentDownload:
        self._require_group(group_key)
        path = self.storage.resolve_existing(
            self._factibility_group_dir(candidate, group_key),
            filename,
            allowed=set(ATTACHMENT_TYPES),
        )
        return self._download(path)

    def delete_factibility_document(
        self,
        candidate: models.LocationCandidate,
        group_key: str,
        filename: str,
    ) -> list[schemas.CandidateAttachmentOut]:
        self._require_group(group_key)
        self.storage.delete(
            self._factibility_group_dir(candidate, group_key),
            filename,
            allowed=set(ATTACHMENT_TYPES),
            prune=3,
        )
        return self.list_factibility_documents(candidate, group_key)

    def factibility_library(self, candidate: models.LocationCandidate) -> list[dict]:
        return [
            {
                "area": area,
                "key": key,
                "title": title,
                "files": self.list_factibility_documents(candidate, key),
            }
            for area, key, title, _ in self.adapters.factibility_groups
        ]

    def list_sheet_images(
        self, candidate: models.LocationCandidate
    ) -> list[schemas.CandidateAttachmentOut]:
        return [
            self._sheet_image_out(candidate.id, item)
            for item in self._sheet_image_documents(candidate)
        ]

    async def upload_sheet_images(
        self,
        candidate: models.LocationCandidate,
        files: list[UploadFile],
    ) -> list[schemas.CandidateAttachmentOut]:
        prepared = await self.prepare_uploads(files)
        if any(
            Path(item.name).suffix.lower() not in SHEET_IMAGE_TYPES
            for item in prepared
        ):
            raise HTTPException(400, "La ficha solo admite archivos de imagen.")
        self.storage.store_many(
            self._sheet_image_dir(candidate), prepared, maximum_total=2
        )
        return self.list_sheet_images(candidate)

    def open_sheet_image(
        self, candidate: models.LocationCandidate, filename: str
    ) -> DocumentDownload:
        try:
            path = self.storage.resolve_existing(
                self._sheet_image_dir(candidate),
                filename,
                allowed=set(SHEET_IMAGE_TYPES),
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(404, "Imagen no encontrada.") from exc
            raise
        return DocumentDownload(
            path=path,
            media_type=SHEET_IMAGE_TYPES[path.suffix.lower()],
        )

    def delete_sheet_image(
        self, candidate: models.LocationCandidate, filename: str
    ) -> list[schemas.CandidateAttachmentOut]:
        try:
            self.storage.delete(
                self._sheet_image_dir(candidate),
                filename,
                allowed=set(SHEET_IMAGE_TYPES),
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(404, "Imagen no encontrada.") from exc
            raise
        return self.list_sheet_images(candidate)

    def sheet_image_paths(self, candidate: models.LocationCandidate) -> list[Path]:
        return [item.path for item in self._sheet_image_documents(candidate)]

    def project_sheet_photos(self, candidate: models.LocationCandidate) -> list[Path]:
        documents = self.storage.list(
            self._candidate_dir(candidate), allowed=set(SHEET_IMAGE_TYPES)
        )
        return [item.path for item in documents[:3]]

    def read_sales_sheet(
        self, candidate: models.LocationCandidate, default: dict
    ) -> dict:
        try:
            content = self.storage.read_bytes(
                self._factibility_candidate_dir(candidate), "ficha_ventas.json"
            )
        except HTTPException as exc:
            logger.exception("Could not read the Factibilidad sales sheet copy.")
            raise HTTPException(
                500, "No fue posible leer la ficha propia de Factibilidad."
            ) from exc
        if content is None:
            return default
        try:
            saved = json.loads(content.decode("utf-8"))
            return schemas.CandidateProjectVariablesIn.model_validate(
                saved
            ).model_dump(mode="json")
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise HTTPException(
                500, "No fue posible leer la ficha propia de Factibilidad."
            ) from exc

    def write_sales_sheet(
        self,
        candidate: models.LocationCandidate,
        payload: schemas.CandidateProjectVariablesIn,
    ) -> dict:
        values = payload.model_dump(mode="json")
        content = json.dumps(values, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            self.storage.write_atomic(
                self._factibility_candidate_dir(candidate), "ficha_ventas.json", content
            )
        except HTTPException as exc:
            logger.exception("Could not store the Factibilidad sales sheet copy.")
            raise HTTPException(
                500, f"No fue posible guardar la ficha de Factibilidad: {exc.detail}"
            ) from exc
        return values

    def factibility_state(self) -> tuple[int, int]:
        return self.storage.state(Path("Factibilidad"))

    def _candidate_dir(self, candidate: models.LocationCandidate) -> Path:
        return Path(f"Proyeccion{self.adapters.projection_id(candidate)}")

    def _factibility_candidate_dir(self, candidate: models.LocationCandidate) -> Path:
        return Path("Factibilidad") / f"Proyeccion{self.adapters.projection_id(candidate)}"

    def _factibility_group_dir(
        self, candidate: models.LocationCandidate, group_key: str
    ) -> Path:
        area, _ = self._require_group(group_key)
        return self._factibility_candidate_dir(candidate) / area / group_key

    def _sheet_image_dir(self, candidate: models.LocationCandidate) -> Path:
        return self._factibility_candidate_dir(candidate) / "ficha_imagenes"

    def _sheet_image_documents(
        self, candidate: models.LocationCandidate
    ) -> list[StoredDocument]:
        documents = self.storage.list(
            self._sheet_image_dir(candidate),
            allowed=set(SHEET_IMAGE_TYPES),
            newest_first=False,
        )
        return documents[:2]

    def _require_group(self, group_key: str) -> tuple[str, str]:
        definition = self._groups.get(group_key)
        if not definition:
            raise HTTPException(404, "La macrotarea de Factibilidad no existe.")
        return definition

    @staticmethod
    def _candidate_out(
        candidate_id: int, item: StoredDocument
    ) -> schemas.CandidateAttachmentOut:
        return schemas.CandidateAttachmentOut(
            name=item.name,
            size=item.size,
            content_type=item.content_type,
            modified_at=item.modified_at,
            url=(
                f"/candidates/{candidate_id}/attachments/"
                f"{quote(item.name, safe='')}"
            ),
        )

    @staticmethod
    def _factibility_out(
        candidate_id: int,
        group_key: str,
        item: StoredDocument,
    ) -> schemas.CandidateAttachmentOut:
        return schemas.CandidateAttachmentOut(
            name=item.name,
            size=item.size,
            content_type=item.content_type,
            modified_at=item.modified_at,
            url=(
                f"/factibilidad/locations/{candidate_id}/groups/"
                f"{quote(group_key, safe='')}/attachments/"
                f"{quote(item.name, safe='')}"
            ),
        )

    @staticmethod
    def _sheet_image_out(
        candidate_id: int, item: StoredDocument
    ) -> schemas.CandidateAttachmentOut:
        return schemas.CandidateAttachmentOut(
            name=item.name,
            size=item.size,
            content_type=item.content_type,
            modified_at=item.modified_at,
            url=(
                f"/factibilidad/locations/{candidate_id}/sales-sheet/images/"
                f"{quote(item.name, safe='')}"
            ),
        )

    @staticmethod
    def _download(path: Path) -> DocumentDownload:
        suffix = path.suffix.lower()
        mode = "inline" if suffix in IMAGE_TYPES or suffix == ".pdf" else "attachment"
        if suffix == ".svg":
            mode = "attachment"
        return DocumentDownload(
            path=path,
            media_type=ATTACHMENT_TYPES[suffix],
            disposition=f"{mode}; filename*=UTF-8''{quote(path.name, safe='')}",
        )


__all__ = ["DocumentAdapters", "DocumentService"]
