"""Filesystem adapter confined to the configured document root."""
from __future__ import annotations

import hashlib
import mimetypes
import os
import threading
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from app.documents.errors import DocumentError
from app.documents.policy import ATTACHMENT_TYPES
from app.documents.types import PreparedDocument, StoredDocument


class FileSystemDocumentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = threading.RLock()

    def directory(self, relative: Path, *, create: bool = False) -> Path:
        folder = (self.root / relative).resolve()
        if folder != self.root and self.root not in folder.parents:
            raise DocumentError(404, "Attachment not found")
        if create:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DocumentError(
                    500, f"Could not create attachment directory: {exc}"
                ) from exc
        return folder

    def list(
        self,
        relative: Path,
        *,
        allowed: set[str] | None = None,
        newest_first: bool = True,
    ) -> list[StoredDocument]:
        folder = self.directory(relative)
        if not folder.exists():
            return []
        extensions = allowed or set(ATTACHMENT_TYPES)
        paths = [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        ]
        paths.sort(
            key=lambda path: (path.stat().st_mtime, path.name.lower()),
            reverse=newest_first,
        )
        return [self.describe(path) for path in paths]

    def store_many(
        self,
        relative: Path,
        documents: list[PreparedDocument],
        *,
        maximum_total: int | None = None,
    ) -> list[StoredDocument]:
        with self._lock:
            folder = self.directory(relative)
            existing = (
                [path for path in folder.iterdir() if path.is_file()]
                if folder.exists()
                else []
            )
            if (
                maximum_total is not None
                and len(existing) + len(documents) > maximum_total
            ):
                raise DocumentError(400, "La ficha admite un máximo de dos imágenes.")
            folder = self.directory(relative, create=True)
            occupied = {path.name.lower() for path in existing}
            written: list[Path] = []
            try:
                for document in documents:
                    target = self._write_unique(folder, document, occupied)
                    written.append(target)
                return [self.describe(path) for path in written]
            except (OSError, DocumentError) as exc:
                for path in written:
                    with suppress(OSError):
                        path.unlink()
                if isinstance(exc, DocumentError):
                    raise
                raise DocumentError(500, f"Could not store file: {exc}") from exc

    def resolve_existing(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
    ) -> Path:
        folder = self.directory(relative)
        suffix = Path(filename).suffix.lower()
        if Path(filename).name != filename or (allowed is not None and suffix not in allowed):
            raise DocumentError(404, "Attachment not found")
        path = (folder / filename).resolve()
        if path.parent != folder or not path.is_file():
            raise DocumentError(404, "Attachment not found")
        return path

    def delete(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
        prune: int = 1,
    ) -> None:
        with self._lock:
            path = self.resolve_existing(relative, filename, allowed=allowed)
            try:
                path.unlink()
                folder = path.parent
                for _ in range(prune):
                    if folder == self.root or self.root not in folder.parents:
                        break
                    with suppress(OSError):
                        folder.rmdir()
                    folder = folder.parent
            except OSError as exc:
                raise DocumentError(500, f"Could not delete file: {exc}") from exc

    def state(self, relative: Path) -> tuple[int, int]:
        root = self.directory(relative)
        files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
        return len(files), max((path.stat().st_mtime_ns for path in files), default=0)

    def read_bytes(self, relative: Path, filename: str) -> bytes | None:
        folder = self.directory(relative)
        path = (folder / filename).resolve()
        if path.parent != folder or not path.is_file():
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            raise DocumentError(500, f"Could not read file: {exc}") from exc

    def read_existing(
        self,
        relative: Path,
        filename: str,
        *,
        allowed: set[str] | None = None,
    ) -> bytes:
        path = self.resolve_existing(relative, filename, allowed=allowed)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise DocumentError(500, f"Could not read file: {exc}") from exc

    def write_atomic(self, relative: Path, filename: str, content: bytes) -> None:
        with self._lock:
            folder = self.directory(relative, create=True)
            path = (folder / filename).resolve()
            if path.parent != folder:
                raise DocumentError(400, "Invalid attachment path.")
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as target:
                    target.write(content)
                os.replace(temporary, path)
            except OSError as exc:
                with suppress(OSError):
                    temporary.unlink()
                raise DocumentError(500, f"Could not store file: {exc}") from exc

    def restore_exact(self, relative: Path, filename: str, content: bytes) -> None:
        """Restore compensation bytes without renaming or overwriting another upload."""
        with self._lock:
            folder = self.directory(relative, create=True)
            target = (folder / filename).resolve()
            if target.parent != folder or Path(filename).name != filename:
                raise DocumentError(500, "Could not restore deleted file safely.")
            try:
                with target.open("xb") as output:
                    output.write(content)
            except FileExistsError as exc:
                try:
                    if target.read_bytes() == content:
                        return
                except OSError:
                    pass
                raise DocumentError(
                    500, "Could not restore deleted file because its name is occupied."
                ) from exc
            except OSError as exc:
                raise DocumentError(500, f"Could not restore deleted file: {exc}") from exc

    def describe(self, path: Path) -> StoredDocument:
        stat = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return StoredDocument(
            name=path.name,
            path=path,
            size=stat.st_size,
            content_type=ATTACHMENT_TYPES.get(
                path.suffix.lower(),
                mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
            ),
            sha256=digest.hexdigest(),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            relative_path=path.relative_to(self.root).as_posix(),
        )

    @staticmethod
    def _write_unique(
        folder: Path,
        document: PreparedDocument,
        occupied: set[str],
    ) -> Path:
        source = Path(document.name)
        counter = 1
        while True:
            candidate_name = (
                document.name
                if counter == 1
                else f"{source.stem}_{counter}{source.suffix}"
            )
            counter += 1
            if candidate_name.lower() in occupied:
                continue
            target = folder / candidate_name
            try:
                with target.open("xb") as output:
                    output.write(document.content)
            except FileExistsError:
                continue
            occupied.add(candidate_name.lower())
            return target


__all__ = ["FileSystemDocumentStorage"]
