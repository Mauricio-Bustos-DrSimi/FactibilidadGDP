"""Storage port used by document use cases."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.documents.types import DocumentContext, PreparedDocument, StoredDocument


class DocumentStoragePort(Protocol):
    def list(
        self,
        relative: Path,
        *,
        allowed: set[str] | None = None,
        newest_first: bool = True,
    ) -> list[StoredDocument]: ...

    def store_many(
        self,
        relative: Path,
        documents: list[PreparedDocument],
        *,
        maximum_total: int | None = None,
    ) -> list[StoredDocument]: ...

    def resolve_existing(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
    ) -> Path: ...

    def delete(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
        prune: int = 1,
    ) -> None: ...

    def state(self, relative: Path) -> tuple[int, int]: ...

    def read_bytes(self, relative: Path, filename: str) -> bytes | None: ...

    def read_existing(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
    ) -> bytes: ...

    def write_atomic(self, relative: Path, filename: str, content: bytes) -> None: ...


class FactibilityDocumentRepository:
    """Persists traceability metadata exclusively in ``factibilidad.*``."""

    def record(
        self,
        db: Session,
        context: DocumentContext,
        prepared: PreparedDocument,
        stored: StoredDocument,
        *,
        user_id: str | None,
    ) -> models.FactibilityDocument:
        row = models.FactibilityDocument(
            candidate_id=context.candidate_id,
            projection_id=context.projection_id,
            local_reference=context.local,
            area=context.area,
            group_key=context.macro_task,
            category=context.category,
            original_name=prepared.original_name,
            stored_name=stored.name,
            relative_path=stored.relative_path,
            extension=stored.path.suffix.lower(),
            content_type=stored.content_type,
            size=stored.size,
            sha256=stored.sha256,
            uploaded_by_id=user_id,
            present=True,
        )
        db.add(row)
        return row

    def list_active(
        self,
        db: Session,
        context: DocumentContext,
    ) -> list[models.FactibilityDocument]:
        statement = select(models.FactibilityDocument).where(
            models.FactibilityDocument.candidate_id == context.candidate_id,
            models.FactibilityDocument.category == context.category,
            models.FactibilityDocument.present.is_(True),
        )
        if context.area is not None:
            statement = statement.where(
                models.FactibilityDocument.area == context.area
            )
        if context.macro_task is not None:
            statement = statement.where(
                models.FactibilityDocument.group_key == context.macro_task
            )
        return list(db.scalars(statement).all())

    def mark_absent(
        self,
        db: Session,
        context: DocumentContext,
        stored_name: str,
    ) -> None:
        statement = select(models.FactibilityDocument).where(
            models.FactibilityDocument.candidate_id == context.candidate_id,
            models.FactibilityDocument.category == context.category,
            models.FactibilityDocument.stored_name == stored_name,
            models.FactibilityDocument.present.is_(True),
        )
        if context.macro_task is not None:
            statement = statement.where(
                models.FactibilityDocument.group_key == context.macro_task
            )
        row = db.scalar(statement)
        if row is not None:
            row.present = False


__all__ = ["DocumentStoragePort", "FactibilityDocumentRepository"]
