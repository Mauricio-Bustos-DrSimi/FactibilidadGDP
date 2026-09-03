"""Value objects exposed by the document management boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PreparedDocument:
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


@dataclass(frozen=True)
class DocumentDownload:
    path: Path
    media_type: str
    disposition: str | None = None


__all__ = ["DocumentDownload", "PreparedDocument", "StoredDocument"]
