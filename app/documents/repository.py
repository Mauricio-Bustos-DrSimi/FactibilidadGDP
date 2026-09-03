"""Storage port used by document use cases."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.documents.types import PreparedDocument, StoredDocument


class DocumentStorage(Protocol):
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


__all__ = ["DocumentStorage"]
