"""Value objects exposed by the document management boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


class DocumentUpload(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class DocumentContext:
    domain: Literal["gdp", "factibilidad"]
    candidate_id: int
    projection_id: str
    local: str | None = None
    area: str | None = None
    macro_task: str | None = None
    category: Literal["candidate", "macro_task", "sheet_image"] = "candidate"


@dataclass(frozen=True)
class FactibilityDocumentGroup:
    area: str
    key: str
    title: str
    tasks: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PreparedDocument:
    original_name: str
    name: str
    content: bytes
    content_type: str
    sha256: str


@dataclass(frozen=True)
class StoredDocument:
    name: str
    path: Path
    size: int
    content_type: str
    sha256: str
    modified_at: datetime
    relative_path: str
    context: DocumentContext | None = None


@dataclass(frozen=True)
class DocumentDownload:
    path: Path
    media_type: str
    disposition: str | None = None


__all__ = [
    "DocumentContext",
    "DocumentDownload",
    "DocumentUpload",
    "FactibilityDocumentGroup",
    "PreparedDocument",
    "StoredDocument",
]
